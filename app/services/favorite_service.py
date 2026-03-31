"""
收藏管理服务模块

提供用户收藏夸夸语录的增删改查功能。
"""

from datetime import datetime
from typing import Optional

import aiosqlite

from app.models.schemas import FavoriteCreate, FavoriteResponse
from app.models.database import get_db
from app.core.exceptions import DatabaseException, NotFoundException


class FavoriteService:
    """
    收藏管理服务类
    
    封装用户收藏夸夸语录的业务逻辑，包括列表查询、添加、删除等操作。
    
    Attributes:
        db_path: 数据库文件路径，None 表示使用默认路径
        
    Example:
        >>> service = FavoriteService()
        >>> favorites = await service.list_favorites("user123")
        >>> new_favorite = await service.add_favorite("user123", FavoriteCreate(content="你真棒！"))
    """
    
    def __init__(self, db_path: Optional[str] = None):
        """
        初始化收藏管理服务
        
        Args:
            db_path: 数据库文件路径，None 表示使用默认路径
        """
        self.db_path = db_path
    
    async def list_favorites(self, user_id: str) -> list[FavoriteResponse]:
        """
        获取用户的收藏列表
        
        查询指定用户的所有收藏记录，按创建时间倒序排列。
        
        Args:
            user_id: 用户标识
            
        Returns:
            list[FavoriteResponse]: 收藏记录列表
            
        Raises:
            DatabaseException: 当数据库查询失败时抛出
        """
        try:
            async with get_db(self.db_path) as db:
                async with db.execute(
                    """
                    SELECT id, content, scene, created_at 
                    FROM favorites 
                    WHERE user_id = ? 
                    ORDER BY created_at DESC
                    """,
                    (user_id,)
                ) as cursor:
                    rows = await cursor.fetchall()
                    
                    return [
                        FavoriteResponse(
                            id=row["id"],
                            content=row["content"],
                            scene=row["scene"],
                            created_at=datetime.fromisoformat(row["created_at"])
                            if isinstance(row["created_at"], str)
                            else row["created_at"]
                        )
                        for row in rows
                    ]
        except aiosqlite.Error as e:
            raise DatabaseException(f"查询收藏列表失败: {str(e)}")
        except Exception as e:
            raise DatabaseException(f"查询收藏列表时发生错误: {str(e)}")
    
    async def add_favorite(
        self, 
        user_id: str, 
        data: FavoriteCreate
    ) -> FavoriteResponse:
        """
        添加收藏记录
        
        为指定用户添加一条新的夸夸语录收藏。
        
        Args:
            user_id: 用户标识
            data: 收藏创建数据，包含内容和场景
            
        Returns:
            FavoriteResponse: 新创建的收藏记录（包含生成的 ID 和时间戳）
            
        Raises:
            DatabaseException: 当数据库插入失败时抛出
        """
        try:
            async with get_db(self.db_path) as db:
                cursor = await db.execute(
                    """
                    INSERT INTO favorites (user_id, content, scene) 
                    VALUES (?, ?, ?)
                    """,
                    (user_id, data.content, data.scene)
                )
                await db.commit()
                
                favorite_id = cursor.lastrowid
                
                # 查询刚插入的记录以获取完整信息
                async with db.execute(
                    """
                    SELECT id, content, scene, created_at 
                    FROM favorites 
                    WHERE id = ?
                    """,
                    (favorite_id,)
                ) as cursor2:
                    row = await cursor2.fetchone()
                    
                    return FavoriteResponse(
                        id=row["id"],
                        content=row["content"],
                        scene=row["scene"],
                        created_at=datetime.fromisoformat(row["created_at"])
                        if isinstance(row["created_at"], str)
                        else row["created_at"]
                    )
        except aiosqlite.Error as e:
            raise DatabaseException(f"添加收藏失败: {str(e)}")
        except Exception as e:
            raise DatabaseException(f"添加收藏时发生错误: {str(e)}")
    
    async def delete_favorite(self, user_id: str, favorite_id: int) -> bool:
        """
        删除单条收藏记录
        
        删除指定用户的特定收藏记录。
        
        Args:
            user_id: 用户标识
            favorite_id: 收藏记录 ID
            
        Returns:
            bool: 删除成功返回 True，记录不存在返回 False
            
        Raises:
            NotFoundException: 当收藏记录不存在时抛出
            DatabaseException: 当数据库删除失败时抛出
        """
        try:
            async with get_db(self.db_path) as db:
                # 先检查记录是否存在且属于该用户
                async with db.execute(
                    "SELECT id FROM favorites WHERE id = ? AND user_id = ?",
                    (favorite_id, user_id)
                ) as cursor:
                    row = await cursor.fetchone()
                    if not row:
                        raise NotFoundException(f"收藏记录不存在: {favorite_id}")
                
                # 执行删除
                await db.execute(
                    "DELETE FROM favorites WHERE id = ? AND user_id = ?",
                    (favorite_id, user_id)
                )
                await db.commit()
                
                return True
        except NotFoundException:
            raise
        except aiosqlite.Error as e:
            raise DatabaseException(f"删除收藏失败: {str(e)}")
        except Exception as e:
            raise DatabaseException(f"删除收藏时发生错误: {str(e)}")
    
    async def clear_favorites(self, user_id: str) -> int:
        """
        清空用户所有收藏
        
        删除指定用户的所有收藏记录。
        
        Args:
            user_id: 用户标识
            
        Returns:
            int: 删除的记录数量
            
        Raises:
            DatabaseException: 当数据库删除失败时抛出
        """
        try:
            async with get_db(self.db_path) as db:
                cursor = await db.execute(
                    "DELETE FROM favorites WHERE user_id = ?",
                    (user_id,)
                )
                await db.commit()
                
                return cursor.rowcount
        except aiosqlite.Error as e:
            raise DatabaseException(f"清空收藏失败: {str(e)}")
        except Exception as e:
            raise DatabaseException(f"清空收藏时发生错误: {str(e)}")
