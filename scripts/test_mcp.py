"""
MCP Server 连接测试脚本

用法:
    python scripts/test_mcp.py                          # 使用默认配置
    python scripts/test_mcp.py --url http://xxx/sse     # 指定 URL
    python scripts/test_mcp.py --token YourName         # 指定 token
    python scripts/test_mcp.py --timeout 20             # 指定超时
    python scripts/test_mcp.py --test-call              # 测试工具调用
"""


import argparse
import asyncio
import json
import sys
import time
from urllib.parse import urljoin

import httpx


# ==================== 硬编码配置 ====================
# 直接修改这里的值进行测试，无需命令行参数
DEFAULT_URL = "http://106.55.151.27/sse"
DEFAULT_TOKEN = "kuakua-agent"
DEFAULT_TIMEOUT = 15.0
# ===================================================

def print_step(step: str, msg: str, status: str = ">>") -> None:
    print(f"  [{status}] {step}: {msg}")


def print_ok(step: str, msg: str) -> None:
    print_step(step, msg, "OK")


def print_fail(step: str, msg: str) -> None:
    print_step(step, msg, "FAIL")


def print_info(step: str, msg: str) -> None:
    print_step(step, msg, "  ")


async def test_raw_sse(url: str, token: str, timeout: float) -> bool:
    """Step 1: 测试原始 HTTP/SSE 连接"""
    print("\n[Step 1] 测试 SSE 连接")
    t0 = time.time()

    headers = {"token": token, "Cache-Control": "no-cache"}
    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(timeout, read=timeout)
        ) as client:
            resp = await client.send(
                client.build_request("GET", url, headers=headers), stream=True
            )
            elapsed = time.time() - t0

            if resp.status_code != 200:
                print_fail("SSE", f"HTTP {resp.status_code} ({elapsed:.2f}s)")
                return False

            print_ok("SSE", f"HTTP {resp.status_code} ({elapsed:.2f}s)")

            # 读取 endpoint 事件
            endpoint_url = None
            event_type = None
            data_buf = []

            async for line in resp.aiter_lines():
                line = line.strip()
                if line.startswith("event:"):
                    event_type = line[6:].strip()
                elif line.startswith("data:"):
                    data_buf.append(line[5:].strip())
                elif line == "" and data_buf:
                    data = "\n".join(data_buf)
                    if event_type == "endpoint":
                        endpoint_url = urljoin(url, data)
                        print_ok("endpoint", endpoint_url)
                        break
                    event_type = None
                    data_buf = []

            if not endpoint_url:
                print_fail("endpoint", "未收到 endpoint 事件")
                return False

            return True

    except httpx.ConnectError as e:
        print_fail("SSE", f"连接拒绝 ({time.time()-t0:.2f}s): {e}")
        return False
    except httpx.ReadTimeout:
        print_fail("SSE", f"读取超时 ({timeout}s)")
        return False
    except Exception as e:
        print_fail("SSE", f"{type(e).__name__}: {e}")
        return False


