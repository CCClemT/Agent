import os
import click
from openai import AsyncOpenAI
import asyncio
from mcp_client import MCPClient
import re
from typing import Tuple, List, Callable
from string import Template
import ast
import platform
import inspect

from utils import get_api_key
from prompt_template import react_system_prompt_template
from dotenv import load_dotenv


class ReActAgent:
    def __init__(self, tools: List[Callable], model: str, project_directory: str):
        self.tools = { func.__name__: func for func in tools}
        #将工具列表转换为一个字典,函数名:函数自身
        self.model = model
        self.project_directory = project_directory
        self.client = AsyncOpenAI(
        #调用对话api
            base_url="https://api.deepseek.com",
            api_key=get_api_key(),
        )
        #初始化MCP客户端
        self.mcp_client = MCPClient()
        self.mcp_server_path = ReActAgent.get_mcp_server_path()
        self.mcp_connected = False
        self.mcp_tools = {}

    async def run(self, user_input: str):
        await self.connect_mcp_server()
        #构建对话消息
        messages = [
            {"role": "system", "content": self.render_system_prompt(react_system_prompt_template)},
            #读取系统提示词
            {"role": "user", "content": f"<question>{user_input}</question>"},
        ]

        while True:

            #请求模型
            content = await self.call_model(messages)

            #检测Thought
            tought_match = re.search(r"<thought>(.*?)</thought>", content, re.DOTALL)
            if tought_match:
                thought = tought_match.group(1)
                print(f"\nThought: {thought}\n")
            
            #检测是否为Final Answer,是则输出最终答案
            if "<final_answer>" in content:
                final_answer = re.search(r"<final_answer>(.*?)</final_answer>", content, re.DOTALL)
                return final_answer.group(1)
            
            #检测Action
            action_match = re.search(r"<action>(.*?)</action>", content, re.DOTALL)
            if not action_match:
                raise RuntimeError("模型输出不合法,缺少<action>标签")
            action = action_match.group(1)
            tool_name,args = self.parse_action(action)
            print(f"\n Action: {tool_name}({', '.join(args)})\n")
            # 只有终端命令才需要询问用户,其他的工具直接执行
            should_continue = input(f"\n\n是否继续?(Y/N)") if tool_name == "run_terminal_command" else "y"
            if should_continue.lower() != 'y':
                print("\n\n操作已取消。\n")
                return "操作被用户取消"
            
            try:
                observation = self.tools[tool_name](*args)
            except Exception as e:
                observation = f"工具执行出错:{str(e)}"
            print(f"\n Observation: {observation}\n")
            obs_msg = f"<observation>{observation}</observation>"
            messages.append({"role": "user", "content": obs_msg})
            #print(f"\n当前消息列表: {messages}\n")
    
    @staticmethod
    def get_mcp_server_path():
        #从.env文件中加载MCP_SERVER_PATH的值。
        load_dotenv()
        return os.getenv("MCP_SERVER_PATH")

    async def connect_mcp_server(self):
        # 检查MCP服务器路径是否配置
        if not self.mcp_server_path:
            print("\nMCP服务器路径未配置(.env文件中MCP_SERVER_PATH为空),连接MCP失败\n")
            self.mcp_connected = False
            return
        try:
            await self.mcp_client.connect_to_server(self.mcp_server_path)
            # 获取 MCP 工具
            mcp_tool_list = self.mcp_client.tools
            # 把 MCP 工具 合并到 self.tools
            added = 0
            for tool in mcp_tool_list:
                tool_name = tool.name
                if tool_name not in self.tools:
                    self.tools[tool_name] = tool  # 加入主工具列表
                    added += 1
            self.mcp_connected = True
            print(f"\nMCP 连接成功，已添加 {added} 个工具到 agent.tools")
        except Exception as e:
            print(f"\nMCP 连接失败：{e}")
            self.mcp_connected = False
        finally:
            try:
                await self.mcp_client.cleanup()
            except:
                pass

    async def call_model(self, message):
        print(f"\n正在请求模型,请稍等...\n")
        response = await self.client.chat.completions.create(
            model=self.model,
            messages=message,
        )
        content = response.choices[0].message.content
        message.append({"role": "assistant", "content": content})
        return content
    

    def parse_action(self, code_str: str) -> Tuple[str, List[str]]:
        match = re.match(r'(\w+)\((.*)\)', code_str, re.DOTALL)
        if not match:
            raise ValueError("Invalid function call syntax")

        func_name = match.group(1)
        args_str = match.group(2).strip()

        # 手动解析参数,特别处理包含多行内容的字符串
        args = []
        current_arg = ""
        in_string = False
        string_char = None
        i = 0
        paren_depth = 0
        
        while i < len(args_str):
            char = args_str[i]
            
            if not in_string:
                if char in ['"', "'"]:
                    in_string = True
                    string_char = char
                    current_arg += char
                elif char == '(':
                    paren_depth += 1
                    current_arg += char
                elif char == ')':
                    paren_depth -= 1
                    current_arg += char
                elif char == ',' and paren_depth == 0:
                    # 遇到顶层逗号,结束当前参数
                    args.append(self._parse_single_arg(current_arg.strip()))
                    current_arg = ""
                else:
                    current_arg += char
            else:
                current_arg += char
                if char == string_char and (i == 0 or args_str[i-1] != '\\'):
                    in_string = False
                    string_char = None
            
            i += 1
        
        # 添加最后一个参数
        if current_arg.strip():
            args.append(self._parse_single_arg(current_arg.strip()))
        
        return func_name, args

    
    def _parse_single_arg(self, arg_str: str):
        """解析单个参数"""
        arg_str = arg_str.strip()
        
        # 如果是字符串字面量
        if (arg_str.startswith('"') and arg_str.endswith('"')) or \
           (arg_str.startswith("'") and arg_str.endswith("'")):
            # 移除外层引号并处理转义字符
            inner_str = arg_str[1:-1]
            # 处理常见的转义字符
            inner_str = inner_str.replace('\\"', '"').replace("\\'", "'")
            inner_str = inner_str.replace('\\n', '\n').replace('\\t', '\t')
            inner_str = inner_str.replace('\\r', '\r').replace('\\\\', '\\')
            return inner_str
        
        # 尝试使用 ast.literal_eval 解析其他类型
        try:
            return ast.literal_eval(arg_str)
        except (SyntaxError, ValueError):
            # 如果解析失败,返回原始字符串
            return arg_str

    def get_tool_list(self) -> str:
        """生成工具列表：本地 + MCP 已经全部在 self.tools 里"""
        tool_descriptions = []
        for func in self.tools.values():
            name = func.__name__
            signature = str(inspect.signature(func))
            doc = inspect.getdoc(func) or "无说明"
            tool_descriptions.append(f"- {name}{signature}: {doc}")
        return "\n".join(tool_descriptions)

    def render_system_prompt(self, system_prompt_template: str)-> str:
        # 渲染系统提示词,替换占位符
        tool_list = self.get_tool_list()
        # 生成文件列表时,将反斜杠替换为正斜杠
        file_list = ", ".join(
            os.path.abspath(os.path.join(self.project_directory, f)).replace("\\", "/")
            for f in os.listdir(self.project_directory)
        )
        return Template(system_prompt_template).substitute(
            operating_system=self.get_operating_system_name(),
            tool_list=tool_list,
            file_list=file_list
        )
    
    def get_operating_system_name(self):
        os_map = {
            "Darwin": "macOS",
            "Windows": "Windows",
            "Linux": "Linux"
        }

        return os_map.get(platform.system(), "Unknown")

def read_file(file_path):
    with open(file_path, "r", encoding="utf-8") as f:
        return f.read()

def write_to_file(file_path, content):
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(content)
    return "写入成功"

def run_terminal_command(command):
    import subprocess
    result = subprocess.run(command, shell=True, capture_output=True, text=True)
    return "执行成功" if result.returncode == 0 else result.stderr

@click.command()
@click.argument("project_directory", type=click.Path(exists=True))
def main(project_directory):
    #用于标记一个函数为命令行接口的入口点,并指定一个参数project_directory,要求它是一个存在的路径。
    project_dir = os.path.abspath(project_directory)
    #获取文件路径的绝对路径,并将其存储在变量project_dir中。
    
    tools = [read_file, write_to_file, run_terminal_command]
    agent = ReActAgent(tools = tools, model="deepseek-chat", project_directory=project_dir)
    while True:
        task = input("请输入任务:")

        asyncio.run(agent.run(task))

        if task.lower() in ["exit", "quit"]:
            print("退出程序。")
            break




if __name__ == "__main__":
    main()