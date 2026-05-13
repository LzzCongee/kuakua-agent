"""
MCP Client 封装模块

基于官方 mcp Python SDK 的 MCP Client，实现与 supermemory MCP Server 的 SSE 长连接通信。
设计为单例模式，由 FastAPI lifespan 统一管理生命周期。

supermemory MCP Server 提供语义记忆功能：
- search_memory: 语义搜索用户历史记忆
- add_memory: 添加对话到语义记忆

关键设计：
- SSE 长连接，应用启动时建立、关闭时释放
- 静默降级：服务不可用时返回 None，不抛异常
- 短超时：避免阻塞主请求流程
"""

import asyncio
import json
from typing import Any, Dict, Optional

from app.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)
settings = get_settings()


class MCPClient:
    """
    基于官方 mcp SDK 的 MCP Client 封装

    支持 SSE 长连接，自动协议握手，工具动态发现。
    设计为单例，由 FastAPI lifespan 统一管理生命周期。
    """

    def __init__(self) -> None:
        self.url: str = settings.supermemory_url
        self.headers: Dict[str, str] = settings.supermemory_headers or {}
        self.timeout: float = settings.supermemory_timeout
        self.enabled: bool = settings.supermemory_enabled

        self._session: Any = None  # ClientSession，无类型注解避免循环 import
        self._client_ctx: Any = None

    async def connect(self) -> None:
        """建立 SSE 连接并完成 MCP 协议握手（应用启动时调用）"""
        if not self.enabled:
            logger.info("supermemory MCP 已禁用，跳过连接")
            return

        try:
            from mcp.client.sse import sse_client
            from mcp import ClientSession

            logger.info(f"正在建立 MCP 连接: {self.url}")
            # 使用 wait_for 包装连接和握手过程，避免启动阻塞
            async with asyncio.timeout(self.timeout):
                self._client_ctx = sse_client(self.url, headers=self.headers)
                read, write = await self._client_ctx.__aenter__()
                self._session = ClientSession(read, write)

                # MCP 协议握手：initialize → list_tools
                await self._session.initialize()
                tools = await self._session.list_tools()
                tool_names = [t.name for t in tools]
                logger.info(f"MCP 连接已建立 | 可用工具: {tool_names}")
        except asyncio.TimeoutError:
            logger.error(f"MCP 连接超时 ({self.timeout}s): {self.url}")
            self._session = None
            # 注意：这里不需要手动调用 __aexit__，因为 timeout 抛出异常会中断 aenter
        except Exception as e:
            logger.error(f"MCP 连接失败: {e}")
            self._session = None

    async def call(self, tool_name: str, **kwargs: Any) -> Optional[Dict[str, Any]]:
        """
        调用 MCP 工具，带超时和静默降级

        Args:
            tool_name: MCP 工具名（如 add_memory、search_memory）
            **kwargs: 工具参数

        Returns:
            dict: 工具返回结果（已解析 content）
            None: 调用失败或降级时
        """
        if not self.enabled or self._session is None:
            return None

        try:
            result = await asyncio.wait_for(
                self._session.call_tool(tool_name, arguments=kwargs),
                timeout=self.timeout,
            )

            # 解析 CallToolResult → dict
            # result.content 是 list[TextContent | ImageContent]
            if result.content and hasattr(result.content[0], "text"):
                return json.loads(result.content[0].text)
            return {}

        except asyncio.TimeoutError:
            logger.warning(f"MCP 调用超时 [{tool_name}]")
            return None
        except Exception as e:
            logger.warning(f"MCP 调用失败 [{tool_name}]: {e}")
            return None

    async def disconnect(self) -> None:
        """关闭 SSE 连接（应用关闭时调用）"""
        if self._client_ctx is not None:
            try:
                await self._client_ctx.__aexit__(None, None, None)
            except Exception:
                pass
            self._client_ctx = None
            self._session = None
            logger.info("MCP 连接已关闭")


# 全局单例（由 lifespan 管理生命周期）
mcp_client = MCPClient()
