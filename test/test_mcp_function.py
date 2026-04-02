import asyncio
import sys
import json
from mcp_client import MCPClient

async def test_mcp_function_final(server_script_path: str):
    print("=" * 60)
    print("✅ MCP 工具调用最终版（已适配真实返回结构）")
    print("=" * 60)

    client = MCPClient()

    try:
        # 连接
        print("\n[1/4] 连接 MCP 服务器...")
        await client.connect_to_server(server_script_path)

        # 调用工具（不封装，直接取原始结构）
        print("\n[2/4] 调用 get_all_function_addresses...")
        result = await client.session.call_tool(
            name="get_all_function_addresses",
            arguments={}
        )

        # ==============================
        # ✅ 正确取值（根据你真实的结构）
        # ==============================
        text_content = result.content[0].text
        data = json.loads(text_content)

        # 输出结果
        print("\n[3/4] 调用成功！解析结果：")
        print(f"✅ 函数总数：{data.get('func_count')}")
        print(f"✅ 前5个函数：")
        for i, func in enumerate(data.get('functions', [])[:5]):
            print(f"  {i+1}. {func['func_ea']} -> {func['func_name']}")

        print("\n🎉 全部正常运行！")

    except Exception as e:
        print(f"\n❌ 错误：{e}")
        import traceback
        traceback.print_exc()
    finally:
        print("\n[4/4] 清理资源...")
        await client.cleanup()

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("使用：python test_mcp_function_final.py <mcpserver.py>")
        sys.exit(1)

    asyncio.run(test_mcp_function_final(sys.argv[1]))