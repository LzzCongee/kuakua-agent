"""
管理后台接口路由模块

提供 Prompt 管理、AB 测试管理、日志查询等管理接口。
所有接口需要 X-Admin-Key 认证。
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import get_settings
from ..core.auth import verify_admin_key
from ..core.logging import get_logger, LOG_DIR
from ..models.database import get_session
from ..models.schemas import (
    ApiResponse,
    ABTestCreate,
    ABTestResponse,
    ABTestUpdate,
    PromptResponse,
    PromptTestRequest,
    PromptTestResponse,
    PromptUpdate,
)
from ..providers.openai_compatible import OpenAICompatibleProvider
from ..services.ab_test_service import ABTestService
from ..services.prompt_service import PromptService

# 获取日志记录器
logger = get_logger(__name__)


router = APIRouter(prefix="/api/admin", tags=["管理后台"]) 

# ---------- 依赖注入类型别名 ----------
PromptServiceDep = Annotated[PromptService, Depends(lambda: PromptService())]
ABTestServiceDep = Annotated[ABTestService, Depends(lambda: ABTestService())]
SessionDep = Annotated[AsyncSession, Depends(get_session)]
AdminKeyDep = Annotated[str, Depends(verify_admin_key)]


# ==================== Prompt CRUD ====================


@router.get("/prompts", response_model=ApiResponse[list[PromptResponse]])
async def list_prompts(
    prompt_service: PromptServiceDep,
    session: SessionDep,
    _admin: AdminKeyDep,
) -> ApiResponse[list[PromptResponse]]:
    """
    列出所有 prompt 模板

    返回数据库中所有已保存的 prompt 模板列表，包含各场景的 system/user prompt 及版本信息。

    请求头：
        X-Admin-Key: 管理后台 API Key（必填）
    """
    logger.info("管理后台 | 列出所有 prompt 模板")
    prompts = await prompt_service.list_prompts(session)
    return ApiResponse(data=prompts)


@router.get("/prompts/{scene}", response_model=ApiResponse[PromptResponse])
async def get_prompt(
    scene: str,
    prompt_service: PromptServiceDep,
    session: SessionDep,
    _admin: AdminKeyDep,
) -> ApiResponse[PromptResponse]:
    """
    获取指定场景的 prompt

    Args:
        scene: 场景标识，可选值：general, career, beauty, love, daily

    请求头：
        X-Admin-Key: 管理后台 API Key（必填）
    """
    logger.info(f"管理后台 | 获取 prompt | scene={scene}")
    prompt = await prompt_service.get_prompt(scene, session)
    return ApiResponse(data=prompt)


@router.put("/prompts/{scene}", response_model=ApiResponse[PromptResponse])
async def update_prompt(
    scene: str,
    data: PromptUpdate,
    prompt_service: PromptServiceDep,
    session: SessionDep,
    _admin: AdminKeyDep,
) -> ApiResponse[PromptResponse]:
    """
    更新 prompt（热更新，无需重启服务）

    更新指定场景的 system_prompt 和 user_prompt，版本号自动递增。

    Args:
        scene: 场景标识，可选值：general, career, beauty, love, daily
        data: 更新数据，包含 system_prompt（必填）和 user_prompt（可选）

    请求头：
        X-Admin-Key: 管理后台 API Key（必填）
    """
    logger.info(f"管理后台 | 更新 prompt | scene={scene}")
    prompt = await prompt_service.update_prompt(scene, data, session)
    return ApiResponse(data=prompt)


@router.post(
    "/prompts/{scene}/test", response_model=ApiResponse[PromptTestResponse]
)
async def test_prompt(
    scene: str,
    data: PromptTestRequest,
    prompt_service: PromptServiceDep,
    session: SessionDep,
    _admin: AdminKeyDep,
) -> ApiResponse[PromptTestResponse]:
    """
    测试 prompt 效果

    使用当前激活的 prompt 模板，传入测试文本调用 AI 生成，用于验证 prompt 改动效果。

    Args:
        scene: 场景标识
        data: 测试参数，包含 test_input（测试文本）和 temperature（采样温度，0-2）

    请求头：
        X-Admin-Key: 管理后台 API Key（必填）
    """
    logger.info(f"管理后台 | 测试 prompt | scene={scene}")
    # 获取当前 prompt
    prompt_resp = await prompt_service.get_prompt(scene, session)

    # 调用 AI 生成
    settings = get_settings()
    provider = OpenAICompatibleProvider(
        api_key=settings.modelscope_api_key,
        base_url=settings.ai_base_url,
        model=settings.ai_model,
    )
    output = await provider.generate(
        prompt=data.test_input,
        system_prompt=prompt_resp.system_prompt,
        temperature=data.temperature,
        max_tokens=100,
    )

    logger.info(f"管理后台 | prompt 测试完成 | scene={scene}")
    return ApiResponse(
        data=PromptTestResponse(
            output=output,
            scene=scene,
            prompt_version=prompt_resp.version,
        )
    )


# ==================== AB Test CRUD ====================


@router.get("/ab-tests", response_model=ApiResponse[list[ABTestResponse]])
async def list_ab_tests(
    ab_test_service: ABTestServiceDep,
    session: SessionDep,
    _admin: AdminKeyDep,
) -> ApiResponse[list[ABTestResponse]]:
    """
    列出所有 AB 测试

    返回所有 AB 测试实验的配置信息，包括对照组/实验组 prompt、流量比例和状态。

    请求头：
        X-Admin-Key: 管理后台 API Key（必填）
    """
    logger.info("管理后台 | 列出所有 AB 测试")
    tests = await ab_test_service.list_ab_tests(session)
    return ApiResponse(data=tests)


@router.post("/ab-tests", response_model=ApiResponse[ABTestResponse])
async def create_ab_test(
    data: ABTestCreate,
    ab_test_service: ABTestServiceDep,
    session: SessionDep,
    _admin: AdminKeyDep,
) -> ApiResponse[ABTestResponse]:
    """
    创建 AB 测试

    创建一个新的 prompt AB 测试实验，指定对照组和实验组的 prompt ID 及流量分配比例。

    Args:
        data: 测试配置，包含 name（测试名称）、scene（场景）、prompt_a_id（对照组）、
              prompt_b_id（实验组）、traffic_ratio（实验组流量比例，0-1，默认 0.5）

    请求头：
        X-Admin-Key: 管理后台 API Key（必填）
    """
    logger.info(f"管理后台 | 创建 AB 测试 | scene={data.scene}")
    ab_test = await ab_test_service.create_ab_test(data, session)
    return ApiResponse(data=ab_test)


@router.put("/ab-tests/{ab_test_id}", response_model=ApiResponse[ABTestResponse])
async def update_ab_test(
    ab_test_id: int,
    data: ABTestUpdate,
    ab_test_service: ABTestServiceDep,
    session: SessionDep,
    _admin: AdminKeyDep,
) -> ApiResponse[ABTestResponse]:
    """
    更新 AB 测试配置

    修改运行中的 AB 测试的名称、流量比例或状态（running/stopped）。

    Args:
        ab_test_id: AB 测试 ID
        data: 更新字段（均为可选）

    请求头：
        X-Admin-Key: 管理后台 API Key（必填）
    """
    logger.info(f"管理后台 | 更新 AB 测试 | ab_test_id={ab_test_id}")
    ab_test = await ab_test_service.update_ab_test(ab_test_id, data, session)
    return ApiResponse(data=ab_test)


@router.delete("/ab-tests/{ab_test_id}", response_model=ApiResponse[None])
async def stop_ab_test(
    ab_test_id: int,
    ab_test_service: ABTestServiceDep,
    session: SessionDep,
    _admin: AdminKeyDep,
) -> ApiResponse[None]:
    """
    结束 AB 测试

    停止并删除指定的 AB 测试实验。

    Args:
        ab_test_id: AB 测试 ID

    请求头：
        X-Admin-Key: 管理后台 API Key（必填）
    """
    logger.info(f"管理后台 | 停止 AB 测试 | ab_test_id={ab_test_id}")
    await ab_test_service.delete_ab_test(ab_test_id, session)
    return ApiResponse(message="AB 测试已结束")


# ==================== 日志查询 ====================


class LogEntry(BaseModel):
    """单条日志记录"""
    timestamp: str = Field(description="日志时间")
    level: str = Field(description="日志级别")
    trace_id: str = Field(default="-", description="追踪 ID")
    logger_name: str = Field(default="", description="Logger 名称")
    message: str = Field(description="日志内容")


class LogQueryResponse(BaseModel):
    """日志查询响应"""
    total: int = Field(description="匹配的总行数")
    lines: list[LogEntry] = Field(description="日志条目列表")
    file: str = Field(description="读取的日志文件名")


# 日志行正则：2025-05-13 16:30:00 | INFO     | abc12345 | app.middleware | 请求开始 ...
_LOG_PATTERN = re.compile(
    r"^(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})\s*\|\s*"
    r"(DEBUG|INFO|WARNING|ERROR|CRITICAL)\s*\|\s*"
    r"([^\s|]+)\s*\|\s*"
    r"(?:(.+?)\s*\|\s*)?"
    r"(.*)$"
)


def _parse_log_line(line: str) -> Optional[LogEntry]:
    """将一行文本解析为 LogEntry，解析失败返回 None"""
    m = _LOG_PATTERN.match(line.strip())
    if not m:
        return None
    return LogEntry(
        timestamp=m.group(1),
        level=m.group(2),
        trace_id=m.group(3),
        logger_name=m.group(4) or "",
        message=m.group(5),
    )


@router.get("/logs", response_model=ApiResponse[LogQueryResponse])
async def query_logs(
    _admin: AdminKeyDep,
    keyword: Optional[str] = Query(default=None, description="关键词搜索（不区分大小写）"),
    level: Optional[str] = Query(
        default=None, description="日志级别过滤：DEBUG / INFO / WARNING / ERROR / CRITICAL"
    ),
    trace_id: Optional[str] = Query(default=None, description="按 trace_id 过滤"),
    tail: int = Query(default=200, ge=1, le=2000, description="读取最后 N 行"),
    page: int = Query(default=1, ge=1, description="页码"),
    page_size: int = Query(default=50, ge=1, le=200, description="每页条数"),
) -> ApiResponse[LogQueryResponse]:
    """
    查询服务日志

    从容器内的日志文件读取最近的日志，支持关键词搜索、级别过滤和分页。
    仅用于调试，生产环境建议使用 CloudBase 控制台查看完整日志。
    """
    # 确定日志文件路径
    log_file = LOG_DIR / "kuakua-agent.log"
    error_log_file = LOG_DIR / "kuakua-agent-error.log"

    # 优先读取主日志文件，不存在则读取 error 日志
    if log_file.exists():
        target_file = log_file
    elif error_log_file.exists():
        target_file = error_log_file
    else:
        return ApiResponse(
            data=LogQueryResponse(total=0, lines=[], file="未找到日志文件"),
            message="日志文件不存在，可能服务刚启动尚未写入日志",
        )

    # 读取文件最后 N 行
    try:
        with open(target_file, "r", encoding="utf-8", errors="replace") as f:
            # 高效读取尾部：先 seek 到文件末尾附近
            lines = f.readlines()[-tail:]
    except Exception as e:
        logger.error(f"读取日志文件失败: {e}")
        return ApiResponse(
            data=LogQueryResponse(total=0, lines=[], file=str(target_file)),
            message=f"读取日志文件失败: {e}",
        )

    # 解析并过滤
    entries: list[LogEntry] = []
    for line in lines:
        entry = _parse_log_line(line)
        if entry is None:
            # 无法解析的行，作为上一条日志的续行或跳过
            continue

        # 级别过滤
        if level and entry.level != level.upper():
            continue

        # trace_id 过滤
        if trace_id and entry.trace_id != trace_id:
            continue

        # 关键词过滤
        if keyword and keyword.lower() not in entry.message.lower():
            continue

        entries.append(entry)

    # 分页
    total = len(entries)
    start = (page - 1) * page_size
    end = start + page_size
    page_entries = entries[start:end]

    return ApiResponse(
        data=LogQueryResponse(
            total=total,
            lines=page_entries,
            file=str(target_file),
        )
    )
