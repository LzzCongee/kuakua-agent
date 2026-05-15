"""
交互式夸夸接口路由模块

提供基于文字和图片的多模态夸夸生成 REST API 接口
支持普通请求-响应和 SSE 流式输出两种模式

请求头说明：
- X-User-ID: 用户标识（必填，用于数据隔离和个性化服务）
- X-Trace-ID: 请求追踪 ID（可选，用于日志关联）
"""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import AsyncGenerator
from datetime import datetime, timezone
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sse_starlette.sse import EventSourceResponse

from ..config import get_settings
from ..core.dependencies import HeaderUserID
from ..core.logging import get_logger
from ..core.mcp_client import mcp_client
from ..models.database import get_session
from ..models.schemas import (
    ApiResponse,
    ChatDebugInfo,
    ChatRequest,
    ChatResponse,
    MemorySummary,
    PromptContent,
    UserProfileUpdate,
)
import uuid
from ..prompts.templates import get_chat_prompt
from ..providers.openai_compatible import OpenAICompatibleProvider
from ..services.ab_test_service import ABTestService
from ..services.chat_service import ChatService
from ..services.memory_extractor import MemoryExtractor
from ..services.memory_service import MemoryService
from ..services.prompt_service import PromptService

# 获取日志记录器
logger = get_logger(__name__)


# 创建路由实例
router: APIRouter = APIRouter(prefix="/api/chat", tags=["交互式夸夸"])


class MCPTracker:
    """MCP 调用追踪器，包装 mcp_client 记录每次调用的详情"""

    def __init__(self, client: Any) -> None:
        self._client = client
        self.calls: list[dict[str, Any]] = []

    async def call(self, tool_name: str, **kwargs: Any) -> Any:
        start = time.monotonic()
        result = await self._client.call(tool_name, **kwargs)
        duration_ms = round((time.monotonic() - start) * 1000)

        # 构建参数摘要
        args_summary_parts: list[str] = []
        for k, v in kwargs.items():
            if isinstance(v, str) and len(v) > 60:
                args_summary_parts.append(f"{k}={v[:60]}...")
            elif isinstance(v, dict):
                args_summary_parts.append(f"{k}={{...}}")
            else:
                args_summary_parts.append(f"{k}={v}")
        args_summary = ", ".join(args_summary_parts)

        # 构建结果摘要
        if result is None:
            result_summary = "null (降级/失败)"
        elif isinstance(result, dict):
            keys = list(result.keys())
            result_summary = f"dict keys={keys}"
        else:
            result_summary = str(result)[:100]

        self.calls.append({
            "tool": tool_name,
            "args_summary": args_summary,
            "result_summary": result_summary,
            "success": result is not None,
            "duration_ms": duration_ms,
        })
        return result

# ---------- 依赖注入类型别名 ----------
SessionDep = Annotated[AsyncSession, Depends(get_session)]


def get_chat_service() -> ChatService:
    """获取 ChatService 实例（依赖注入工厂函数）"""
    settings = get_settings()
    provider = OpenAICompatibleProvider.from_config(settings.ai_chat)
    return ChatService(
        provider=provider,
        vision_config=settings.ai_vision
    )


ChatServiceDep = Annotated[ChatService, Depends(get_chat_service)]


