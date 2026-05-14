"""
MCP Client 封装模块

基于官方 mcp Python SDK 的 MCP Client，实现与 supermemory MCP Server 的 SSE 长连接通信。
设计为单例模式，由 FastAPI lifespan 统一管理生命周期。

supermemory MCP Server 提供语义记忆功能：
- search_memory: 语义搜索用户历史记忆
- add_memory: 添加对话到语义记忆

关键设计：
- SSE 长连接，应用启动时建立、关闭时释放
- ClientSession 必须作为异步上下文管理器使用（启动 _receive_loop）
- 静默降级：服务不可用时返回 None，不抛异常
- 短超时：避免阻塞主请求流程
"""

import asyncio
import json
from contextlib import AsyncExitStack
from typing import Any, Dict, Optional  # noqa: UP035

from app.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)
settings = get_settings()


class MCPClient:
    """
    基于官方 mcp SDK 的 MCP Client 封装

    支持 SSE 长连接，自动协议握手，工具动态发现。
    设计为单例，由 FastAPI lifespan 统一管理生命周期。

    重要：ClientSession 必须通过 async with 启动 _receive_loop，
    否则 send_request 会永远收不到响应（initialize 超时）。
    使用 AsyncExitStack 管理嵌套的异步上下文管理器生命周期。
    """

    def __init__(self) -> None:
        self.url: str = settings.supermemory_url
        self.timeout: float = settings.supermemory_timeout
        self.enabled: bool = settings.supermemory_enabled

        # 构建 headers：优先使用 supermemory_headers，否则用 supermemory_token
        if settings.supermemory_headers:
            self.headers: Dict[str, str] = dict(settings.supermemory_headers)
        else:
            self.headers = {"token": settings.supermemory_token}

        self._session: Any = None  # ClientSession，无类型注解避免循环 import
        self._exit_stack: Optional[AsyncExitStack] = None
        self._connected: bool = False
        self._available_tools: list[str] = []

    async def connect(self) -> None:
        """建立 SSE 连接并完成 MCP 协议握手（应用启动时调用）"""
        if not self.enabled:
            logger.info("supermemory MCP 已禁用，跳过连接")
            return

        try:
            from mcp.client.sse import sse_client
            from mcp import ClientSession

            # 掩码显示 token（只显示前4位）
            token = self.headers.get("token", "")
            masked_token = token[:4] + "***" if len(token) > 4 else token
            logger.info(f"正在建立 MCP 连接 | url={self.url} | token={masked_token} | headers_keys={list(self.headers.keys())}")

            # 使用 AsyncExitStack 管理嵌套的异步上下文管理器
            # 1. sse_client 是 async context manager → 提供 read/write 流
            # 2. ClientSession 是 async context manager → 启动 _receive_loop
            #    如果不作为上下文管理器使用，_receive_loop 不会启动，
            #    send_request 将永远收不到响应，导致 initialize 超时
            self._exit_stack = AsyncExitStack()
            await self._exit_stack.__aenter__()

            async with asyncio.timeout(self.timeout):
                # 进入 sse_client 上下文
                read, write = await self._exit_stack.enter_async_context(
                    sse_client(self.url, headers=self.headers)
                )

                # 进入 ClientSession 上下文（启动 _receive_loop）
                self._session = await self._exit_stack.enter_async_context(
                    ClientSession(read, write)
                )

                # MCP 协议握手：initialize → list_tools
                logger.debug(f"MCP 开始 initialize 握手 | timeout={self.timeout}s")
                await self._session.initialize()
                tools_result = await self._session.list_tools()
                tool_names = [t.name for t in tools_result.tools]
                self._connected = True
                self._available_tools = tool_names
                logger.info(f"MCP 连接已建立 | 可用工具: {tool_names}")
        except asyncio.TimeoutError:
            logger.error(
                f"MCP 连接超时 ({self.timeout}s) | url={self.url}\n"
                f"  SSE 连接成功但 MCP 握手无响应，请检查：\n"
                f"  1. MCP Server 进程是否正常运行\n"
                f"  2. Server 端日志有无 initialize 请求记录\n"
                f"  3. nginx 是否配置了 proxy_buffering off（SSE 需要）"
            )
            await self._cleanup()
        except Exception as e:
            logger.error(f"MCP 连接失败 | url={self.url} | error={type(e).__name__}: {e}")
            await self._cleanup()

    async def _cleanup(self) -> None:
        """清理连接资源"""
        if self._exit_stack is not None:
            try:
                await self._exit_stack.aclose()
            except Exception:
                logger.debug("MCP 资源清理时异常（可忽略）", exc_info=True)
        self._exit_stack = None
        self._session = None
        self._connected = False
        self._available_tools = []

    @property
    def is_connected(self) -> bool:
        """返回 MCP 连接是否可用"""
        return self.enabled and self._connected and self._session is not None

    @property
    def available_tools(self) -> list[str]:
        """返回当前可用的 MCP 工具列表"""
        return self._available_tools

    async def call(self, tool_name: str, **kwargs: Any) -> Optional[Dict[str, Any]]:
        """
        调用 MCP 工具，带超时和静默降级

        Args:
            tool_name: MCP 工具名（如 add_memory、search_memory）
            **kwargs: 工具参数（如 user_id、query、content 等）

        Returns:
            dict: 工具返回结果（已解析 content）
            None: 调用失败或降级时
        """
        if not self.enabled or self._session is None:
            logger.debug(f"MCP 调用跳过 [{tool_name}] | enabled={self.enabled} | connected={self._connected}")
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
            logger.warning(f"MCP 调用超时 [{tool_name}] | timeout={self.timeout}s")
            return None
        except Exception as e:
            logger.warning(f"MCP 调用失败 [{tool_name}] | error={type(e).__name__}: {e}")
            return None

    async def disconnect(self) -> None:
        """关闭 SSE 连接（应用关闭时调用）"""
        await self._cleanup()
        logger.info("MCP 连接已关闭")


# 全局单例（由 lifespan 管理生命周期）
mcp_client = MCPClient()
