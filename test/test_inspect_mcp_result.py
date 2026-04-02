import asyncio
import sys
from mcp_client import MCPClient

async def inspect_mcp_result(server_script_path: str):
    print("=" * 60)
    print("🧪 MCP 返回结果结构排查脚本（不修改任何源码）")
    print("=" * 60)

    # 1. 创建客户端
    client = MCPClient()

    try:
        # 2. 连接 MCP
        print("\n[1/5] 连接 MCP 服务器...")
        await client.connect_to_server(server_script_path)

        # 3. 确认工具存在
        print("\n[2/5] 检查工具列表...")
        tool_names = [t.name for t in client.tools]
        print(f"可用工具：{tool_names}")

        if "get_all_function_addresses" not in tool_names:
            print("❌ 工具不存在")
            return

        # 4. 直接调用，不经过包装，查看原始返回
        print("\n[3/5] 直接调用 call_tool，查看原始返回...")
        raw_result = await client.session.call_tool(
            name="get_all_function_addresses",
            arguments={}
        )

        # ==============================
        # 核心排查：打印返回值全部信息
        # ==============================
        print("\n" + "="*60)
        print("🔥 原始返回对象类型：", type(raw_result))
        print("🔥 完整对象：", raw_result)
        print("🔥 对象所有属性：", dir(raw_result))
        
        # 尝试所有可能的属性
        print("\n🔍 尝试读取常见属性：")
        for attr in ['result', 'value', 'content', 'data', 'output']:
            if hasattr(raw_result, attr):
                print(f"   ✅ {attr} = {getattr(raw_result, attr)}")
            else:
                print(f"   ❌ {attr} 不存在")

        print("\n✅ 排查完成！请把上面这段输出发给我")
        print("我会告诉你 mcp_client.py 正确怎么写！")
        print("="*60)

    except Exception as e:
        print(f"\n❌ 出错：{e}")
        import traceback
        traceback.print_exc()
    finally:
        print("\n[5/5] 清理资源...")
        await client.cleanup()

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("使用方法：")
        print("  python test_inspect_mcp_result.py <mcpserver.py路径>")
        sys.exit(1)

    asyncio.run(inspect_mcp_result(sys.argv[1]))