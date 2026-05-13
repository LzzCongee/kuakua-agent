"""
日志模块

提供：
1. 结构化日志配置（支持 trace_id）
2. 请求追踪中间件
3. 统一的日志记录器获取函数

遵循微服务架构最佳实践：
- 配置与代码分离（logging.yaml）
- 每个请求自动生成 trace_id
- 结构化日志输出便于收集和分析
"""

import logging
import logging.config
import os
import sys
import time
import uuid
from contextvars import ContextVar
from pathlib import Path
from typing import Callable, Optional

import yaml
from fastapi import FastAPI, Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from app.config import get_settings


# ==================== 全局变量 ====================

# 日志目录（项目根目录下的 logs 文件夹）
LOG_DIR = Path(__file__).parent.parent.parent / "logs"

# 日志配置路径
LOG_CONFIG_PATH = Path(__file__).parent.parent.parent / "logging.yaml"


# ==================== Trace ID 管理 ====================

# 使用 contextvars 替代 threading.local，确保 asyncio 环境下安全
_trace_id_var: ContextVar[str] = ContextVar("trace_id", default="-")


class TraceIDFilter(logging.Filter):
    """
    日志过滤器：为每条日志添加 trace_id
    
    使用 contextvars 保存当前请求的 trace_id，
    相比 threading.local 更安全（支持 asyncio 协程切换）
    """
    
    def filter(self, record: logging.LogRecord) -> bool:
        """为日志记录添加 trace_id 属性"""
        record.trace_id = _trace_id_var.get("-")
        return True


# 全局 trace_id 过滤器实例
_trace_filter = TraceIDFilter()


def get_trace_id() -> str:
    """
    获取当前请求的 trace_id
    
    Returns:
        str: 当前协程的 trace_id，如果没有则返回 "-"
    """
    return _trace_id_var.get("-")


def set_trace_id(trace_id: str) -> None:
    """
    设置当前协程的 trace_id
    
    Args:
        trace_id: 追踪 ID
    """
    _trace_id_var.set(trace_id)


def clear_trace_id() -> None:
    """重置当前协程的 trace_id"""
    _trace_id_var.set("-")


# ==================== 日志初始化 ====================

def _cleanup_log_files() -> None:
    """删除现有日志文件，确保服务每次启动时从新文件开始（覆盖模式）"""
    for filename in ["kuakua-agent.log", "kuakua-agent-error.log"]:
        log_file = LOG_DIR / filename
        if log_file.exists():
            log_file.unlink()


def setup_logging(config_path: Optional[Path] = None) -> None:
    """
    初始化日志配置
    
    从 logging.yaml 读取配置并应用。
    如果配置文件不存在，使用默认配置。
    
    Args:
        config_path: 日志配置文件路径，默认使用项目根目录的 logging.yaml
    """
    # 确保日志目录存在
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    
    # 删除旧日志文件，实现每次启动覆盖而非追加
    _cleanup_log_files()
    
    config_path = config_path or LOG_CONFIG_PATH
    
    if config_path.exists():
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                config = yaml.safe_load(f)
            
            # 应用配置
            logging.config.dictConfig(config)
        except Exception as e:
            # 配置加载失败，使用默认配置
            _setup_default_logging()
            logging.warning(f"日志配置文件加载失败，使用默认配置: {e}")
    else:
        # 配置文件不存在，使用默认配置
        _setup_default_logging()
        logging.info(f"日志配置文件不存在，使用默认配置: {config_path}")


def _setup_default_logging() -> None:
    """
    设置默认日志配置（当 logging.yaml 不存在时使用）
    
    输出到控制台和 logs/app.log 文件
    """
    # 确保日志目录存在
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    
    # 清空现有处理器
    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    
    # 设置根日志级别
    root_logger.setLevel(logging.INFO)
    
    # 控制台处理器
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(trace_id)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    ))
    console_handler.addFilter(_trace_filter)
    root_logger.addHandler(console_handler)
    
    # 文件处理器
    file_handler = logging.handlers.TimedRotatingFileHandler(
        LOG_DIR / "kuakua-agent.log",
        when="M",
        interval=1440,
        backupCount=30,
        encoding="utf-8"
    )
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(trace_id)s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    ))
    file_handler.addFilter(_trace_filter)
    root_logger.addHandler(file_handler)


