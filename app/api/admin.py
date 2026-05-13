"""
管理后台接口路由模块

提供 Prompt 管理、AB 测试管理等管理接口。
所有接口需要 X-Admin-Key 认证。
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import get_settings
from ..core.auth import verify_admin_key
from ..core.logging import get_logger
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
from ..providers.qwen import QwenProvider
from ..services.ab_test_service import ABTestService
from ..services.prompt_service import PromptService

# 获取日志记录器
logger = get_logger(__name__)


router = APIRouter(prefix="/api/admin", tags=["管理后台"]) 

# ---------- 依赖注入类型别名 ----------
type PromptServiceDep = Annotated[PromptService, Depends(lambda: PromptService())]
type ABTestServiceDep = Annotated[ABTestService, Depends(lambda: ABTestService())]
type SessionDep = Annotated[AsyncSession, Depends(get_session)]
type AdminKeyDep = Annotated[str, Depends(verify_admin_key)]


# ==================== Prompt CRUD ====================


@router.get("/prompts", response_model=ApiResponse[list[PromptResponse]])
async def list_prompts(
    prompt_service: PromptServiceDep,
    session: SessionDep,
    _admin: AdminKeyDep,
) -> ApiResponse[list[PromptResponse]]:
    """列出所有 prompt 模板"""
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
    """获取指定场景的 prompt"""
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
    """更新 prompt（热更新，无需重启服务）"""
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
    """测试 prompt 效果"""
    logger.info(f"管理后台 | 测试 prompt | scene={scene}")
    # 获取当前 prompt
    prompt_resp = await prompt_service.get_prompt(scene, session)

    # 调用 AI 生成
    settings = get_settings()
    provider = QwenProvider(
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
    """列出所有 AB 测试"""
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
    """创建 AB 测试"""
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
    """更新 AB 测试配置"""
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
    """结束 AB 测试"""
    logger.info(f"管理后台 | 停止 AB 测试 | ab_test_id={ab_test_id}")
    await ab_test_service.delete_ab_test(ab_test_id, session)
    return ApiResponse(message="AB 测试已结束")
