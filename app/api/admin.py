"""
管理后台接口路由模块

提供日志查询等管理接口。
所有接口需要 X-Admin-Key 认证。

历史:本文件曾包含 Prompt CRUD 和 AB Test 管理端点,2026-06 随
PromptService / ABTestService 一并下线(无生产流量)。如需重启用,
需重新评估路由键(原按 scene 路由,现已废弃)。
"""

from __future__ import annotations

import re
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from ..core.auth import verify_admin_key
from ..core.logging import LOG_DIR, get_logger
from ..models.schemas import ApiResponse

logger = get_logger(__name__)


router = APIRouter(prefix="/api/admin", tags=["管理后台"])

AdminKeyDep = Annotated[str, Depends(verify_admin_key)]


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
