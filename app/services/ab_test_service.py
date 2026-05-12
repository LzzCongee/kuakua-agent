"""
AB 测试管理服务模块

提供 AB 测试的创建、管理和灰度流量分配功能
"""

import hashlib

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.models import ABTest, Prompt
from ..models.schemas import ABTestCreate, ABTestResponse, ABTestUpdate
from ..core.exceptions import DatabaseException, NotFoundException, ValidationException


class ABTestService:
    """
    AB 测试管理服务类

    封装 AB 测试的 CRUD 逻辑和灰度流量分配算法。

    Example:
        >>> service = ABTestService()
        >>> tests = await service.list_ab_tests(session)
        >>> prompt = await service.get_prompt_for_user("career", "user123", session)
    """

    async def list_ab_tests(
        self, session: AsyncSession
    ) -> list[ABTestResponse]:
        """列出所有 AB 测试"""
        try:
            stmt = select(ABTest).order_by(ABTest.created_at.desc())
            result = await session.execute(stmt)
            rows = result.scalars().all()
            return [self._to_response(row) for row in rows]
        except Exception as e:
            raise DatabaseException(f"查询 AB 测试列表失败: {str(e)}")

    async def create_ab_test(
        self, data: ABTestCreate, session: AsyncSession
    ) -> ABTestResponse:
        """创建 AB 测试"""
        try:
            # 验证 prompt_a 和 prompt_b 存在
            await self._validate_prompt_exists(data.prompt_a_id, session)
            await self._validate_prompt_exists(data.prompt_b_id, session)

            ab_test = ABTest(
                name=data.name,
                scene=data.scene,
                prompt_a_id=data.prompt_a_id,
                prompt_b_id=data.prompt_b_id,
                traffic_ratio=data.traffic_ratio,
                status="running",
            )
            session.add(ab_test)
            await session.flush()
            return self._to_response(ab_test)
        except (NotFoundException, ValidationException):
            raise
        except Exception as e:
            raise DatabaseException(f"创建 AB 测试失败: {str(e)}")

    async def update_ab_test(
        self,
        ab_test_id: int,
        data: ABTestUpdate,
        session: AsyncSession,
    ) -> ABTestResponse:
        """更新 AB 测试配置"""
        try:
            stmt = select(ABTest).where(ABTest.id == ab_test_id)
            result = await session.execute(stmt)
            ab_test = result.scalar_one_or_none()
            if not ab_test:
                raise NotFoundException(f"AB 测试不存在: {ab_test_id}")

            if data.name is not None:
                ab_test.name = data.name  # type: ignore
            if data.traffic_ratio is not None:
                ab_test.traffic_ratio = data.traffic_ratio  # type: ignore
            if data.status is not None:
                if data.status not in ("running", "stopped"):
                    raise ValidationException("status 只能是 running 或 stopped")
                ab_test.status = data.status  # type: ignore

            await session.flush()
            return self._to_response(ab_test)
        except (NotFoundException, ValidationException):
            raise
        except Exception as e:
            raise DatabaseException(f"更新 AB 测试失败: {str(e)}")

    async def delete_ab_test(
        self, ab_test_id: int, session: AsyncSession
    ) -> None:
        """结束 AB 测试（设置状态为 stopped）"""
        try:
            stmt = select(ABTest).where(ABTest.id == ab_test_id)
            result = await session.execute(stmt)
            ab_test = result.scalar_one_or_none()
            if not ab_test:  # type: ignore[reportGeneralTypeIssues]
                raise NotFoundException(f"AB 测试不存在: {ab_test_id}")

            ab_test.status = "stopped"  # type: ignore[reportAttributeAccessIssue]
            await session.flush()
        except NotFoundException:
            raise
        except Exception as e:
            raise DatabaseException(f"结束 AB 测试失败: {str(e)}")

    async def get_prompt_for_user(
        self,
        scene: str,
        user_id: str,
        session: AsyncSession,
    ) -> dict[str, str] | None:
        """
        根据 AB 测试配置为用户分配 prompt
        
        使用 user_id 的 MD5 哈希决定走哪组，保证同一用户始终走同一组。
        
        Args:
            scene: 场景标识
            user_id: 用户 ID
            session: 数据库会话
            
        Returns:
            {"system": "...", "user": "...", "ab_group": "a"/"b", "ab_test_id": int} 或 None
        """
        try:
            # 查询该场景是否有进行中的 AB 测试
            stmt = select(ABTest).where(
                ABTest.scene == scene,
                ABTest.status == "running",
            )
            result = await session.execute(stmt)
            ab_test = result.scalar_one_or_none()

            if not ab_test:  # type: ignore[reportGeneralTypeIssues]
                return None

            # 根据 user_id 哈希决定走哪组
            hash_val = int(hashlib.md5(user_id.encode()).hexdigest(), 16) % 100
            use_group_b = hash_val < float(ab_test.traffic_ratio) * 100  # type: ignore[reportUnknownMemberType]

            prompt_id = ab_test.prompt_b_id if use_group_b else ab_test.prompt_a_id

            # 查询对应的 prompt
            prompt_stmt = select(Prompt).where(Prompt.id == prompt_id)
            prompt_result = await session.execute(prompt_stmt)
            prompt = prompt_result.scalar_one_or_none()

            if not prompt:  # type: ignore[reportGeneralTypeIssues]
                return None

            return {
                "system": prompt.system_prompt,  # type: ignore[reportUnknownMemberType]
                "user": prompt.user_prompt,  # type: ignore[reportUnknownMemberType]
                "ab_group": "b" if use_group_b else "a",
                "ab_test_id": ab_test.id,  # type: ignore[reportUnknownMemberType]
            }
        except Exception:
            return None

    async def _validate_prompt_exists(
        self, prompt_id: int, session: AsyncSession
    ) -> None:
        """验证 prompt 是否存在"""
        stmt = select(Prompt).where(Prompt.id == prompt_id)
        result = await session.execute(stmt)
        if not result.scalar_one_or_none():
            raise NotFoundException(f"Prompt 不存在: {prompt_id}")

    def _to_response(self, row: ABTest) -> ABTestResponse:
        """ORM 对象转 Pydantic 响应"""
        return ABTestResponse(
            id=int(row.id),  # type: ignore[reportArgumentType]
            name=str(row.name),  # type: ignore[reportArgumentType]
            scene=str(row.scene),  # type: ignore[reportArgumentType]
            prompt_a_id=int(row.prompt_a_id),  # type: ignore[reportArgumentType]
            prompt_b_id=int(row.prompt_b_id),  # type: ignore[reportArgumentType]
            traffic_ratio=float(row.traffic_ratio),  # type: ignore[reportUnknownMemberType]
            status=str(row.status),  # type: ignore[reportArgumentType]
            created_at=row.created_at,  # type: ignore[reportArgumentType]
        )
