from dotenv import load_dotenv
import os

def get_api_key():
    #从.env文件中加载DEEPSEEK_API_KEY的值。
    load_dotenv()
    return os.getenv("DEEPSEEK_API_KEY")