@router.post("", response_model=ApiResponse[ChatResponse])
async def chat(
    request: ChatRequest,
    service: ChatServiceDep,
    session: SessionDep,
    user_id: HeaderUserID,
    session_id: Annotated[str, Query(description="会话ID，用于追踪上下文")] = "",
    debug: Annotated[bool, Query(description="是否返回调试信息")] = False,
) -> ApiResponse[ChatResponse]:
    """
    交互式夸夸接口（请求-响应模式）

    接收用户发送的文字和/或图片，生成个性化的夸赞文案。
    支持记忆注入，根据用户偏好生成千人千面的夸夸。

    请求头：
        X-User-ID: 用户标识（必填）
        X-Trace-ID: 请求追踪 ID（可选）
    """
    logger.info(f"收到夸夸请求 | user_id={user_id} | session_id={session_id} | scene={request.scene}")
    logger.debug(f"用户输入详情 | user_id={user_id} | text={request.text[:100] if request.text else 'None'} | has_image={bool(request.image)}")

    if not session_id:
        session_id = f"session_{user_id}"

    # 判断输入类型
    has_text = bool(request.text and request.text.strip())
    has_image = bool(request.image and request.image.strip())
    if has_text and has_image:
        input_type = "mixed"
    elif has_image:
        input_type = "image_only"
    else:
        input_type = "text_only"

    # 尝试从 AB 测试获取 prompt
    prompt_override = await _try_get_ab_test_prompt(
        request.scene, user_id, session
    )
    prompt_source = "ab_test" if prompt_override else None
    logger.debug(f"AB测试结果 | user_id={user_id} | has_override={prompt_override is not None}")

    # 调试模式：提前创建 MCPTracker，跟踪整个请求生命周期的 MCP 调用
    tracker: MCPTracker | None = MCPTracker(mcp_client) if debug else None

    # 获取用户记忆汇总
    memory_summary = await _get_user_memory(user_id, session_id, session, request.text or "", mcp=tracker)
    if memory_summary:
        logger.debug(f"记忆注入详情 | user_id={user_id} | prefer_scene={memory_summary.prefer_scene} | prefer_style={memory_summary.prefer_style} | tags={memory_summary.user_tags} | emotion={memory_summary.last_emotion} | milestones_count={len(memory_summary.milestones)} | semantic_count={len(memory_summary.semantic_memories)}")
    else:
        logger.debug(f"无记忆注入 | user_id={user_id}")

    # 调试模式：捕获最终 system prompt
    debug_info: ChatDebugInfo | None = None
    if debug:
        if prompt_override:
            system_prompt = prompt_override["system"]
        else:
            db_prompt = await _try_get_db_prompt(request.scene, input_type, session)
            if db_prompt:
                system_prompt = db_prompt["system"]
                prompt_source = prompt_source or "db"
            else:
                prompt_template = get_chat_prompt(input_type)
                system_prompt = prompt_template["system"]
                prompt_source = prompt_source or "template"

        if memory_summary:
            system_prompt = _inject_memory_to_prompt(system_prompt, memory_summary)

        user_message = request.text or ""
        if has_image:
            user_message += " [含图片输入]"

        debug_info = ChatDebugInfo(
            system_prompt=system_prompt,
            user_message=user_message,
            prompt_source=prompt_source or "template",
            input_type=input_type,
            memory_summary=memory_summary.model_dump() if memory_summary else None,
            mcp_connected=mcp_client.is_connected,
            mcp_calls=[],
            extraction=None,
        )

    try:
        response = await service.chat(
            request,
            prompt_override=prompt_override,
            memory_summary=memory_summary
        )
    except Exception as e:
        if debug and debug_info:
            # 调试模式下，即使 AI 调用失败也返回已收集的调试信息
            logger.warning(f"AI调用失败(调试模式) | user_id={user_id} | error={e}")
            error_response = ChatResponse(
                content=f"[AI 调用失败] {e}",
                scene=request.scene,
                has_image=has_image,
            )
            error_response.debug = debug_info
            return ApiResponse(code=500, message=str(e), data=error_response)
        raise

    if debug:
        # 调试模式：同步执行后台任务，捕获 MCP 调用和记忆提取结果
        assert debug_info is not None
        await _update_session_after_chat_with_debug(
            user_id, session_id, request, response, debug_info, tracker
        )
        response.debug = debug_info
    else:
        # 更新会话记录（后台任务，不阻塞响应）
        task = asyncio.create_task(_update_session_after_chat_bg(user_id, session_id, request, response))
        task.add_done_callback(_handle_task_exception)

    logger.info(f"夸夸生成完成 | user_id={user_id} | response_length={len(response.content)}")
    logger.debug(f"AI响应内容 | user_id={user_id} | content={response.content[:200]}")

    return ApiResponse(data=response)


