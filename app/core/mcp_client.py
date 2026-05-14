"""
MCP Client 封装模块

基于官方 mcp Python SDK 的 MCP Client，实现与 supermemory MCP Server 的 SSE 长连接通信。
设计为单例模式，由 FastAPI lifespan 统一管理生命周期。

supermemory MCP Server 提供语义记忆功能：
- search_memory: 语义搜索用户历史记忆
- add_memory: 添加对话到语义记忆

关键设计：
- SSE 长连接，应用启动时建立、关闭时释放
- 静默降级：服务不可用时返回 None，不抛异常
- 短超时：避免阻塞主请求流程
"""

import asyncio
import json
from typing import Any, Dict, Optional  # noqa: UP035

from app.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)
settings = get_settings()


class MCPClient:
    """
    基于官方 mcp SDK 的 MCP Client 封装

    支持 SSE 长连接，自动协议握手，工具动态发现。
    设计为单例，由 FastAPI lifespan 统一管理生命周期。
    """

    def __init__(self) -> None:
        self.url: str = settings.supermemory_url
        self.timeout: float = settings.supermemory_timeout
        self.enabled: bool = settings.supermemory_enabled

        # 构建 headers：优先使用 supermemory_headers，否则用 supermemory_token
        if settings.supermemory_headers:
            self.headers: Dict[str, str] = dict(settings.supermemory_headers)
        else:
            self.headers = {"token": settings.supermemory_token}

        self._session: Any = None  # ClientSession，无类型注解避免循环 import
        self._client_ctx: Any = None
        self._connected: bool = False

    async def connect(self) -> None:
        """建立 SSE 连接并完成 MCP 协议握手（应用启动时调用）"""
        if not self.enabled:
            logger.info("supermemory MCP 已禁用，跳过连接")
            return

        try:
            from mcp.client.sse import sse_client
            from mcp import ClientSession

            # 掩码显示 token（只显示前4位）
            token = self.headers.get("token", "")
            masked_token = token[:4] + "***" if len(token) > 4 else token
            logger.info(f"正在建立 MCP 连接 | url={self.url} | token={masked_token} | headers_keys={list(self.headers.keys())}")

            # 使用 wait_for 包装连接和握手过程，避免启动阻塞
            async with asyncio.timeout(self.timeout):
                self._client_ctx = sse_client(self.url, headers=self.headers)
                read, write = await self._client_ctx.__aenter__()
                self._session = ClientSession(read, write)

                # MCP 协议握手：initialize → list_tools
                logger.debug(f"MCP 开始 initialize 握手 | timeout={self.timeout}s")
                await self._session.initialize()
                tools = await self._session.list_tools()
                tool_names = [t.name for t in tools]
                self._connected = True
                logger.info(f"MCP 连接已建立 | 可用工具: {tool_names}")
        except asyncio.TimeoutError:
            logger.error(
                f"MCP 连接超时 ({self.timeout}s) | url={self.url}\n"
                f"  SSE 连接成功但 MCP 握手无响应，请检查：\n"
                f"  1. MCP Server 进程是否正常运行\n"
                f"  2. Server 端日志有无 initialize 请求记录\n"
                f"  3. nginx 是否配置了 proxy_buffering off（SSE 需要）"
            )
            self._session = None
            self._connected = False
        except Exception as e:
            logger.error(f"MCP 连接失败 | url={self.url} | error={type(e).__name__}: {e}")
            self._session = None
            self._connected = False

    async def call(self, tool_name: str, **kwargs: Any) -> Optional[Dict[str, Any]]:
        """
        调用 MCP 工具，带超时和静默降级

        Args:
            tool_name: MCP 工具名（如 add_memory、search_memory）
            **kwargs: 工具参数（如 user_id、query、content 等）

        Returns:
            dict: 工具返回结果（已解析 content）
            None: 调用失败或降级时
        """
        if not self.enabled or self._session is None:
            logger.debug(f"MCP 调用跳过 [{tool_name}] | enabled={self.enabled} | connected={self._connected}")
            return None

        try:
            result = await asyncio.wait_for(
                self._session.call_tool(tool_name, arguments=kwargs),
                timeout=self.timeout,
            )

            # 解析 CallToolResult → dict
            # result.content 是 list[TextContent | ImageContent]
            if result.content and hasattr(result.content[0], "text"):
                return json.loads(result.content[0].text)
            return {}

        except asyncio.TimeoutError:
            logger.warning(f"MCP 调用超时 [{tool_name}] | timeout={self.timeout}s")
            return None
        except Exception as e:
            logger.warning(f"MCP 调用失败 [{tool_name}] | error={type(e).__name__}: {e}")
            return None

    async def disconnect(self) -> None:
        """关闭 SSE 连接（应用关闭时调用）"""
        if self._client_ctx is not None:
            try:
                await self._client_ctx.__aexit__(None, None, None)
            except Exception:
                logger.debug("MCP 连接关闭时异常（可忽略）", exc_info=True)
            self._client_ctx = None
            self._session = None
            logger.info("MCP 连接已关闭")


# 全局单例（由 lifespan 管理生命周期）
mcp_client = MCPClient()
