import os
import click
from openai import AsyncOpenAI
import asyncio
from mcp_client import MCPClient
import re
from typing import Tuple, List, Callable, Optional, Dict, Any
from string import Template
import ast
import platform
import inspect
import logging
import traceback

from utils import get_api_key
from prompt_template import react_system_prompt_template
from dotenv import load_dotenv

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("agent_debug.log", encoding="utf-8")
    ]
)
logger = logging.getLogger(__name__)


class ReActAgent:
    def __init__(self, tools: List[Callable], model: str, project_directory: str, debug: bool = True):
        self.tools = {func.__name__: func for func in tools}
        self.model = model
        self.project_directory = project_directory
        self.debug = debug
        self.client = AsyncOpenAI(
            base_url="https://api.deepseek.com",
            api_key=get_api_key(),
        )
        self.mcp_client = MCPClient()
        self.mcp_server_path = self.get_mcp_server_path()
        self.mcp_connected = False
        self.mcp_tools: Dict[str, Any] = {}
        
        # 测试模式标记
        self.test_mode = False
        self.test_responses = []

    async def run(self, user_input: str) -> str:
        """
        运行Agent处理用户输入
        :param user_input: 用户输入的任务
        :return: 处理结果
        """
        logger.info(f"开始处理任务: {user_input}")
        await self.connect_mcp_server()
        
        # 构建对话消息
        messages = [
            {"role": "system", "content": self.render_system_prompt(react_system_prompt_template)},
            {"role": "user", "content": f"<question>{user_input}</question>"},
        ]

        try:
            while True:
                # 请求模型
                if self.debug:
                    logger.info("\n【调试】正在请求模型...")
                    print("\n【调试】正在请求模型...")
                
                content = await self.call_model(messages)
                
                if self.debug:
                    logger.info(f"【调试】模型原始返回：\n{content}\n")
                    print(f"【调试】模型原始返回：\n{content}\n")

                # 检测 Thought
                thought_match = re.search(r"<thought>(.*?)</thought>", content, re.DOTALL)
                if thought_match:
                    thought = thought_match.group(1)
                    logger.info(f"\nThought: {thought}\n")
                    if self.debug:
                        print(f"\nThought: {thought}\n")
                
                # 检测是否为 Final Answer
                if "<final_answer>" in content:
                    final_answer = re.search(r"<final_answer>(.*?)</final_answer>", content, re.DOTALL)
                    if final_answer:
                        result = final_answer.group(1)
                        logger.info(f"任务完成，最终答案：{result}")
                        return result
                    else:
                        raise RuntimeError("找到final_answer标签但未匹配到内容")
                
                # 检测 Action
                action_match = re.search(r"<action>(.*?)</action>", content, re.DOTALL)
                if not action_match:
                    error_msg = "模型输出不合法,缺少<action>标签"
                    logger.error(error_msg)
                    raise RuntimeError(error_msg)
                
                action = action_match.group(1)
                tool_name, args = self.parse_action(action)
                
                # 调试信息打印
                if self.debug:
                    debug_info = {
                        "工具名称": tool_name,
                        "解析后的参数": args,
                        "参数类型": type(args),
                        "本地工具": list(self.tools.keys()),
                        "MCP已连接": self.mcp_connected,
                        "MCP工具": [t for t in self.mcp_tools]
                    }
                    logger.info(f"\n{'='*60}\n【⚠️ 调试：Agent 即将调用工具】")
                    for key, value in debug_info.items():
                        logger.info(f"{key}：{value}")
                    logger.info(f"{'='*60}\n")
                    
                    print("\n" + "="*60)
                    print("【⚠️ 调试：Agent 即将调用工具】")
                    for key, value in debug_info.items():
                        print(f"{key}：{value}")
                    print("="*60)

                # 测试模式下自动确认，非测试模式下终端命令需要用户确认
                if self.test_mode:
                    should_continue = "y"
                else:
                    should_continue = input("\n是否继续?(Y/N) ") if tool_name == "run_terminal_command" else "y"
                
                if should_continue.lower() != 'y':
                    logger.info("\n操作已取消。")
                    print("\n操作已取消。")
                    return "操作被用户取消"
                
                # 工具调用核心逻辑
                try:
                    observation = await self._call_tool(tool_name, args)
                except Exception as e:
                    error_detail = f"{type(e).__name__}: {e}"
                    logger.error(f"\n【❌ 工具调用失败！完整错误】：{error_detail}")
                    logger.error(traceback.format_exc())
                    
                    if self.debug:
                        print(f"\n【❌ 工具调用失败！完整错误】：{error_detail}")
                        traceback.print_exc()
                    
                    observation = f"工具执行出错: {error_detail}"
                
                logger.info(f"\nObservation: {observation}\n")
                if self.debug:
                    print(f"\nObservation: {observation}\n")
                
                obs_msg = f"<observation>{observation}</observation>"
                messages.append({"role": "user", "content": obs_msg})
                
                # 测试模式下记录响应
                if self.test_mode:
                    self.test_responses.append({
                        "tool": tool_name,
                        "args": args,
                        "observation": observation
                    })
                    
        except Exception as e:
            error_msg = f"Agent运行出错: {type(e).__name__}: {e}"
            logger.error(error_msg)
            logger.error(traceback.format_exc())
            if self.debug:
                print(f"\n【❌ Agent运行出错】：{error_msg}")
                traceback.print_exc()
            return error_msg

    async def _call_tool(self, tool_name: str, args: List[Any]) -> str:
        """
        内部工具调用方法，封装工具调用逻辑
        """
        # 本地工具调用
        if tool_name in self.tools:
            logger.info(f"【调试】使用本地工具：{tool_name}")
            if self.debug:
                print(f"【调试】使用本地工具：{tool_name}")
            
            # 确保参数是列表并解包
            if not isinstance(args, list):
                args = [args]
            observation = self.tools[tool_name](*args)
        
        # MCP工具调用
        elif tool_name in self.mcp_tools:
            logger.info(f"【调试】使用 MCP 工具：{tool_name}, 参数：{args}")
            if self.debug:
                print(f"【调试】使用 MCP 工具：{tool_name}, 参数：{args}")

            # MCP工具需要字典参数
            if isinstance(args, list) and len(args) == 1 and isinstance(args[0], dict):
                args_dict = args[0]
            elif isinstance(args, dict):
                args_dict = args
            else:
                try:
                    # 尝试将参数转换为字典
                    args_dict = dict(enumerate(args))
                    logger.warning(f"【调试】参数自动转换为字典：{args_dict}")
                    if self.debug:
                        print(f"【调试】参数自动转换为字典：{args_dict}")
                except:
                    args_dict = {}
                    logger.warning(f"【调试】参数转换失败，使用空字典：{args}")
                    if self.debug:
                        print(f"【调试】参数转换失败，使用空字典：{args}")

            observation = await self.mcp_client.call_tool(tool_name, args_dict)
        
        else:
            observation = f"错误：工具 {tool_name} 不存在"
            logger.error(observation)
        
        return str(observation)

    @staticmethod
    def get_mcp_server_path() -> Optional[str]:
        """从.env文件中加载MCP_SERVER_PATH的值"""
        load_dotenv()
        return os.getenv("MCP_SERVER_PATH")

    async def connect_mcp_server(self):
        """连接MCP服务器"""
        if not self.mcp_server_path:
            warning_msg = "\nMCP服务器路径未配置(.env文件中MCP_SERVER_PATH为空),连接MCP失败\n"
            logger.warning(warning_msg)
            if self.debug:
                print(warning_msg)
            self.mcp_connected = False
            return
        
        try:
            await self.mcp_client.connect_to_server(self.mcp_server_path)
            self.mcp_tools = {tool.name: tool for tool in self.mcp_client.tools}
            self.mcp_connected = True
            logger.info(f"MCP服务器连接成功，加载到 {len(self.mcp_tools)} 个工具")
            if self.debug:
                print(f"\nMCP服务器连接成功，加载到 {len(self.mcp_tools)} 个工具\n")
        except Exception as e:
            error_msg = f"\nMCP 连接失败：{e}"
            logger.error(error_msg)
            if self.debug:
                print(error_msg)
            self.mcp_connected = False
        finally:
            try:
                await self.mcp_client.cleanup()
            except Exception as e:
                logger.warning(f"MCP清理失败：{e}")

    async def call_model(self, messages: List[Dict[str, str]]) -> str:
        """调用LLM模型"""
        logger.info("\n正在请求模型,请稍等...\n")
        if self.debug:
            print("\n正在请求模型,请稍等...\n")
        
        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=0.7,
                max_tokens=2000
            )
            content = response.choices[0].message.content
            messages.append({"role": "assistant", "content": content})
            return content
        except Exception as e:
            error_msg = f"模型调用失败: {e}"
            logger.error(error_msg)
            raise RuntimeError(error_msg)

    def parse_action(self, code_str: str) -> Tuple[str, List[Any]]:
        """
        解析Action中的函数调用
        :param code_str: 函数调用字符串
        :return: (函数名, 参数列表)
        """
        # 清理字符串
        code_str = code_str.strip()
        match = re.match(r'(\w+)\((.*)\)', code_str, re.DOTALL)
        
        if not match:
            logger.error(f"无效的函数调用语法: {code_str}")
            raise ValueError(f"Invalid function call syntax: {code_str}")

        func_name = match.group(1)
        args_str = match.group(2).strip()

        # 空参数
        if not args_str:
            return func_name, []

        # 解析参数
        args = []
        try:
            # 使用ast解析更复杂的参数
            parsed_args = ast.parse(f"f({args_str})", mode='eval').body.args
            for arg in parsed_args:
                args.append(ast.literal_eval(arg))
        except:
            # 备用的手动解析逻辑
            logger.warning("使用备用参数解析逻辑")
            args = self._manual_parse_args(args_str)
        
        logger.info(f"解析出函数 {func_name} 的参数：{args}")
        return func_name, args

    def _manual_parse_args(self, args_str: str) -> List[Any]:
        """手动解析参数，兼容复杂字符串"""
        args = []
        current_arg = ""
        in_string = False
        string_char = None
        paren_depth = 0
        bracket_depth = 0
        brace_depth = 0
        
        i = 0
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
                elif char == '[':
                    bracket_depth += 1
                    current_arg += char
                elif char == ']':
                    bracket_depth -= 1
                    current_arg += char
                elif char == '{':
                    brace_depth += 1
                    current_arg += char
                elif char == '}':
                    brace_depth -= 1
                    current_arg += char
                elif char == ',' and paren_depth == 0 and bracket_depth == 0 and brace_depth == 0:
                    # 顶层逗号，分割参数
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
        
        return args

    def _parse_single_arg(self, arg_str: str) -> Any:
        """解析单个参数"""
        arg_str = arg_str.strip()
        
        # 空参数
        if not arg_str:
            return ""
        
        # 字符串字面量
        if (arg_str.startswith('"') and arg_str.endswith('"')) or \
           (arg_str.startswith("'") and arg_str.endswith("'")):
            try:
                return ast.literal_eval(arg_str)
            except:
                # 手动处理转义
                inner_str = arg_str[1:-1]
                inner_str = inner_str.replace('\\"', '"').replace("\\'", "'")
                inner_str = inner_str.replace('\\n', '\n').replace('\\t', '\t')
                inner_str = inner_str.replace('\\r', '\r').replace('\\\\', '\\')
                return inner_str
        
        # 尝试解析其他类型
        try:
            return ast.literal_eval(arg_str)
        except (SyntaxError, ValueError):
            # 解析失败返回原始字符串
            return arg_str

    def get_tool_list(self) -> str:
        """生成工具列表说明"""
        tool_descriptions = []
        for func in self.tools.values():
            name = func.__name__
            signature = str(inspect.signature(func))
            doc = inspect.getdoc(func) or "无说明"
            tool_descriptions.append(f"- {name}{signature}: {doc}")
        return "\n".join(tool_descriptions)

    def render_system_prompt(self, system_prompt_template: str) -> str:
        """渲染系统提示词"""
        tool_list = self.get_tool_list()
        
        # MCP工具列表
        mcp_tool_list = []
        if self.mcp_connected and self.mcp_tools:
            mcp_tool_list = [f"{tool}" for tool in self.mcp_tools]
        mcp_tool_str = ", ".join(mcp_tool_list) if mcp_tool_list else ""

        # 生成文件列表
        try:
            file_list = ", ".join(
                os.path.abspath(os.path.join(self.project_directory, f)).replace("\\", "/")
                for f in os.listdir(self.project_directory)
                if os.path.isfile(os.path.join(self.project_directory, f))
            )
        except:
            file_list = "无法获取文件列表"

        # 渲染模板
        return Template(system_prompt_template).substitute(
            operating_system=self.get_operating_system_name(),
            tool_list=tool_list,
            file_list=file_list,
            mcp_tool_list=mcp_tool_str
        )
    
    def get_operating_system_name(self) -> str:
        """获取操作系统名称"""
        os_map = {
            "Darwin": "macOS",
            "Windows": "Windows",
            "Linux": "Linux"
        }
        return os_map.get(platform.system(), "Unknown")

    def set_test_mode(self, enable: bool = True):
        """设置测试模式"""
        self.test_mode = enable
        self.test_responses = []
        logger.info(f"测试模式{'已启用' if enable else '已禁用'}")

    def get_test_responses(self) -> List[Dict[str, Any]]:
        """获取测试模式下的响应记录"""
        return self.test_responses.copy()