@router.post("/stream")
async def chat_stream(
    request: ChatRequest,
    service: ChatServiceDep,
    session: SessionDep,
    user_id: HeaderUserID,
    session_id: Annotated[str, Query(description="会话ID，用于追踪上下文")] = "",
    debug: Annotated[bool, Query(description="是否返回调试信息")] = False,
) -> EventSourceResponse:
    """
    交互式夸夸流式接口（SSE 模式）

    接收用户发送的文字，以 Server-Sent Events 方式流式输出夸赞文案。
    前端可使用 EventSource 或 fetch + ReadableStream 接收。

    请求头：
        X-User-ID: 用户标识（必填）
        X-Trace-ID: 请求追踪 ID（可选）
    """
    logger.info(f"收到夸夸流式请求 | user_id={user_id} | session_id={session_id} | scene={request.scene}")
    logger.debug(f"用户输入详情(流式) | user_id={user_id} | text={request.text[:100] if request.text else 'None'} | has_image={bool(request.image)}")

    if not session_id:
        session_id = f"session_{user_id}"

    settings = get_settings()

    # 判断输入类型
    input_type: Literal["text_only", "image_only", "mixed"]
    has_text = bool(request.text and request.text.strip())
    has_image = bool(request.image and request.image.strip())

    if has_text and has_image:
        input_type = "mixed"
    elif has_image:
        input_type = "image_only"
    else:
        input_type = "text_only"

    # 获取 system prompt（优先从 AB 测试或数据库）
    prompt_override = await _try_get_ab_test_prompt(
        request.scene, user_id, session
    )
    prompt_source = "ab_test" if prompt_override else None
    logger.debug(f"AB测试结果(流式) | user_id={user_id} | has_override={prompt_override is not None}")

    # 调试模式：提前创建 MCPTracker，跟踪整个请求生命周期的 MCP 调用
    tracker: MCPTracker | None = MCPTracker(mcp_client) if debug else None

    # 获取用户记忆汇总
    memory_summary = await _get_user_memory(user_id, session_id, session, request.text or "", mcp=tracker)
    if memory_summary:
        logger.debug(f"记忆注入详情(流式) | user_id={user_id} | prefer_scene={memory_summary.prefer_scene} | prefer_style={memory_summary.prefer_style} | tags={memory_summary.user_tags} | emotion={memory_summary.last_emotion} | milestones_count={len(memory_summary.milestones)} | semantic_count={len(memory_summary.semantic_memories)}")
    else:
        logger.debug(f"无记忆注入(流式) | user_id={user_id}")

    if prompt_override:
        system_prompt = prompt_override["system"]
    else:
        # 尝试从数据库获取
        db_prompt = await _try_get_db_prompt(request.scene, input_type, session)
        if db_prompt:
            system_prompt = db_prompt["system"]
            prompt_source = prompt_source or "db"
        else:
            # 回退到硬编码模板
            prompt_template = get_chat_prompt(input_type)
            system_prompt = prompt_template["system"]
            prompt_source = prompt_source or "template"

    # 注入记忆上下文
    if memory_summary:
        system_prompt = _inject_memory_to_prompt(system_prompt, memory_summary)

    # 调试模式：构建调试信息
    debug_info: ChatDebugInfo | None = None
    if debug:
        user_message = request.text or ""
        if has_image:
            user_message += " [含图片输入]"
        debug_info = ChatDebugInfo(
            system_prompt=system_prompt,
            user_message=user_message,
            prompt_source=prompt_source or "template",
            input_type=input_type,
            memory_summary=memory_summary.model_dump() if memory_summary else None,
            mcp_connected=mcp_client.is_connected,
            mcp_calls=[],
            extraction=None,
        )

    # 多模态请求的超时秒数（视觉模型较慢，给更多时间）
    multimodal_timeout = max(settings.ai_vision.timeout, 60.0)

    async def event_generator() -> AsyncGenerator[dict[str, str], None]:
        try:
            full_content = ""
            logger.info(f"开始流式生成 | user_id={user_id} | session_id={session_id}")

            image_desc = None
            if has_image:
                # 多模态输入：视觉模型不支持流式，降级为非流式生成后一次 yield
                logger.info(f"多模态流式降级 | user_id={user_id} | input_type={input_type} | timeout={multimodal_timeout}s")
                try:
                    async with asyncio.timeout(multimodal_timeout):
                        multimodal_result = await service._generate_multimodal(
                            system_prompt=system_prompt,
                            text=request.text if has_text else None,
                            image=request.image,
                        )
                except TimeoutError:
                    logger.warning(f"多模态生成超时 | user_id={user_id} | timeout={multimodal_timeout}s")
                    yield {
                        "event": "error",
                        "data": json.dumps({"message": f"视觉模型响应超时（{multimodal_timeout}秒），请稍后重试或使用纯文字输入"}, ensure_ascii=False),
                    }
                    return

                full_content = multimodal_result["content"]
                image_desc = multimodal_result.get("image_desc")
                yield {
                    "event": "chunk",
                    "data": json.dumps({"content": full_content}, ensure_ascii=False),
                }
            else:
                async for chunk in service.provider.generate_stream(
                    prompt=request.text or "",
                    system_prompt=system_prompt,
                    temperature=0.7,
                    max_tokens=150,
                ):
                    full_content += chunk
                    yield {
                        "event": "chunk",
                        "data": json.dumps({"content": chunk}, ensure_ascii=False),
                    }

            logger.info(f"流式生成完成 | user_id={user_id} | session_id={session_id} | length={len(full_content)}")
            logger.debug(f"AI响应内容(流式) | user_id={user_id} | content={full_content[:200] if full_content else ''}")

            response = ChatResponse(content=full_content, scene=request.scene, has_image=has_image, image_desc=image_desc)

            if debug and debug_info:
                # 调试模式：同步执行后台任务，捕获 MCP 调用和记忆提取
                await _update_session_after_chat_with_debug(
                    user_id, session_id, request, response, debug_info, tracker
                )
                yield {
                    "event": "debug",
                    "data": json.dumps(
                        debug_info.model_dump(),
                        ensure_ascii=False,
                        default=str,
                    ),
                }
            else:
                task = asyncio.create_task(_update_session_after_chat_bg(user_id, session_id, request, response))
                task.add_done_callback(_handle_task_exception)

            # 发送完成事件（不含 content，避免前端重复追加）
            yield {
                "event": "done",
                "data": json.dumps(
                    {
                        "scene": request.scene,
                        "has_image": has_image,
                        "created_at": datetime.now(timezone.utc).isoformat(),
                    },
                    ensure_ascii=False,
                ),
            }
        except Exception as e:
            logger.error(f"流式生成异常 | user_id={user_id} | error={str(e)}")
            # 调试模式下，即使出错也发送已收集的调试信息
            if debug and debug_info:
                yield {
                    "event": "debug",
                    "data": json.dumps(
                        debug_info.model_dump(),
                        ensure_ascii=False,
                        default=str,
                    ),
                }
            yield {
                "event": "error",
                "data": json.dumps({"message": str(e)}, ensure_ascii=False),
            }

    return EventSourceResponse(event_generator())


