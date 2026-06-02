"""认证 API 路由

提供注册、登录、微信小程序登录等功能。

注册/登录流程：
- 前端 POST /api/auth/register 或 /api/auth/login 获取 user_id
- 后续所有请求通过 X-User-ID 头携带 user_id 进行鉴权
"""

from typing import Annotated

import bcrypt
from fastapi import APIRouter, Depends, HTTPException
from httpx import AsyncClient, RequestError
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import get_settings
from ..core.logging import get_logger
from ..models.database import get_session
from ..models.models import User
from ..models.schemas import ApiResponse, AuthResponse, LoginRequest, RegisterRequest

logger = get_logger(__name__)

router = APIRouter(prefix="/api", tags=["登录认证"])

# Session 依赖注入
SessionDep = Annotated[AsyncSession, Depends(get_session)]


def hash_password(password: str) -> str:
    """使用 bcrypt 哈希密码"""
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, hashed: str) -> bool:
    """验证密码是否匹配"""
    return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))


# ==================== 账号密码注册/登录 ====================


@router.post("/auth/register", response_model=ApiResponse[AuthResponse])
async def register(body: RegisterRequest, db: SessionDep):
    """注册新用户"""
    # bcrypt 限制密码不能超过 72 字节
    password_bytes = body.password.encode("utf-8")
    if len(password_bytes) > 72:
        return ApiResponse(code=400, message="密码过长，请使用不超过72字节的密码", data=None)

    # 检查用户名是否已存在
    result = await db.execute(select(User).where(User.username == body.username))
    if result.scalar_one_or_none() is not None:
        return ApiResponse(code=400, message="用户名已被注册", data=None)

    # 创建用户
    user = User(
        username=body.username,
        password_hash=hash_password(body.password),
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    logger.info(f"用户注册成功: username={user.username} user_id={user.id}")
    return ApiResponse(
        data=AuthResponse(user_id=user.id, username=user.username),
    )


@router.post("/auth/login", response_model=ApiResponse[AuthResponse])
async def login(body: LoginRequest, db: SessionDep):
    """账号密码登录"""
    result = await db.execute(select(User).where(User.username == body.username))
    user = result.scalar_one_or_none()

    if user is None:
        return ApiResponse(code=400, message="用户名或密码错误", data=None)

    if not verify_password(body.password, user.password_hash):
        return ApiResponse(code=400, message="用户名或密码错误", data=None)

    logger.info(f"用户登录成功: username={user.username} user_id={user.id}")
    return ApiResponse(
        data=AuthResponse(user_id=user.id, username=user.username),
    )


# ==================== 微信小程序登录（保留） ====================


class WechatLoginRequest(BaseModel):
    code: str


class WechatLoginResponse(BaseModel):
    openid: str


@router.post("/login", response_model=WechatLoginResponse)
async def wechat_login(body: WechatLoginRequest):
    """微信小程序登录 — 用 code 换取 openid"""
    settings = get_settings()
    try:
        async with AsyncClient(timeout=10) as client:
            resp = await client.get(
                "https://api.weixin.qq.com/sns/jscode2session",
                params={
                    "appid": settings.wechat_app_id,
                    "secret": settings.wechat_app_secret,
                    "js_code": body.code,
                    "grant_type": "authorization_code",
                },
            )
        data = resp.json()
    except RequestError as e:
        logger.error(f"微信 API 调用失败: {e}")
        raise HTTPException(status_code=502, detail="微信登录服务不可用") from e

    if "openid" not in data:
        errcode = data.get("errcode", -1)
        logger.warning(f"微信登录失败: code={errcode} msg={data.get('errmsg')}")
        raise HTTPException(status_code=400, detail=f"微信登录失败({errcode})")

    logger.info(f"微信登录成功: openid={data['openid']}")
    return WechatLoginResponse(openid=data["openid"])
