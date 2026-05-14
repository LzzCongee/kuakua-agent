"""
记忆管理 API 路由

提供记忆相关的 RESTful 接口：
- 用户偏好管理（GET/PUT /api/memory/profile）
- 会话管理（GET/POST /api/memory/sessions）
- 里程碑管理（GET/POST /api/memory/milestones/）
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.dependencies import HeaderUserID
from ..core.logging import get_logger
from ..models.database import get_session
from ..models.schemas import (
    ApiResponse,
    MemorySummary,
    MilestoneCreate,
    MilestoneResponse,
    SessionCreate,
    SessionResponse,
    SessionUpdate,
    UserProfileResponse,
    UserProfileUpdate,
)
from ..services.memory_service import MemoryService

# 获取日志记录器
logger = get_logger(__name__)

router = APIRouter(prefix="/api/memory", tags=["记忆管理"])

# ---------- 依赖注入类型别名 ----------

AdminSessionDep = Annotated[AsyncSession, Depends(get_session)]


def _get_memory_service(session: AdminSessionDep) -> MemoryService:
    """获取 MemoryService 实例（依赖注入工厂函数）"""
    return MemoryService(session)


MemoryServiceDep = Annotated[MemoryService, Depends(_get_memory_service)]


# ---------- 辅助函数 ----------

def _parse_json_list(value: str | None) -> list[Any]:
    """安全解析 JSON 字符串为 list，失败返回空列表"""
    if not value:
        return []
    try:
        result: list[Any] = json.loads(value)
        return result
    except json.JSONDecodeError:
        return []


def _parse_json_str_list(value: str | None) -> list[str]:
    """安全解析 JSON 字符串为 list[str]，失败返回空列表"""
    if not value:
        return []
    try:
        result: list[str] = json.loads(value)
        return result
    except json.JSONDecodeError:
        return []


def _profile_to_response(
    id: int,
    user_id: str,
    prefer_scene: str | None,
    prefer_style: str | None,
    user_tags_raw: str | None,
    avoid_words_raw: str | None,
    last_emotion: str | None,
    conversation_count: int | None,
    favorite_count: int | None,
    last_active: datetime | None,
) -> UserProfileResponse:
    """将 UserProfile ORM 属性映射为 UserProfileResponse（消除重复的 JSON 解析逻辑）"""
    return UserProfileResponse(
        id=id,
        user_id=user_id,
        prefer_scene=prefer_scene,
        prefer_style=prefer_style,
        user_tags=_parse_json_str_list(user_tags_raw),
        avoid_words=_parse_json_str_list(avoid_words_raw),
        last_emotion=last_emotion,
        conversation_count=conversation_count or 0,
        favorite_count=favorite_count or 0,
        last_active=last_active,
    )


# ==================== 用户偏好相关接口 ====================


@router.get("/profile", response_model=ApiResponse[UserProfileResponse])
async def get_user_profile(
    service: MemoryServiceDep,
    _session: AdminSessionDep,
    user_id: HeaderUserID,
) -> ApiResponse[UserProfileResponse]:
    """
    获取用户偏好记录
    
    Returns:
        用户偏好信息，如果不存在则返回空数据结构
    """
    logger.info(f"获取用户偏好 | user_id={user_id}")
    profile = await service.get_user_profile(user_id)
    
    if not profile:
        logger.info(f"用户偏好不存在 | user_id={user_id}")
        return ApiResponse(
            data=UserProfileResponse(
                id=0,
                user_id=user_id,
                user_tags=[],
                avoid_words=[]
            )
        )
    
    logger.info(f"用户偏好获取完成 | user_id={user_id}")
    return ApiResponse(
        data=_profile_to_response(
            id=profile.id,
            user_id=profile.user_id,
            prefer_scene=profile.prefer_scene,
            prefer_style=profile.prefer_style,
            user_tags_raw=profile.user_tags,
            avoid_words_raw=profile.avoid_words,
            last_emotion=profile.last_emotion,
            conversation_count=profile.conversation_count,
            favorite_count=profile.favorite_count,
            last_active=profile.last_active,
        )
    )


@router.put("/profile", response_model=ApiResponse[UserProfileResponse])
async def update_user_profile(
    data: UserProfileUpdate,
    service: MemoryServiceDep,
    _session: AdminSessionDep,
    user_id: HeaderUserID,
) -> ApiResponse[UserProfileResponse]:
    """
    更新用户偏好
    
    Args:
        data: 偏好更新数据
        
    Returns:
        更新后的用户偏好
    """
    logger.info(f"更新用户偏好 | user_id={user_id}")
    profile = await service.update_user_profile(user_id, data)
    
    logger.info(f"用户偏好更新完成 | user_id={user_id}")
    return ApiResponse(
        data=_profile_to_response(
            id=profile.id,
            user_id=profile.user_id,
            prefer_scene=profile.prefer_scene,
            prefer_style=profile.prefer_style,
            user_tags_raw=profile.user_tags,
            avoid_words_raw=profile.avoid_words,
            last_emotion=profile.last_emotion,
            conversation_count=profile.conversation_count,
            favorite_count=profile.favorite_count,
            last_active=profile.last_active,
        )
    )


@router.get("/summary", response_model=ApiResponse[MemorySummary])
async def get_memory_summary(
    service: MemoryServiceDep,
    session_id: Annotated[str | None, Query(description="可选的当前会话ID")] = None,
    user_id: HeaderUserID = "anonymous",
) -> ApiResponse[MemorySummary]:
    """
    获取用户记忆汇总（用于注入 Prompt）
    
    Args:
        session_id: 可选的当前会话ID
        
    Returns:
        完整的记忆汇总信息
    """
    logger.info(f"获取用户记忆汇总 | user_id={user_id} | session_id={session_id}")
    summary = await service.get_memory_summary(user_id, session_id)
    logger.info(f"用户记忆汇总获取完成 | user_id={user_id}")
    return ApiResponse(data=summary)


# ==================== 会话相关接口 ====================


@router.get("/sessions", response_model=ApiResponse[list[SessionResponse]])
async def get_user_sessions(
    service: MemoryServiceDep,
    limit: int = 5,
    user_id: HeaderUserID = "anonymous",
) -> ApiResponse[list[SessionResponse]]:
    """
    获取用户的会话历史（列表，不含消息详情）

    Args:
        limit: 返回数量限制

    Returns:
        会话列表（message_count 用于前端展示计数，messages 为空）
    """
    logger.info(f"获取用户会话历史 | user_id={user_id} | limit={limit}")
    sessions = await service.get_recent_sessions(user_id, limit)

    results = [
        SessionResponse(
            id=s.id,
            session_id=s.session_id,
            user_id=s.user_id,
            scene=s.scene,
            message_count=s.message_count or 0,
            last_message_at=s.last_message_at,
            messages=[],  # 列表接口不返回消息详情，前端点击展开时调用详情接口
            created_at=s.created_at,
            updated_at=s.updated_at,
        )
        for s in sessions
    ]

    logger.info(f"用户会话历史获取完成 | user_id={user_id} | count={len(results)}")
    return ApiResponse(data=results)


@router.post("/sessions", response_model=ApiResponse[SessionResponse])
async def create_or_update_session(
    data: SessionCreate,
    service: MemoryServiceDep,
    user_id: HeaderUserID = "anonymous",
) -> ApiResponse[SessionResponse]:
    """
    创建或更新会话

    Args:
        data: 会话创建数据

    Returns:
        创建/更新的会话信息
    """
    session = await service.get_or_create_session(
        user_id=user_id or data.user_id,
        session_id=data.session_id,
        scene=data.scene
    )

    logger.info(f"会话创建/更新完成 | user_id={user_id} | session_id={data.session_id}")

    return ApiResponse(
        data=SessionResponse(
            id=session.id,
            session_id=session.session_id,
            user_id=session.user_id,
            scene=session.scene,
            message_count=session.message_count or 0,
            last_message_at=session.last_message_at,
            messages=[],
            created_at=session.created_at,
            updated_at=session.updated_at
        )
    )


@router.put("/sessions/{session_id}", response_model=ApiResponse[SessionResponse])
async def update_session(
    session_id: str,
    data: SessionUpdate,
    service: MemoryServiceDep,
) -> ApiResponse[SessionResponse]:
    """
    更新会话（仅支持更新 scene）

    Args:
        session_id: 会话ID
        data: 更新数据

    Returns:
        更新后的会话信息
    """
    logger.info(f"更新会话 | session_id={session_id}")

    session = await service.get_session(session_id)

    if not session:
        logger.warning(f"会话不存在 | session_id={session_id}")
        raise HTTPException(status_code=404, detail="会话不存在")

    if data.scene:
        session.scene = data.scene
        await service.session.flush()

    logger.info(f"会话更新完成 | session_id={session_id}")

    return ApiResponse(
        data=SessionResponse(
            id=session.id,
            session_id=session.session_id,
            user_id=session.user_id,
            scene=session.scene,
            message_count=session.message_count or 0,
            last_message_at=session.last_message_at,
            messages=[],
            created_at=session.created_at,
            updated_at=session.updated_at
        )
    )


@router.get("/sessions/detail/{session_id}", response_model=ApiResponse[SessionResponse])
async def get_session_by_id(
    session_id: str,
    service: MemoryServiceDep,
) -> ApiResponse[SessionResponse]:
    """
    根据 session_id 获取会话详情（含消息列表）

    Args:
        session_id: 会话ID

    Returns:
        会话详细信息（包含完整消息列表）
    """
    session = await service.get_session(session_id)

    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")

    # 获取会话的消息
    messages = await service.get_session_messages(session_id, limit=50)
    message_list = [
        {
            "role": msg.role,
            "content": msg.content,
            "timestamp": msg.created_at.isoformat() if msg.created_at else None,
        }
        for msg in messages
    ]

    return ApiResponse(
        data=SessionResponse(
            id=session.id,
            session_id=session.session_id,
            user_id=session.user_id,
            scene=session.scene,
            message_count=session.message_count or 0,
            last_message_at=session.last_message_at,
            messages=message_list,
            created_at=session.created_at,
            updated_at=session.updated_at
        )
    )


# ==================== 里程碑相关接口 ====================


@router.get("/milestones", response_model=ApiResponse[list[MilestoneResponse]])
async def get_user_milestones(
    service: MemoryServiceDep,
    limit: int = 10,
    user_id: HeaderUserID = "anonymous",
) -> ApiResponse[list[MilestoneResponse]]:
    """
    获取用户的高光里程碑
    
    Args:
        limit: 返回数量限制
        
    Returns:
        里程碑列表
    """
    milestones = await service.get_milestones(user_id, limit)
    
    results = [
        MilestoneResponse(
            id=m.id,
            user_id=m.user_id,
            content=m.content,
            source=m.source,
            importance=m.importance,
            is_achieved=m.is_achieved,
            created_at=m.created_at,
        )
        for m in milestones
    ]
    
    return ApiResponse(data=results)


@router.post("/milestones", response_model=ApiResponse[MilestoneResponse])
async def create_milestone(
    data: MilestoneCreate,
    service: MemoryServiceDep,
    user_id: HeaderUserID = "anonymous",
) -> ApiResponse[MilestoneResponse]:
    """
    添加高光里程碑
    
    Args:
        data: 里程碑数据
        
    Returns:
        创建的里程碑信息
    """
    milestone = await service.add_milestone(
        MilestoneCreate(
            user_id=user_id or data.user_id,
            content=data.content,
            source=data.source,
            importance=data.importance,
        )
    )
    
    return ApiResponse(
        data=MilestoneResponse(
            id=milestone.id,
            user_id=milestone.user_id,
            content=milestone.content,
            source=milestone.source,
            importance=milestone.importance,
            is_achieved=milestone.is_achieved,
            created_at=milestone.created_at,
        )
    )


@router.post("/milestones/extract", response_model=ApiResponse[MilestoneResponse | None])
async def extract_milestone(
    content: str,
    service: MemoryServiceDep,
    user_id: HeaderUserID = "anonymous",
) -> ApiResponse[MilestoneResponse | None]:
    """
    从对话内容中提取并添加里程碑
    
    Args:
        content: 对话内容
        
    Returns:
        如果提取到成就则返回创建的里程碑，否则返回 null
    """
    milestone = await service.extract_and_add_milestone(user_id, content)
    
    if not milestone:
        return ApiResponse(data=None, message="未检测到成就内容")
    
    return ApiResponse(
        data=MilestoneResponse(
            id=milestone.id,
            user_id=milestone.user_id,
            content=milestone.content,
            source=milestone.source,
            importance=milestone.importance,
            is_achieved=milestone.is_achieved,
            created_at=milestone.created_at,
        ),
        message="成功提取里程碑"
    )


# ==================== 管理接口 ====================


@router.post("/cleanup", response_model=ApiResponse[int])
async def cleanup_expired_sessions(
    service: MemoryServiceDep,
    hours: int = 2,
) -> ApiResponse[int]:
    """
    清理过期的会话记录
    
    Args:
        hours: 过期小时数，默认 2 小时
        
    Returns:
        删除的记录数
    """
    count = await service.cleanup_expired_sessions(hours)
    return ApiResponse(data=count, message=f"清理了 {count} 条过期会话")