# 工具函数
def read_file(file_path: str) -> str:
    """
    读取文件内容
    :param file_path: 文件路径
    :return: 文件内容
    """
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
        logger.info(f"成功读取文件: {file_path}")
        return content
    except Exception as e:
        error_msg = f"读取文件失败: {e}"
        logger.error(error_msg)
        return error_msg

def write_to_file(file_path: str, content: str) -> str:
    """
    写入内容到文件
    :param file_path: 文件路径
    :param content: 要写入的内容
    :return: 操作结果
    """
    try:
        # 确保目录存在
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(content)
        logger.info(f"成功写入文件: {file_path}")
        return "写入成功"
    except Exception as e:
        error_msg = f"写入文件失败: {e}"
        logger.error(error_msg)
        return error_msg

def run_terminal_command(command: str) -> str:
    """
    执行终端命令
    :param command: 要执行的命令
    :return: 执行结果
    """
    import subprocess
    logger.info(f"执行终端命令: {command}")
    try:
        result = subprocess.run(
            command, 
            shell=True, 
            capture_output=True, 
            text=True,
            timeout=30  # 设置超时
        )
        if result.returncode == 0:
            return f"执行成功:\n{result.stdout}"
        else:
            return f"执行失败:\n{result.stderr}"
    except subprocess.TimeoutExpired:
        return "命令执行超时（30秒）"
    except Exception as e:
        return f"命令执行出错: {e}"

