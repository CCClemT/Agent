import asyncio
import sys
import json
from mcp_client import MCPClient

async def debug_agent_mcp_full(server_path: str):
    print("=" * 80)
    print("🔥 完整调试 Agent → MCP 调用全过程（打印所有返回值）")
    print("=" * 80)

    client = MCPClient()

    try:
        # ======================
        # 1. 连接
        # ======================
        print("\n[1/6] 连接 MCP 服务器...")
        await client.connect_to_server(server_path)
        print("✅ 连接成功")

        # ======================
        # 2. 打印所有工具（完整信息）
        # ======================
        print("\n[2/6] 所有 MCP 工具（原始返回）：")
        for idx, tool in enumerate(client.tools):
            print(f"  {idx+1}. 工具名: {tool.name}")
            print(f"     描述: {tool.description}")
            print(f"     输入Schema: {tool.inputSchema}")
            print("-" * 40)

        tool_names = [t.name for t in client.tools]
        print(f"\n✅ 工具名称列表: {tool_names}")

        # ======================
        # 3. 调用 get_all_strings（核心）
        # ======================
        print("\n[3/6] 调用工具: get_all_strings()")
        result = await client.session.call_tool(name="get_all_strings", arguments={})

        # ======================
        # 4. 打印 原始返回对象
        # ======================
        print("\n[4/6] 🧿 MCP 原始返回结果（全部内容）:")
        print(f"类型: {type(result)}")
        print(f"完整对象: {result}")

        # ======================
        # 5. 打印 content 内容（最关键）
        # ======================
        print("\n[5/6] 📦 content 列表内容：")
        if hasattr(result, 'content'):
            print(f"content 存在: {result.content}")
            for i, c in enumerate(result.content):
                print(f"content[{i}] = {c}")
                if hasattr(c, 'text'):
                    print(f"  → text = {c.text}")
        else:
            print("❌ 没有 content 属性！")

        # ======================
        # 6. 尝试解析 JSON
        # ======================
        print("\n[6/6] 尝试解析 JSON：")
        try:
            text = result.content[0].text
            print("提取 text:", text)
            data = json.loads(text)
            print("\n✅ JSON 解析成功！")
            print("最终数据:", data)
        except Exception as e:
            print("\n❌ JSON 解析失败：", e)

    except Exception as e:
        print("\n" + "="*80)
        print("❌ ❌ ❌ 调用完全失败！")
        print(f"失败原因: {e}")
        import traceback
        traceback.print_exc()
        print("="*80)
    finally:
        await client.cleanup()

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("使用方法:")
        print("   uv run debug_agent_mcp.py mcpserver.py")
        sys.exit(1)

    asyncio.run(debug_agent_mcp_full(sys.argv[1]))