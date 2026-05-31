"""
BigModel Flash ASR 实现

使用火山引擎 BigModel Flash ASR API 进行语音转写。
这是纯粹的 ASR 接口，不依赖 Chat Completions API。

接口文档：https://www.volcengine.com/docs/6561/1631584

API 端点：
- POST https://openspeech.bytedance.com/api/v3/auc/bigmodel/recognize/flash

配置（环境变量）：
- PURE_ASR__APP_KEY: API 密钥（新版控制台 App Key）
- PURE_ASR__BASE_URL: ASR 端点
- PURE_ASR__RESOURCE_ID: 资源 ID
- PURE_ASR__MODEL: 模型名称
- PURE_ASR__TIMEOUT: 超时秒数
"""

import base64
import logging
import uuid
from typing import TYPE_CHECKING, cast, override

import httpx

from ..base import ASRException, ASRResult, BaseASRProvider

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from ....config import PureASRConfig

# 成功状态码
SUCCESS_CODE = "20000000"
SILENCE_CODE = "20000003"


class BigModelFlashASRProvider(BaseASRProvider):
    """BigModel Flash ASR Provider

    直接调用火山引擎 BigModel Flash ASR API，返回详细转写结果。
    支持词级时间戳和置信度。

    与 DoubaoASRProvider 的区别：
    - DoubaoASRProvider: 通过 Chat Completions API 用 prompt 转写，可返回情绪
    - BigModelFlashASRProvider: 调用专用 ASR API，返回词级细节，更快更准
    """

    def __init__(
        self,
        app_key: str,
        base_url: str,
        resource_id: str = "volc.bigasr.auc_turbo",
        model: str = "bigmodel",
        timeout: float = 30.0,
    ):
        self.app_key = app_key
        self.base_url = base_url
        self.resource_id = resource_id
        self.model = model
        self.timeout = timeout
        self._client: httpx.AsyncClient | None = None

    @property
    def client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self.timeout)
        return self._client

    @classmethod
    def from_config(cls, config: "PureASRConfig") -> "BigModelFlashASRProvider":
        """从 PureASRConfig 创建实例"""
        return cls(
            app_key=config.app_key,
            base_url=config.base_url,
            resource_id=config.resource_id,
            model=config.model,
            timeout=config.timeout,
        )

    @override
    async def transcribe(
        self,
        audio: bytes,
        format: str = "mp3",
    ) -> ASRResult:
        """
        使用 BigModel Flash ASR 转写音频

        Args:
            audio: 原始音频数据
            format: 音频格式 (mp3/wav/m4a/ogg等)

        Returns:
            ASRResult: 转写结果
        """
        logger.info(f"BigModel ASR 开始转写 | format={format}, size={len(audio)}")

        request_id = str(uuid.uuid4())
        audio_b64 = base64.b64encode(audio).decode("utf-8")

        headers = {
            "X-Api-App-Key": self.app_key,
            "X-Api-Resource-Id": self.resource_id,
            "X-Api-Request-Id": request_id,
            "X-Api-Sequence": "-1",
        }

        body = {
            "user": {"uid": self.app_key},
            "audio": {"data": audio_b64, "format": format},
            "request": {"model_name": self.model},
        }

        try:
            response = await self.client.post(
                self.base_url,
                json=body,
                headers=headers,
            )

            status_code = response.headers.get("X-Api-Status-Code", "")
            status_msg = response.headers.get("X-Api-Message", "")
            log_id = response.headers.get("X-Tt-Logid", "")

            logger.info(
                f"BigModel ASR 响应 | status={status_code} msg={status_msg} log_id={log_id}"
            )

            if status_code == SUCCESS_CODE:
                data = cast(dict, response.json())
                return self._parse_response(data)

            if status_code == SILENCE_CODE:
                logger.info("BigModel ASR 检测到静音音频")
                return ASRResult(text="")

            # 其他错误
            error_msg = f"ASR 请求失败 | code={status_code} message={status_msg} log_id={log_id}"
            logger.error(error_msg)
            raise ASRException(error_msg)

        except httpx.HTTPError as e:
            logger.error(f"BigModel ASR HTTP 异常 | {e}")
            raise ASRException(f"ASR HTTP 请求失败: {e}", original_error=e) from e
        except ASRException:
            raise
        except Exception as e:
            logger.error(f"BigModel ASR 异常 | {type(e).__name__}: {e}")
            raise ASRException(f"语音转写失败: {e}", original_error=e) from e

    def _parse_response(self, data: dict) -> ASRResult:
        """解析 BigModel Flash ASR 响应"""
        result = data.get("result", {})
        text = result.get("text", "").strip()

        utterances = result.get("utterances", [])

        # 计算平均置信度（如果有多段语音）
        confidence = None
        word_confidences = []
        for utterance in utterances:
            for word in utterance.get("words", []):
                wc = word.get("confidence")
                if wc is not None and wc > 0:
                    word_confidences.append(wc)

        if word_confidences:
            confidence = sum(word_confidences) / len(word_confidences)

        logger.info(f"BigModel ASR 完成 | text={text[:50]}... confidence={confidence}")

        return ASRResult(text=text, confidence=confidence)

    async def transcribe_with_emotion(
        self,
        audio: bytes,
        format: str = "mp3",
    ) -> ASRResult:
        """BigModel Flash 不支持情绪检测，降级为普通转写"""
        return await self.transcribe(audio, format)

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None