# ==================== 日志记录器获取 ====================

def get_logger(name: str) -> logging.Logger:
    """
    获取应用日志记录器
    
    Args:
        name: 日志记录器名称，通常使用 __name__（模块路径）
        
    Returns:
        logging.Logger: 配置好的日志记录器
        
    Example:
        >>> logger = get_logger(__name__)
        >>> logger.info("用户请求处理完成")
        >>> logger.error("数据库连接失败", exc_info=True)
    """
    logger = logging.getLogger(name)
    return logger


# ==================== 请求追踪中间件 ====================

class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """
    请求日志中间件
    
    功能：
    1. 为每个请求生成唯一的 trace_id
    2. 记录请求开始和结束日志
    3. 计算请求处理耗时
    4. 在响应头中返回 trace_id 供客户端追踪
    
    推荐的请求头：
    - X-User-ID: 用户标识
    - X-Trace-ID: 客户端传入的追踪 ID（可选，服务端会生成新的）
    """
    
    def __init__(
        self, 
        app: ASGIApp,
        exclude_paths: Optional[list[str]] = None
    ):
        """
        初始化中间件
        
        Args:
            app: ASGI 应用
            exclude_paths: 不记录日志的路径列表（如健康检查）
        """
        super().__init__(app)
        self.exclude_paths = exclude_paths or ["/health", "/docs", "/redoc", "/openapi.json"]
    
    async def dispatch(
        self, 
        request: Request, 
        call_next: Callable
    ) -> Response:
        """处理请求"""
        
        # 检查是否需要跳过日志记录
        if request.url.path in self.exclude_paths:
            return await call_next(request)
        
        # 获取或生成 trace_id
        trace_id = request.headers.get("X-Trace-ID") or str(uuid.uuid4())[:8]
        
        # 优先从请求头获取 user_id，其次从 URL 路径参数尝试提取
        user_id = request.headers.get("X-User-ID")
        if not user_id:
            # 尝试从常见路径参数中提取 user_id
            path_user = request.path_params.get("user_id") or request.path_params.get("userId")
            user_id = path_user if path_user else "anonymous"
        
        # 设置到线程本地存储
        set_trace_id(trace_id)
        
        # 记录请求开始
        logger = get_logger("app.middleware")
        logger.info(
            f"请求开始 | {request.method} {request.url.path} | "
            f"user_id={user_id} | trace_id={trace_id}"
        )
        
        # 记录开始时间
        start_time = time.perf_counter()
        
        try:
            # 处理请求
            response = await call_next(request)
            
            # 计算耗时
            elapsed_ms = (time.perf_counter() - start_time) * 1000
            
            # 在响应头中添加 trace_id
            response.headers["X-Trace-ID"] = trace_id
            response.headers["X-Request-Time-Ms"] = f"{elapsed_ms:.2f}"
            
            # 记录请求完成
            status_code = response.status_code
            log_level = logging.INFO if status_code < 400 else logging.WARNING
            
            logger.log(
                log_level,
                f"请求完成 | {request.method} {request.url.path} | "
                f"status={status_code} | elapsed={elapsed_ms:.2f}ms | "
                f"user_id={user_id} | trace_id={trace_id}"
            )
            
            return response
            
        except Exception as e:
            # 计算耗时
            elapsed_ms = (time.perf_counter() - start_time) * 1000
            
            # 记录错误
            logger.error(
                f"请求异常 | {request.method} {request.url.path} | "
                f"error={str(e)} | elapsed={elapsed_ms:.2f}ms | "
                f"user_id={user_id} | trace_id={trace_id}",
                exc_info=True
            )
            raise
            
        finally:
            # 清除 trace_id
            clear_trace_id()


# ==================== 中间件注册函数 ====================

def register_logging_middleware(app: FastAPI) -> None:
    """
    注册日志中间件到 FastAPI 应用
    
    Args:
        app: FastAPI 应用实例
    """
    # 确保日志已初始化
    setup_logging()
    
    # 注册请求日志中间件
    app.add_middleware(RequestLoggingMiddleware)
    
    # 记录启动日志
    logger = get_logger("app.startup")
    logger.info("日志中间件已注册")