async def test_mcp_handshake(url: str, token: str, timeout: float) -> bool:
    """Step 2: 测试 MCP 协议握手（initialize）"""
    print("\n[Step 2] 测试 MCP 握手 (initialize)")
    t0 = time.time()

    headers = {"token": token, "Cache-Control": "no-cache"}

    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(timeout, read=timeout), headers=headers
        ) as client:
            # 建立 SSE
            resp = await client.send(
                client.build_request("GET", url, headers=headers), stream=True
            )

            # 读 endpoint
            endpoint_url = None
            async for line in resp.aiter_lines():
                line = line.strip()
                if line.startswith("data:"):
                    endpoint_url = urljoin(url, line[5:].strip())
                    break

            if not endpoint_url:
                print_fail("endpoint", "未收到")
                return False

            print_info("endpoint", f"{endpoint_url} ({time.time()-t0:.2f}s)")

            # 后台持续读 SSE 事件
            responses: dict[int, dict] = {}

            async def sse_reader():
                event_type = None
                data_buf = []
                async for line in resp.aiter_lines():
                    line = line.strip()
                    if line.startswith("event:"):
                        event_type = line[6:].strip()
                    elif line.startswith("data:"):
                        data_buf.append(line[5:].strip())
                    elif line == "" and data_buf:
                        data = "\n".join(data_buf)
                        if event_type == "message":
                            try:
                                msg = json.loads(data)
                                msg_id = msg.get("id")
                                if msg_id is not None:
                                    responses[msg_id] = msg
                                    print_info(
                                        "SSE响应",
                                        f"id={msg_id} ({time.time()-t0:.2f}s)",
                                    )
                            except json.JSONDecodeError:
                                print_info("SSE", f"非JSON: {data[:100]}")
                        event_type = None
                        data_buf = []

            reader_task = asyncio.create_task(sse_reader())

            # 发送 initialize 请求
            init_msg = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-03-26",
                    "capabilities": {},
                    "clientInfo": {"name": "kuakua-agent-test", "version": "0.1.0"},
                },
            }

            print_info("POST", f"initialize -> {endpoint_url}")
            r = await client.post(endpoint_url, json=init_msg)
            print_info("POST响应", f"HTTP {r.status_code}")

            if r.status_code != 202:
                print_fail("initialize", f"期望 202，实际 {r.status_code}")
                reader_task.cancel()
                return False

            # 等待 SSE 响应
            print_info("等待", f"SSE 响应 (最多 {timeout}s)...")
            wait_start = time.time()
            while time.time() - wait_start < timeout:
                if 1 in responses:
                    break
                await asyncio.sleep(0.1)

            reader_task.cancel()

            if 1 in responses:
                resp_data = responses[1]
                elapsed = time.time() - t0
                if "result" in resp_data:
                    result = resp_data["result"]
                    server_info = result.get("serverInfo", {})
                    print_ok(
                        "initialize",
                        f"成功 ({elapsed:.2f}s) | "
                        f"server={server_info.get('name', '?')} "
                        f"v{server_info.get('version', '?')}",
                    )
                    return True
                elif "error" in resp_data:
                    error = resp_data["error"]
                    print_fail(
                        "initialize",
                        f"RPC error {error.get('code')}: {error.get('message')}",
                    )
                    return False
            else:
                elapsed = time.time() - t0
                print_fail(
                    "initialize",
                    f"超时 ({elapsed:.1f}s) | POST 返回 202 但 SSE 无响应\n"
                    f"    服务端未处理请求，请检查 MCP Server 进程和日志",
                )
                return False

    except Exception as e:
        print_fail("initialize", f"{type(e).__name__}: {e}")
        return False

    return False


async def test_sdk_connect(url: str, token: str, timeout: float) -> bool:
    """Step 3: 用 MCP SDK 测试完整连接"""
    print("\n[Step 3] 测试 MCP SDK 完整连接")
    t0 = time.time()

    try:
        from mcp import ClientSession
        from mcp.client.sse import sse_client

        headers = {"token": token}
        print_info("SDK", f"mcp SDK 已导入 | headers={headers}")

        ctx = sse_client(url, headers=headers, timeout=timeout)
        try:
            read, write = await asyncio.wait_for(ctx.__aenter__(), timeout=timeout)
            print_ok("SSE", f"连接成功 ({time.time()-t0:.2f}s)")

            async with ClientSession(read, write) as session:
                print_info("握手", "initialize...")
                await asyncio.wait_for(session.initialize(), timeout=timeout)
                print_ok("握手", f"initialize 成功 ({time.time()-t0:.2f}s)")

                print_info("工具", "list_tools...")
                tools_result = await asyncio.wait_for(session.list_tools(), timeout=timeout)
                tool_names = [t.name for t in tools_result.tools]
                print_ok("工具", f"{tool_names} ({time.time()-t0:.2f}s)")

        finally:
            await ctx.__aexit__(None, None, None)
        return True

    except ImportError:
        print_fail("SDK", "mcp 包未安装，请执行: pip install mcp")
        return False
    except asyncio.TimeoutError:
        elapsed = time.time() - t0
        print_fail("SDK", f"超时 ({elapsed:.1f}s)")
        try:
            await ctx.__aexit__(None, None, None)
        except Exception:
            pass
        return False
    except Exception as e:
        print_fail("SDK", f"{type(e).__name__}: {e}")
        try:
            await ctx.__aexit__(None, None, None)
        except Exception:
            pass
        return False


