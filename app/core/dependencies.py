"""
用户身份依赖注入模块

提供 FastAPI 依赖函数，用于从请求头获取用户身份信息。

设计原则：
- 统一通过 X-User-ID 请求头获取用户标识
- 提供默认值支持匿名用户
- 与日志系统集成，支持 trace_id 追踪
"""

from typing import Annotated, Optional, TYPE_CHECKING

from fastapi import Depends, Header, Request

from app.core.logging import get_logger

logger = get_logger(__name__)


async def get_user_id(
    request: Request,
    x_user_id: Annotated[
        Optional[str],
        Header(
            description="用户标识，用于数据隔离和个性化服务"
        )
    ] = "anonymous"
) -> str:
    """
    获取用户 ID（从 X-User-ID 请求头）
    
    此依赖函数从 HTTP 请求头中提取用户标识。
    如果请求头不存在或为空，返回 "anonymous"。
    
    推荐的前端实现：
    ```javascript
    // 小程序端：首次打开时生成 UUID 并缓存
    const userId = wx.getStorageSync('user_id') || uuid.v4();
    wx.setStorageSync('user_id', userId);
    
    // 请求时带上用户标识
    wx.request({
        url: '/api/chat',
        header: {
            'X-User-ID': userId,
            'X-Trace-ID': traceId  // 可选，用于请求追踪
        }
    });
    ```
    
    Args:
        request: FastAPI 请求对象（用于日志记录）
        x_user_id: 从请求头 X-User-ID 获取的用户标识
        
    Returns:
        str: 用户标识，未提供时返回 "anonymous"
        
    Example:
        ```python
        @app.get("/api/example")
        async def example(user_id: str = Depends(get_user_id)):
            logger.info(f"处理用户 {user_id} 的请求")
            return {"user_id": user_id}
        ```
    """
    # 获取 trace_id 用于日志关联
    from app.core.logging import get_trace_id
    trace_id = get_trace_id()
    
    # 如果是匿名用户，记录警告（可选）
    if x_user_id == "anonymous":
        logger.debug(f"匿名用户请求 | trace_id={trace_id} | path={request.url.path}")
    
    return x_user_id or "anonymous"


# 类型别名，方便在接口中使用
UserID = Annotated[str, Depends(get_user_id)]


def get_optional_user_id(
    x_user_id: Annotated[
        Optional[str],
        Header(description="用户标识（可选）")
    ] = None
) -> Optional[str]:
    """
    获取可选的用户 ID
    
    与 get_user_id 不同，此函数在未提供用户 ID 时返回 None，
    而不是默认值 "anonymous"。
    适用于某些可选用户身份的接口。
    
    Args:
        x_user_id: 从请求头 X-User-ID 获取的用户标识
        
    Returns:
        Optional[str]: 用户标识，未提供时返回 None
    """
    return x_user_id


# 类型别名
OptionalUserID = Annotated[Optional[str], Depends(get_optional_user_id)]


async def get_user_id_from_header(
    x_user_id: Annotated[
        Optional[str],
        Header(description="用户标识，用于数据隔离")
    ] = "anonymous"
) -> str:
    """从请求头获取用户 ID（兼容旧代码的便捷函数）"""
    return x_user_id or "anonymous"


# 类型别名，方便在接口中使用
HeaderUserID = Annotated[str, Depends(get_user_id_from_header)]