async def _try_get_ab_test_prompt(
    scene: str, user_id: str, session: AsyncSession
) -> PromptContent | None:
    """尝试从 AB 测试获取 prompt"""
    try:
        ab_service = ABTestService()
        return await ab_service.get_prompt_for_user(scene, user_id, session)
    except Exception:
        logger.warning(f"AB 测试 Prompt 获取降级 | scene={scene} | user_id={user_id}", exc_info=True)
        return None


async def _try_get_db_prompt(
    scene: str, input_type: str, session: AsyncSession
) -> PromptContent | None:
    """尝试从数据库获取 prompt"""
    try:
        prompt_service = PromptService()
        return await prompt_service.get_active_prompt_content(
            scene, input_type, session
        )
    except Exception:
        logger.warning(f"数据库 Prompt 获取降级 | scene={scene} | input_type={input_type}", exc_info=True)
        return None


async def _get_user_memory(
    user_id: str, session_id: str, session: AsyncSession,
    current_query: str = "", mcp: Any = None,
) -> MemorySummary | None:
    """
    获取用户记忆汇总

    Args:
        user_id: 用户ID
        session_id: 会话ID（用于获取短期会话上下文）
        session: 数据库会话
        current_query: 用户当前输入文本（用于 MCP 语义搜索）
        mcp: MCP Client 实例（调试模式传入 MCPTracker）

    Returns:
        MemorySummary 或 None（如果获取失败）
    """
    try:
        memory_service = MemoryService(session, mcp or mcp_client)
        summary = await memory_service.get_memory_summary(user_id, session_id or None, current_query)
        if summary:
            logger.info(
                f"记忆汇总结果 | user_id={user_id} | session_id={session_id} | "
                f"recent_messages={len(summary.recent_messages)} | "
                f"semantic_memories={len(summary.semantic_memories)} | "
                f"milestones={len(summary.milestones)} | "
                f"prefer_scene={summary.prefer_scene} | tags={summary.user_tags}"
            )
        return summary
    except Exception:
        # 记忆获取失败时降级为无记忆模式，不影响核心夸夸功能
        logger.warning(f"记忆获取降级 | user_id={user_id} | session_id={session_id}", exc_info=True)
        return None


