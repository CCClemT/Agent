import os
import click
from openai import OpenAI

from dotenv import load_dotenv

from prompt_template import react_system_prompt_template


class ReActAgent:
    def __init__(self, tools: list[callable], model: str, project_directory: str):
        self.tools = { func.__name__: func for func in tools}
        #将工具列表转换为一个字典，函数名:函数自身
        self.model = model
        self.project_directory = project_directory
        self.client = OpenAI(
        #调用对话api
            base_url="https://api.deepseek.com",
            api_key=ReActAgent.get_api_key(),
        )
    
    def run(self, user_input: str):
        #构建对话消息
        messages = [
            {"role": "system", "content": self.render_system_prompt(react_system_prompt_template)},
            #读取系统提示词
            {"role": "user", "content": f"Task: {user_input}\nAvailable tools: {', '.join(self.tools.keys())}"},
        ]
        response = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            stream=False
        )
        return response.choices[0].message.content

    @staticmethod
    def get_api_key():
        #从.env文件中加载DEEPSEEK_API_KEY的值。
        load_dotenv()
        return os.getenv("DEEPSEEK_API_KEY")
    
    def get_tool_list(self):
        #生成工具列表字符串，包含函数签名和简要说明
        pass

    def render_system_prompt(self, template: str)-> str:
        #渲染系统提示词，替换占位符
        tool_list = self.get_tool_list()
        file_list = ", ".join(os.path.abspath(os.path.join(self.project_directory, f))
            for f in os.listdir(self.project_directory)
        )


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
    #用于标记一个函数为命令行接口的入口点，并指定一个参数project_directory，要求它是一个存在的路径。
    project_dir = os.path.abspath(project_directory)
    #获取文件路径的绝对路径，并将其存储在变量project_dir中。
    
    tools = [read_file, write_to_file, run_terminal_command]
    agent = ReActAgent()


    task = input("请输入任务：")



if __name__ == "__main__":
    main()