"""
Prompt 管理服务模块

提供 Prompt 模板的增删改查和热更新功能
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import Prompt
from app.models.schemas import PromptResponse, PromptUpdate
from app.core.exceptions import DatabaseException, NotFoundException


class PromptService:
    """
    Prompt 管理服务类

    封装 Prompt 模板的 CRUD 逻辑，支持热更新（无需重启服务）。

    Example:
        >>> service = PromptService()
        >>> prompts = await service.list_prompts(session)
        >>> await service.update_prompt("career", PromptUpdate(system_prompt="..."), session)
    """

    async def list_prompts(
        self, session: AsyncSession
    ) -> list[PromptResponse]:
        """列出所有 prompt 模板"""
        try:
            stmt = select(Prompt).order_by(Prompt.scene)
            result = await session.execute(stmt)
            rows = result.scalars().all()
            return [self._to_response(row) for row in rows]
        except Exception as e:
            raise DatabaseException(f"查询 Prompt 列表失败: {str(e)}")

    async def get_prompt(
        self, scene: str, session: AsyncSession
    ) -> PromptResponse:
        """获取指定场景的活跃 prompt"""
        try:
            stmt = select(Prompt).where(
                Prompt.scene == scene, Prompt.is_active == True  # noqa: E712
            )
            result = await session.execute(stmt)
            row = result.scalar_one_or_none()
            if not row:
                raise NotFoundException(f"Prompt 不存在: {scene}")
            return self._to_response(row)
        except NotFoundException:
            raise
        except Exception as e:
            raise DatabaseException(f"查询 Prompt 失败: {str(e)}")

    async def update_prompt(
        self,
        scene: str,
        data: PromptUpdate,
        session: AsyncSession,
    ) -> PromptResponse:
        """
        更新 prompt（热更新）
        
        如果已有该场景的 prompt，则版本号 +1 并更新内容。
        如果不存在，则创建新记录。
        """
        try:
            stmt = select(Prompt).where(Prompt.scene == scene)
            result = await session.execute(stmt)
            existing = result.scalar_one_or_none()

            if existing:
                existing.system_prompt = data.system_prompt
                existing.user_prompt = data.user_prompt
                existing.input_type = data.input_type
                existing.version += 1
                existing.updated_by = data.updated_by
                existing.updated_at = datetime.utcnow()
                await session.flush()
                return self._to_response(existing)
            else:
                new_prompt = Prompt(
                    scene=scene,
                    system_prompt=data.system_prompt,
                    user_prompt=data.user_prompt,
                    input_type=data.input_type,
                    version=1,
                    is_active=True,
                    updated_by=data.updated_by,
                )
                session.add(new_prompt)
                await session.flush()
                return self._to_response(new_prompt)
        except Exception as e:
            raise DatabaseException(f"更新 Prompt 失败: {str(e)}")

    async def get_active_prompt_content(
        self, scene: str, input_type: str, session: AsyncSession
    ) -> Optional[dict[str, str]]:
        """
        获取活跃 prompt 的内容（供业务服务调用）
        
        先从数据库查找，如果没找到则回退到硬编码的模板。
        
        Returns:
            {"system": "...", "user": "..."} 或 None
        """
        try:
            stmt = select(Prompt).where(
                Prompt.scene == scene,
                Prompt.input_type == input_type,
                Prompt.is_active == True,  # noqa: E712
            )
            result = await session.execute(stmt)
            row = result.scalar_one_or_none()
            if row:
                return {"system": row.system_prompt, "user": row.user_prompt}
            return None
        except Exception:
            return None

    def _to_response(self, row: Prompt) -> PromptResponse:
        """ORM 对象转 Pydantic 响应"""
        return PromptResponse(
            id=row.id,
            scene=row.scene,
            system_prompt=row.system_prompt,
            user_prompt=row.user_prompt,
            input_type=row.input_type,
            version=row.version,
            is_active=row.is_active,
            updated_at=row.updated_at,
            updated_by=row.updated_by,
        )
