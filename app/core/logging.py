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
import logging.handlers
import os
import shutil
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

# ==================== 自定义 Handler ====================


class WindowsSafeTimedRotatingFileHandler(logging.handlers.TimedRotatingFileHandler):
    """Windows 兼容的 TimedRotatingFileHandler

    os.rename() 在 Windows 上会因文件被其他进程占用而失败（PermissionError）。
    本 handler 在轮转失败时静默恢复，保证日志系统不崩溃。
    """

    def rotate(self, source: str, dest: str) -> None:
        """覆盖 rotate，失败时回退到 copy+delete"""
        try:
            os.rename(source, dest)
        except PermissionError:
            # Windows: 另一个进程锁定了文件，尝试 copy+delete
            try:
                shutil.copy2(source, dest)
                os.remove(source)
            except Exception:
                pass  # 放弃轮转，继续写入原文件
        except OSError:
            # 兜底：shutil.move 可以处理跨设备重命名
            try:
                shutil.move(source, dest)
            except Exception:
                pass

    def doRollover(self) -> None:
        """覆盖 doRollover，确保轮转失败后 stream 不丢失"""
        try:
            super().doRollover()
        except PermissionError:
            # 轮转失败（通常是 Windows 文件锁），重新打开原文件继续写
            if self.stream is None:
                try:
                    self.stream = self._open()
                except Exception:
                    pass
            logging.warning(
                "日志轮转失败（Windows 文件锁），继续写入原文件",
                stack_info=False,
            )


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

def _should_wipe_logs() -> bool:
    """
    判断是否应该清空并重新创建日志文件
    
    逻辑：如果日志文件存在但上次修改时间不是今天，说明服务停止过，
    需要重新开始新日志（符合微服务每次启动新会话的理念）
    """
    from datetime import date, datetime
    
    log_file = LOG_DIR / "kuakua-agent.log"
    
    if not log_file.exists():
        return False
    
    # 获取文件最后修改时间
    mtime = datetime.fromtimestamp(log_file.stat().st_mtime)
    
    # 如果最后修改不是今天，说明服务停止过，需要覆盖
    if mtime.date() < date.today():
        return True
    
    return False


def _wipe_existing_logs() -> None:
    """清空日志文件内容，重新开始

    优先尝试 unlink 删除文件（Linux 无锁问题），
    若失败（Windows 文件锁）则回退到 truncate 清空内容。
    """
    for filename in ["kuakua-agent.log", "kuakua-agent-error.log"]:
        log_file = LOG_DIR / filename
        if not log_file.exists():
            continue
        try:
            log_file.unlink()
        except PermissionError:
            # Windows: 其他进程持有文件锁，回退到截断清空
            try:
                with open(log_file, "w") as f:
                    f.truncate(0)
            except Exception:
                pass


def setup_logging(config_path: Optional[Path] = None) -> None:
    """
    初始化日志配置
    
    从 logging.yaml 读取配置并应用。
    如果配置文件不存在，使用默认配置。
    
    启动逻辑：
    - 如果日志文件是今天修改的（服务正在运行），保留追加
    - 如果日志文件是昨天或更早的（服务停止后重启），覆盖重新开始
    """
    # 确保日志目录存在
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    
    # 检查是否需要覆盖旧日志
    if _should_wipe_logs():
        _wipe_existing_logs()
    
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
    
    # 文件处理器（每天轮转，保留 7 天）
    file_handler = WindowsSafeTimedRotatingFileHandler(
        LOG_DIR / "kuakua-agent.log",
        when="MIDNIGHT",
        interval=1,
        backupCount=7,
        encoding="utf-8"
    )
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(trace_id)s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    ))
    file_handler.addFilter(_trace_filter)
    root_logger.addHandler(file_handler)

    # 抑制第三方库的冗长日志
    for noisy_logger in ("mcp", "httpx", "httpcore"):
        logging.getLogger(noisy_logger).setLevel(logging.WARNING)

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
        exclude_paths: list[str] | None = None
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
