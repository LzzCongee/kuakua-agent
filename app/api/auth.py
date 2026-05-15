from fastapi import APIRouter, HTTPException
from httpx import AsyncClient, RequestError
from pydantic import BaseModel

from ..config import get_settings
from ..core.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/auth", tags=["登录认证"])


class LoginRequest(BaseModel):
    code: str


class LoginResponse(BaseModel):
    openid: str


@router.post("/login")
async def wechat_login(body: LoginRequest) -> LoginResponse:
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
    return LoginResponse(openid=data["openid"])