async def _update_session_after_chat(
    user_id: str,
    session_id: str,
    request: ChatRequest,
    response: ChatResponse
) -> None:
    """
    聊天结束后更新会话记录

    将用户的消息和 AI 的回复都记录到会话中，
    用于后续的上下文追踪和记忆提取。
    """
    if not session_id:
        logger.debug(f"会话持久化跳过 | session_id 为空")
        return

    # 生成 trace_id 用于追踪本次请求
    trace_id = str(uuid.uuid4())
    logger.info(f"会话持久化开始 | user_id={user_id} | session_id={session_id} | trace_id={trace_id}")

    try:
        from ..models.database import get_db

        async with get_db() as db_session:
            memory_service = MemoryService(db_session)

            # 获取或创建会话
            session_obj = await memory_service.get_or_create_session(
                user_id=user_id,
                session_id=session_id
            )
            logger.debug(f"会话对象已就绪 | user_id={user_id} | session_id={session_id}")

            # 添加用户消息（支持多模态：图片消息存储描述而非原图）
            has_image = bool(request.image and request.image.strip())
            has_text = bool(request.text and request.text.strip())

            # 判断消息类型
            message_type = "text"
            if has_image and has_text:
                message_type = "mixed"
            elif has_image:
                message_type = "image"

            # 构建用户消息内容
            user_content = request.text or ""
            if has_image and has_text and response.image_desc:
                user_content += f"\n[图片：{response.image_desc}]"
            elif has_image and not has_text:
                user_content = response.image_desc or "[图片]"

            # 存储用户消息
            await memory_service.add_message(
                session_id=session_id,
                trace_id=trace_id,
                role="user",
                content=user_content,
                message_type=message_type,
                has_image=has_image,
                image_desc=response.image_desc,
                scene=request.scene,
            )
            logger.debug(f"添加用户消息 | user_id={user_id} | trace_id={trace_id} | type={message_type}")

            # 存储 AI 回复（使用同一个 trace_id 关联）
            await memory_service.add_message(
                session_id=session_id,
                trace_id=trace_id,
                role="assistant",
                content=response.content,
                message_type="text",
                scene=request.scene,
            )
            logger.debug(f"添加AI回复 | user_id={user_id} | trace_id={trace_id}")

            await db_session.commit()
            logger.info(f"会话持久化完成 | user_id={user_id} | session_id={session_id} | trace_id={trace_id}")

            # 混合提取：情绪 + 偏好 + 里程碑（关键词兜底 + LLM 主力）
            extraction_result = None
            if request.text:
                logger.debug(f"开始混合记忆提取 | user_id={user_id} | text={request.text[:100]}")
                extractor = MemoryExtractor.from_settings()
                extraction_result = await extractor.extract(
                    user_message=request.text,
                    ai_response=response.content,
                )
                logger.info(
                    f"记忆提取完成 | user_id={user_id} | source={extraction_result.source} | "
                    f"emotion={extraction_result.emotion} | milestone={extraction_result.has_milestone} | "
                    f"tags={extraction_result.tags}"
                )

                # 写入里程碑
                if extraction_result.has_milestone and extraction_result.milestone_content:
                    from ..models.schemas import MilestoneCreate
                    milestone = await memory_service.add_milestone(MilestoneCreate(
                        user_id=user_id,
                        content=extraction_result.milestone_content,
                        source=extraction_result.source,
                        importance=extraction_result.milestone_importance,
                    ))
                    logger.info(f"里程碑已写入 | user_id={user_id} | milestone_id={milestone.id}")

                # 更新用户画像（情绪、标签、场景倾向）
                profile_update = UserProfileUpdate(
                    last_emotion=extraction_result.emotion if extraction_result.emotion != "neutral" else None,
                    user_tags=extraction_result.tags if extraction_result.tags else None,
                    prefer_scene=extraction_result.scene_hint,
                )
                if profile_update.last_emotion or profile_update.user_tags or profile_update.prefer_scene:
                    await memory_service.update_user_profile(user_id, profile_update)
                    logger.info(f"用户画像已更新 | user_id={user_id} | emotion={profile_update.last_emotion} | tags={profile_update.user_tags}")
            else:
                logger.debug(f"无文本输入，跳过记忆提取 | user_id={user_id}")

            # 保存到 supermemory 语义记忆
            logger.debug(f"开始保存语义记忆 | user_id={user_id}")
            memory_service_sm = MemoryService(db_session, mcp_client)
            await memory_service_sm.save_chat_to_supermemory(
                user_id=user_id,
                user_message=request.text or "",
                ai_response=response.content,
                scene=request.scene,
                emotion=extraction_result.emotion if extraction_result else None,
            )
            logger.debug(f"语义记忆保存完成 | user_id={user_id}")
    except Exception:
        # 后台任务失败不影响主流程，但必须记录日志
        logger.exception(f"后台更新会话失败 | user_id={user_id} | session_id={session_id} | trace_id={trace_id}")