# 测试函数
def test_agent_basic_functions(project_dir: str):
    """
    测试Agent基本功能
    :param project_dir: 测试用的项目目录
    """
    logger.info("开始运行Agent测试...")
    print("\n=== 开始运行Agent测试 ===\n")
    
    # 创建测试Agent实例
    tools = [read_file, write_to_file, run_terminal_command]
    agent = ReActAgent(tools=tools, model="deepseek-chat", project_directory=project_dir, debug=True)
    
    # 启用测试模式
    agent.set_test_mode(True)
    
    # 测试1: 参数解析
    test_cases = [
        ('read_file("test.txt")', ('read_file', ['test.txt'])),
        ('write_to_file("output.txt", "hello")', ('write_to_file', ['output.txt', 'hello'])),
        ('run_terminal_command("ls -l")', ('run_terminal_command', ['ls -l'])),
    ]
    
    print("\n1. 测试参数解析...")
    for code_str, expected in test_cases:
        try:
            func_name, args = agent.parse_action(code_str)
            assert (func_name, args) == expected
            print(f"✓ {code_str} - 解析成功")
        except Exception as e:
            print(f"✗ {code_str} - 解析失败: {e}")
    
    # 测试2: 系统提示词渲染
    print("\n2. 测试系统提示词渲染...")
    try:
        prompt = agent.render_system_prompt(react_system_prompt_template)
        assert "tool_list" in prompt or "工具列表" in prompt
        assert agent.get_operating_system_name() in prompt
        print("✓ 系统提示词渲染成功")
    except Exception as e:
        print(f"✗ 系统提示词渲染失败: {e}")
    
    # 测试3: 工具列表生成
    print("\n3. 测试工具列表生成...")
    try:
        tool_list = agent.get_tool_list()
        assert "read_file" in tool_list
        assert "write_to_file" in tool_list
        assert "run_terminal_command" in tool_list
        print("✓ 工具列表生成成功")
    except Exception as e:
        print(f"✗ 工具列表生成失败: {e}")
    
    print("\n=== 测试完成 ===\n")
    logger.info("Agent测试完成")