async def test_tool_call(url: str, token: str, timeout: float) -> bool:
    """Step 4: 测试实际工具调用"""
    print("\n[Step 4] 测试工具调用 (add_memory + search_memory)")
    t0 = time.time()

    try:
        from mcp import ClientSession
        from mcp.client.sse import sse_client

        headers = {"token": token}
        ctx = sse_client(url, headers=headers, timeout=timeout)

        try:
            read, write = await asyncio.wait_for(ctx.__aenter__(), timeout=timeout)
        except asyncio.TimeoutError:
            print_fail("连接", "SSE 连接超时")
            return False

        try:
            async with ClientSession(read, write) as session:
                try:
                    await asyncio.wait_for(session.initialize(), timeout=timeout)
                except asyncio.TimeoutError:
                    print_fail("握手", "initialize 超时")
                    return False

                # 测试 add_memory
                print_info("add_memory", "写入测试记忆...")
                try:
                    result = await asyncio.wait_for(
                        session.call_tool(
                            "add_memory",
                            arguments={
                                "content": "这是一条测试记忆 - MCP 连接测试",
                                "user_id": "test_user",
                                "metadata": {"type": "test"},
                            },
                        ),
                        timeout=timeout,
                    )
                    if result.content and hasattr(result.content[0], "text"):
                        data = json.loads(result.content[0].text)
                        print_ok("add_memory", f"{data}")
                    else:
                        print_ok("add_memory", "调用成功（无返回内容）")
                except asyncio.TimeoutError:
                    print_fail("add_memory", f"超时 ({timeout}s)")
                except Exception as e:
                    print_fail("add_memory", f"{type(e).__name__}: {e}")

                # 测试 search_memory
                print_info("search_memory", "搜索测试记忆...")
                try:
                    result = await asyncio.wait_for(
                        session.call_tool(
                            "search_memory",
                            arguments={
                                "query": "测试记忆",
                                "user_id": "test_user",
                                "top_k": 3,
                            },
                        ),
                        timeout=timeout,
                    )
                    if result.content and hasattr(result.content[0], "text"):
                        data = json.loads(result.content[0].text)
                        count = len(data.get("results", []))
                        print_ok("search_memory", f"返回 {count} 条结果")
                        for i, item in enumerate(data.get("results", [])[:3]):
                            print_info(f"  [{i}]", f"{item.get('memory', '') or item.get('content', '')[:80]}")
                    else:
                        print_info("search_memory", "无返回内容")
                except asyncio.TimeoutError:
                    print_fail("search_memory", f"超时 ({timeout}s)")
                except Exception as e:
                    print_fail("search_memory", f"{type(e).__name__}: {e}")

        finally:
            await ctx.__aexit__(None, None, None)
        print_ok("完成", f"总耗时 {time.time()-t0:.2f}s")
        return True

    except ImportError:
        print_fail("SDK", "mcp 包未安装")
        return False
    except Exception as e:
        print_fail("测试", f"{type(e).__name__}: {e}")
        return False


async def main():
    parser = argparse.ArgumentParser(description="MCP Server 连接测试")
    parser.add_argument("--url", default=DEFAULT_URL, help="MCP SSE URL")
    parser.add_argument("--token", default=DEFAULT_TOKEN, help="token header 值")
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT, help="超时秒数")
    parser.add_argument("--test-call", action="store_true", help="测试实际工具调用")
    parser.add_argument("--step", type=int, choices=[1, 2, 3, 4], help="只运行指定步骤")
    args = parser.parse_args()

    print("=" * 60)
    print("MCP Server 连接测试")
    print("=" * 60)
    print(f"  URL:     {args.url}")
    print(f"  Token:   {args.token[:4]}***")
    print(f"  Timeout: {args.timeout}s")

    results = {}

    if args.step:
        steps = {args.step}
    elif args.test_call:
        steps = {1, 2, 3, 4}
    else:
        steps = {1, 2, 3}

    if 1 in steps:
        results["SSE连接"] = await test_raw_sse(args.url, args.token, args.timeout)

    if 2 in steps:
        results["MCP握手"] = await test_mcp_handshake(
            args.url, args.token, args.timeout
        )

    if 3 in steps:
        results["SDK连接"] = await test_sdk_connect(
            args.url, args.token, args.timeout
        )

    if 4 in steps:
        results["工具调用"] = await test_tool_call(
            args.url, args.token, args.timeout
        )

    # 汇总
    print("\n" + "=" * 60)
    print("测试结果汇总")
    print("=" * 60)
    all_ok = True
    for name, ok in results.items():
        status = "PASS" if ok else "FAIL"
        print(f"  [{status}] {name}")
        if not ok:
            all_ok = False

    if all_ok:
        print("\n所有测试通过!")
    else:
        print("\n存在失败项，请根据上方提示排查。")

    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