async def _update_session_after_chat_bg(
    user_id: str,
    session_id: str,
    request: ChatRequest,
    response: ChatResponse,
) -> None:
    """后台任务包装，确保异常不会导致未处理的 task 异常"""
    await _update_session_after_chat(user_id, session_id, request, response)


async def _update_session_after_chat_with_debug(
    user_id: str,
    session_id: str,
    request: ChatRequest,
    response: ChatResponse,
    debug_info: ChatDebugInfo,
    tracker: MCPTracker,
) -> None:
    """调试模式下的会话更新：同步执行，捕获 MCP 调用和记忆提取结果"""
    if not session_id:
        return

    trace_id = str(uuid.uuid4())
    logger.info(f"会话持久化开始(调试模式) | user_id={user_id} | session_id={session_id} | trace_id={trace_id}")

    try:
        from ..models.database import get_db

        async with get_db() as db_session:
            # 复用外部传入的 tracker（已包含 search_memory 调用记录）
            memory_service = MemoryService(db_session, tracker)

            # 获取或创建会话
            session_obj = await memory_service.get_or_create_session(
                user_id=user_id,
                session_id=session_id
            )

            # 添加用户消息
            has_image = bool(request.image and request.image.strip())
            has_text = bool(request.text and request.text.strip())

            message_type = "text"
            if has_image and has_text:
                message_type = "mixed"
            elif has_image:
                message_type = "image"

            user_content = request.text or ""
            if has_image and has_text and response.image_desc:
                user_content += f"\n[图片：{response.image_desc}]"
            elif has_image and not has_text:
                user_content = response.image_desc or "[图片]"

            await memory_service.add_message(
                session_id=session_id,
                trace_id=trace_id,
                role="user",
                content=user_content,
                message_type=message_type,
                has_image=has_image,
                image_desc=response.image_desc,
                scene=request.scene,
            )

            # 存储 AI 回复
            await memory_service.add_message(
                session_id=session_id,
                trace_id=trace_id,
                role="assistant",
                content=response.content,
                message_type="text",
                scene=request.scene,
            )

            await db_session.commit()

            # 记忆提取
            extraction_result = None
            if request.text:
                extractor = MemoryExtractor.from_settings()
                extraction_result = await extractor.extract(
                    user_message=request.text,
                    ai_response=response.content,
                )

                if extraction_result.has_milestone and extraction_result.milestone_content:
                    from ..models.schemas import MilestoneCreate
                    await memory_service.add_milestone(MilestoneCreate(
                        user_id=user_id,
                        content=extraction_result.milestone_content,
                        source=extraction_result.source,
                        importance=extraction_result.milestone_importance,
                    ))

                profile_update = UserProfileUpdate(
                    last_emotion=extraction_result.emotion if extraction_result.emotion != "neutral" else None,
                    user_tags=extraction_result.tags if extraction_result.tags else None,
                    prefer_scene=extraction_result.scene_hint,
                )
                if profile_update.last_emotion or profile_update.user_tags or profile_update.prefer_scene:
                    await memory_service.update_user_profile(user_id, profile_update)

                debug_info.extraction = {
                    "source": extraction_result.source,
                    "emotion": extraction_result.emotion,
                    "tags": extraction_result.tags,
                    "has_milestone": extraction_result.has_milestone,
                    "milestone_content": extraction_result.milestone_content,
                    "milestone_importance": extraction_result.milestone_importance,
                    "scene_hint": extraction_result.scene_hint,
                }

            # 保存到 supermemory 语义记忆
            await memory_service.save_chat_to_supermemory(
                user_id=user_id,
                user_message=request.text or "",
                ai_response=response.content,
                scene=request.scene,
                emotion=extraction_result.emotion if extraction_result else None,
            )

            # 将 MCP 调用记录写入 debug_info
            debug_info.mcp_calls = tracker.calls

    except Exception:
        logger.exception(f"后台更新会话失败(调试模式) | user_id={user_id} | session_id={session_id}")