@click.command()
@click.argument("project_directory", type=click.Path(exists=True))
@click.option("--test", is_flag=True, help="运行测试模式")
@click.option("--debug/--no-debug", default=True, help="启用/禁用调试模式")
def main(project_directory: str, test: bool, debug: bool):
    """
    ReAct Agent主程序
    :param project_directory: 项目目录路径
    :param test: 是否运行测试
    :param debug: 是否启用调试模式
    """
    project_dir = os.path.abspath(project_directory)
    logger.info(f"项目目录: {project_dir}")
    
    # 运行测试
    if test:
        test_agent_basic_functions(project_dir)
        return
    
    # 正常运行模式
    tools = [read_file, write_to_file, run_terminal_command]
    agent = ReActAgent(tools=tools, model="deepseek-chat", project_directory=project_dir, debug=debug)
    
    print("\n=== ReAct Agent 已启动 ===")
    print("输入 'exit' 或 'quit' 退出程序")
    print("项目目录:", project_dir)
    print("==========================\n")
    
    while True:
        try:
            task = input("请输入任务: ").strip()
            if not task:
                continue
            
            if task.lower() in ["exit", "quit"]:
                print("\n退出程序。")
                logger.info("用户退出程序")
                break
            
            # 运行Agent
            result = asyncio.run(agent.run(task))
            print(f"\n最终结果: {result}\n")
            
        except KeyboardInterrupt:
            print("\n\n程序被用户中断")
            logger.info("程序被用户中断")
            break
        except Exception as e:
            error_msg = f"\n程序运行出错: {e}"
            logger.error(error_msg)
            print(error_msg)
            continue


# 单元测试兼容
if __name__ == "__main__":
    # 支持命令行运行
    main()
elif __name__ == "test":
    # 支持单元测试框架调用
    test_dir = os.path.dirname(os.path.abspath(__file__))
    test_agent_basic_functions(test_dir)