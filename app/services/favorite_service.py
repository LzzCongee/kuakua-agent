"""
收藏管理服务模块

使用 SQLAlchemy AsyncSession 实现用户收藏的增删改查功能
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import Favorite
from app.models.schemas import FavoriteCreate, FavoriteResponse
from app.core.exceptions import DatabaseException, NotFoundException


class FavoriteService:
    """
    收藏管理服务类

    封装用户收藏夸夸语录的业务逻辑，包括列表查询、添加、删除等操作。

    Example:
        >>> service = FavoriteService()
        >>> favorites = await service.list_favorites("user123", session)
        >>> new_favorite = await service.add_favorite("user123", FavoriteCreate(content="你真棒！"), session)
    """

    async def list_favorites(
        self, user_id: str, session: AsyncSession
    ) -> list[FavoriteResponse]:
        """
        获取用户的收藏列表

        查询指定用户的所有收藏记录，按创建时间倒序排列。

        Args:
            user_id: 用户标识
            session: 数据库会话

        Returns:
            list[FavoriteResponse]: 收藏记录列表

        Raises:
            DatabaseException: 当数据库查询失败时抛出
        """
        try:
            stmt = (
                select(Favorite)
                .where(Favorite.user_id == user_id)
                .order_by(Favorite.created_at.desc())
            )
            result = await session.execute(stmt)
            rows = result.scalars().all()

            return [
                FavoriteResponse(
                    id=row.id,
                    content=row.content,
                    scene=row.scene,
                    created_at=row.created_at if isinstance(row.created_at, datetime) else datetime.fromisoformat(row.created_at),
                )
                for row in rows
            ]
        except Exception as e:
            raise DatabaseException(f"查询收藏列表失败: {str(e)}")

    async def add_favorite(
        self,
        user_id: str,
        data: FavoriteCreate,
        session: AsyncSession,
    ) -> FavoriteResponse:
        """
        添加收藏记录

        为指定用户添加一条新的夸夸语录收藏。

        Args:
            user_id: 用户标识
            data: 收藏创建数据，包含内容和场景
            session: 数据库会话

        Returns:
            FavoriteResponse: 新创建的收藏记录（包含生成的 ID 和时间戳）

        Raises:
            DatabaseException: 当数据库插入失败时抛出
        """
        try:
            favorite = Favorite(
                user_id=user_id,
                content=data.content,
                scene=data.scene,
            )
            session.add(favorite)
            await session.flush()

            return FavoriteResponse(
                id=favorite.id,
                content=favorite.content,
                scene=favorite.scene,
                created_at=favorite.created_at,
            )
        except Exception as e:
            raise DatabaseException(f"添加收藏失败: {str(e)}")

    async def delete_favorite(
        self, user_id: str, favorite_id: int, session: AsyncSession
    ) -> bool:
        """
        删除单条收藏记录

        删除指定用户的特定收藏记录。

        Args:
            user_id: 用户标识
            favorite_id: 收藏记录 ID
            session: 数据库会话

        Returns:
            bool: 删除成功返回 True

        Raises:
            NotFoundException: 当收藏记录不存在时抛出
            DatabaseException: 当数据库删除失败时抛出
        """
        try:
            # 先检查记录是否存在且属于该用户
            stmt = select(Favorite).where(
                Favorite.id == favorite_id, Favorite.user_id == user_id
            )
            result = await session.execute(stmt)
            favorite = result.scalar_one_or_none()

            if not favorite:
                raise NotFoundException(f"收藏记录不存在: {favorite_id}")

            await session.delete(favorite)
            await session.flush()
            return True
        except NotFoundException:
            raise
        except Exception as e:
            raise DatabaseException(f"删除收藏失败: {str(e)}")

    async def clear_favorites(
        self, user_id: str, session: AsyncSession
    ) -> int:
        """
        清空用户所有收藏

        删除指定用户的所有收藏记录。

        Args:
            user_id: 用户标识
            session: 数据库会话

        Returns:
            int: 删除的记录数量

        Raises:
            DatabaseException: 当数据库删除失败时抛出
        """
        try:
            stmt = delete(Favorite).where(Favorite.user_id == user_id)
            result = await session.execute(stmt)
            await session.flush()
            return result.rowcount
        except Exception as e:
            raise DatabaseException(f"清空收藏失败: {str(e)}")
