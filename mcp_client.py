import asyncio
import sys
from typing import Optional
from contextlib import AsyncExitStack

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from openai import OpenAI
from dotenv import load_dotenv
from agent import ReActAgent

load_dotenv()

class MCPClient:
    def __init__(self):
        self.session: Optional[ClientSession] = None
        self.exit_stack = AsyncExitStack()
        #self.client = AsyncOpenAI()
        self.client = OpenAI(
            base_url="https://api.deepseek.com",
            api_key=ReActAgent.get_api_key()
        )        
        self.tools = []  # 初始化工具列表
        self.stdio = None
        self.write = None

    async def connect_to_server(self, server_script_path: str):
        """连接到 MCP 服务器并加载工具列表"""
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

        stdio_transport = await self.exit_stack.enter_async_context(stdio_client(server_params))
        self.stdio, self.write = stdio_transport
        self.session = await self.exit_stack.enter_async_context(ClientSession(self.stdio, self.write))

        await self.session.initialize()
        response = await self.session.list_tools()
        self.tools = response.tools

    async def call_tool(self, tool_name: str, params: dict) -> dict:
        """调用 MCP 服务器中的指定工具"""
        if not self.session:
            raise RuntimeError("未连接到 MCP 服务器")
        
        tool_names = [t.name for t in self.tools]
        if tool_name not in tool_names:
            raise ValueError(f"工具 {tool_name} 不存在，可用工具：{tool_names}")
        
        result = await self.session.call_tool(tool_name=tool_name, arguments=params)
        return result.result

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

    async def cleanup(self):
        """清理连接资源"""
        try:
            await self.exit_stack.aclose()
        except Exception:
            pass

async def main():
    if len(sys.argv) < 2:
        print("Usage: python mcp_client.py <server_path>")
        sys.exit(1)

    client = MCPClient()
    try:
        await client.connect_to_server(sys.argv[1])
        print("可用工具：", [tool.name for tool in client.tools])
    finally:
        await client.cleanup()

if __name__ == "__main__":
    asyncio.run(main())