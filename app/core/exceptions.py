"""
统一异常处理模块

定义应用级别的异常类和全局异常处理器，提供统一的错误响应格式。
"""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from ..core.logging import get_logger
from ..models.schemas import ApiResponse


class AppException(Exception):
    """
    应用异常基类
    
    所有业务异常都应继承此类，提供统一的错误码和错误消息格式。
    业务错误码（code）用于问题域定位，HTTP 状态码（status_code）用于响应。
    
    Attributes:
        code: 业务错误码（如 NOT_FOUND），UPPER_SNAKE_CASE 格式
        message: 用户友好的错误描述信息
        status_code: HTTP 状态码
    """
    
    def __init__(self, code: str, message: str, status_code: int = 400):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
    
    def __str__(self) -> str:
        return f"[{self.code}] {self.message}"


class AIServiceException(AppException):
    """
    AI 服务异常
    
    调用 AI Provider 生成内容时发生的错误，如 API 调用失败、超时等。
    """
    
    def __init__(self, message: str = "AI 服务调用失败"):
        super().__init__(code="AI_SERVICE_ERROR", message=message, status_code=503)


class DatabaseException(AppException):
    """
    数据库异常
    
    数据库操作失败时抛出，如连接失败、SQL 执行错误等。
    """
    
    def __init__(self, message: str = "数据库操作失败"):
        super().__init__(code="DATABASE_ERROR", message=message, status_code=500)


class NotFoundException(AppException):
    """
    资源未找到异常
    
    请求的资源不存在时抛出，如收藏记录不存在。
    """
    
    def __init__(self, message: str = "请求的资源不存在"):
        super().__init__(code="NOT_FOUND", message=message, status_code=404)


class ValidationException(AppException):
    """
    参数校验异常
    
    请求参数不合法时抛出。
    """
    
    def __init__(self, message: str = "请求参数错误"):
        super().__init__(code="VALIDATION_ERROR", message=message, status_code=400)


def register_exception_handlers(app: FastAPI) -> None:
    """
    注册全局异常处理器
    
    为 FastAPI 应用注册统一的异常处理逻辑，确保所有错误都以 ApiResponse 格式返回。
    
    Args:
        app: FastAPI 应用实例
        
    Example:
        >>> app = FastAPI()
        >>> register_exception_handlers(app)
    """
    
    # 处理应用自定义异常
    @app.exception_handler(AppException)
    async def app_exception_handler(request: Request, exc: AppException) -> JSONResponse:
        """处理 AppException 及其子类"""
        logger = get_logger("app.exceptions")
        logger.warning(f"业务异常 | code={exc.code} | message={exc.message} | path={request.url.path}")
        return JSONResponse(
            status_code=exc.status_code,
            content=ApiResponse(code=exc.status_code, message=exc.message).model_dump()
        )
        
    # 处理通用异常（兜底）
    @app.exception_handler(Exception)
    async def general_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        """处理所有未捕获的异常"""
        # 记录完整错误日志（含堆栈）
        logger = get_logger("app.exceptions")
        logger.error(f"Unhandled exception: {exc}", exc_info=True)
            
        return JSONResponse(
            status_code=500,
            content=ApiResponse(
                code=500, 
                message="服务器内部错误，请稍后重试"
            ).model_dump()
        )
