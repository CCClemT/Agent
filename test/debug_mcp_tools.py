import sys
import os

# 关键：让 test 目录能找到上级的 agent.py 和 mcp_client.py
sys.path.append(os.path.abspath(".."))

import asyncio
from mcp_client import MCPClient
from dotenv import load_dotenv


async def debug_mcp_tools():
    print("=" * 60)
    print("🧪 DEBUG: MCP 工具详细信息")
    print("=" * 60)

    # 加载环境变量
    load_dotenv()
    mcp_server_path = os.getenv("MCP_SERVER_PATH")

    if not mcp_server_path:
        print("❌ 未配置 MCP_SERVER_PATH，请检查 .env 文件")
        return

    print(f"🔌 MCP 服务器路径: {mcp_server_path}")
    print("⏳ 正在连接 MCP 服务器...\n")

    # 创建 MCP 客户端并连接
    client = MCPClient()

    try:
        await client.connect_to_server(mcp_server_path)
        print(f"✅ MCP 连接成功！共获取 {len(client.tools)} 个工具\n")

        # 遍历输出所有工具的【完整详细信息】
        for idx, tool in enumerate(client.tools, 1):
            print(f"📌 工具 {idx}: {tool.name}")
            print(f"   描述: {tool.description or '无说明'}")
            
            print("   入参 Schema:")
            props = tool.inputSchema.get("properties", {})
            for param_name, param_info in props.items():
                typ = param_info.get("type", "unknown")
                default = param_info.get("default", "无默认值")
                print(f"     - {param_name}: {typ} (默认: {default})")

            print("   完整 Tool 对象:")
            print(f"     {tool}\n")

    except Exception as e:
        print(f"❌ MCP 连接失败: {e}")
    finally:
        await client.cleanup()

    print("=" * 60)
    print("✅ 调试完成")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(debug_mcp_tools())