"""
统一异常处理模块

定义应用级别的异常类和全局异常处理器，提供统一的错误响应格式。
"""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.models.schemas import ApiResponse


class AppException(Exception):
    """
    应用异常基类
    
    所有业务异常都应继承此类，提供统一的错误码和错误消息格式。
    
    Attributes:
        code: HTTP 状态码或业务错误码
        message: 错误描述信息
    """
    
    def __init__(self, code: int, message: str):
        super().__init__(message)
        self.code = code
        self.message = message
    
    def __str__(self) -> str:
        return f"[{self.code}] {self.message}"


class AIServiceException(AppException):
    """
    AI 服务异常
    
    调用 AI Provider 生成内容时发生的错误，如 API 调用失败、超时等。
    """
    
    def __init__(self, message: str = "AI 服务调用失败"):
        super().__init__(code=503, message=message)


class DatabaseException(AppException):
    """
    数据库异常
    
    数据库操作失败时抛出，如连接失败、SQL 执行错误等。
    """
    
    def __init__(self, message: str = "数据库操作失败"):
        super().__init__(code=500, message=message)


class NotFoundException(AppException):
    """
    资源未找到异常
    
    请求的资源不存在时抛出，如收藏记录不存在。
    """
    
    def __init__(self, message: str = "请求的资源不存在"):
        super().__init__(code=404, message=message)


class ValidationException(AppException):
    """
    参数校验异常
    
    请求参数不合法时抛出。
    """
    
    def __init__(self, message: str = "请求参数错误"):
        super().__init__(code=400, message=message)


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
        return JSONResponse(
            status_code=exc.code,
            content=ApiResponse(code=exc.code, message=exc.message).model_dump()
        )
        
    # 处理通用异常（兜底）
    @app.exception_handler(Exception)
    async def general_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        """处理所有未捕获的异常"""
        # 记录错误日志（生产环境建议添加）
        # logger.error(f"Unhandled exception: {exc}", exc_info=True)
            
        return JSONResponse(
            status_code=500,
            content=ApiResponse(
                code=500, 
                message=f"服务器内部错误：{str(exc)}"
            ).model_dump()
        )
