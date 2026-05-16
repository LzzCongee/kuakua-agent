"""
记忆服务工厂模块

根据配置自动选择使用 SQL（PostgreSQL/SQLite）或 CloudBase NoSQL 数据库
提供统一的接口，方便在两种实现之间切换
"""


from ..config import get_settings
from ..models.schemas import MemorySummary

# CloudBase 实现
from ..services.cloudbase_memory import CloudBaseMemoryService

# SQL 实现
from ..services.memory_service import MemoryService as SQLMemoryService

# 统一类型别名
MemoryServiceType = SQLMemoryService | CloudBaseMemoryService


def get_memory_service(db_session=None) -> MemoryServiceType:
    """
    获取记忆服务实例（工厂函数）
    
    根据配置项 `use_cloudbase` 决定使用哪种实现：
    - True: 使用 CloudBase NoSQL 数据库
    - False: 使用 SQLAlchemy（PostgreSQL/SQLite）
    
    Args:
        db_session: 数据库会话（仅 SQL 实现需要）
        
    Returns:
        记忆服务实例
        
    Usage:
        # SQL 模式（需要传入 db_session）
        memory_service = get_memory_service(db_session)
        
        # CloudBase 模式（不需要 db_session）
        memory_service = get_memory_service()
    """
    settings = get_settings()
    
    if settings.use_cloudbase:
        # 使用 CloudBase NoSQL 数据库
        return CloudBaseMemoryService(
            env_id=settings.cloudbase_env_id,
            secret_id=settings.cloudbase_secret_id,
            secret_key=settings.cloudbase_secret_key
        )
    else:
        # 使用 SQLAlchemy（PostgreSQL/SQLite）
        if db_session is None:
            raise ValueError("SQL 模式需要传入 db_session 参数")
        return SQLMemoryService(db_session)


# 导出统一的接口
__all__ = ["get_memory_service", "SQLMemoryService", "CloudBaseMemoryService", "MemorySummary"]