def _handle_task_exception(task: asyncio.Task[Any]) -> None:
    """处理后台任务中未捕获的异常，防止 'Task exception was never retrieved' 警告"""
    if not task.cancelled():
        try:
            exception = task.exception()
            if exception:
                logger.error(f"后台任务未捕获异常 | error={exception}")
        except asyncio.InvalidStateError:
            # 任务尚未完成
            pass


def _inject_memory_to_prompt(system_prompt: str, memory: MemorySummary) -> str:
    """
    将用户记忆注入到 system prompt（用于流式接口）
    
    Args:
        system_prompt: 原始 system prompt
        memory: 用户记忆汇总
        
    Returns:
        str: 注入记忆后的 system prompt
    """
    parts: list[str] = []
    
    # 偏好场景和风格
    if memory.prefer_scene:
        parts.append(f"- 偏好场景：{memory.prefer_scene}")
    if memory.prefer_style:
        parts.append(f"- 喜欢风格：{memory.prefer_style}")
    
    # 用户标签
    if memory.user_tags:
        tags_str = ", ".join(memory.user_tags[:5])
        parts.append(f"- 用户标签：{tags_str}")
    
    # 最近情绪
    if memory.last_emotion:
        parts.append(f"- 当前情绪：{memory.last_emotion}")
    
    # 最近对话（用于保持上下文连贯，按完整轮次拼接）
    if memory.recent_messages:
        from datetime import datetime
        msg_list: list[str] = []
        msgs = memory.recent_messages
        # 找最近一条 assistant 消息的位置
        last_assistant_idx = None
        for i in range(len(msgs) - 1, -1, -1):
            if msgs[i].get("role") == "assistant":
                last_assistant_idx = i
                break
        if last_assistant_idx is not None:
            start = max(0, last_assistant_idx - 1)
            # 时间戳只取 user 消息的，放在整轮对话开头
            first_msg = msgs[start]
            ts = first_msg.get("timestamp", "")
            time_str = ""
            if ts:
                try:
                    dt = datetime.fromisoformat(ts)
                    time_str = f"({dt.strftime('%H:%M')}) "
                except (ValueError, TypeError):
                    pass
            for idx, msg in enumerate(msgs[start:last_assistant_idx + 1]):
                role = "用户" if msg.get("role") == "user" else "夸夸"
                content = (msg.get("content") or "")[:80]
                # 时间戳只加在第一句前面
                prefix = time_str if idx == 0 else ""
                msg_list.append(f"{prefix}{role}：{content}")
        if msg_list:
            parts.append(f"- 最近对话：{' | '.join(msg_list)}")
    
    # 高光里程碑（用于夸得真诚）
    if memory.milestones:
        milestones_str = "; ".join(memory.milestones[:3])
        parts.append(f"- 高光时刻：{milestones_str}")

    # 语义记忆（来自 supermemory）
    if memory.semantic_memories:
        semantic_str = "; ".join(memory.semantic_memories[:2])
        parts.append(f"- 相关记忆：{semantic_str}")

    if not parts:
        return system_prompt

    memory_block = "\n".join(parts)
    logger.debug(f"Prompt 记忆注入(流式) | 内容预览: {memory_block[:300]}")
    return f"{system_prompt}\n\n【用户个性化信息】（请结合以下信息生成更贴合用户的夸夸）\n{memory_block}"
