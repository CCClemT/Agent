import asyncio
import sys
import json
from typing import Optional
from contextlib import AsyncExitStack
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from openai import OpenAI
from dotenv import load_dotenv
from utils import get_api_key

load_dotenv()

class MCPClient:
    def __init__(self):
        self.session: Optional[ClientSession] = None
        self.exit_stack = AsyncExitStack()
        self.client = OpenAI(
            base_url="https://api.deepseek.com",
            api_key=get_api_key()
        )        
        self.tools = []
        self.stdio = None
        self.write = None

    async def connect_to_server(self, server_script_path: str):
        """连接到 MCP 服务器，保持长连接不掉线"""
        if self.session:
            return  # 已连接，直接返回

        is_python = server_script_path.endswith('.py')
        is_js = server_script_path.endswith('.js')
        if not (is_python or is_js):
            raise ValueError("Server script must be a .py or .js file")

        command = "python" if is_python else "node"
        server_params = StdioServerParameters(
            command=command,
            args=[server_script_path],
            env=None
        )

        # 持有连接
        stdio_transport = await self.exit_stack.enter_async_context(stdio_client(server_params))
        self.stdio, self.write = stdio_transport
        self.session = await self.exit_stack.enter_async_context(ClientSession(self.stdio, self.write))
        
        await self.session.initialize()
        response = await self.session.list_tools()
        self.tools = response.tools
        print(f"连接到 MCP 服务器成功")

    async def call_tool(self, tool_name: str, params: dict) -> dict:
        """调用 MCP 服务器中的指定工具"""
        if not self.session:
            raise RuntimeError("未连接到 MCP 服务器")

        tool_names = [t.name for t in self.tools]
        if tool_name not in tool_names:
            raise ValueError(f"工具 {tool_name} 不存在，可用工具：{tool_names}")

        try:
            # 1. 调用 MCP 工具
            result = await self.session.call_tool(name=tool_name, arguments=params)
            # 2. 取值：content[0].text
            text = result.content[0].text
            # 3. 自动解析 JSON
            return json.loads(text)

        except Exception as e:
            raise RuntimeError(f"MCP工具调用失败: {str(e)}")

    def get_tools_openai_format(self):
        """转换为 OpenAI 函数调用格式（给 agent 使用）"""
        openai_tools = []
        for tool in self.tools:
            openai_tools.append({
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.inputSchema
                }
            })
        return openai_tools

async def main():
    if len(sys.argv) < 2:
        print("Usage: python mcp_client.py <server_path>")
        sys.exit(1)
    client = MCPClient()

    await client.connect_to_server(sys.argv[1])
    print("可用工具：", [tool.name for tool in client.tools])



if __name__ == "__main__":
    asyncio.run(main())