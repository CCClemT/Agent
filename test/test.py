import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))

from openai import OpenAI
import agent

client = OpenAI(
            base_url="https://api.deepseek.com",
            api_key=agent.ReActAgent.get_api_key(),
        )

response = client.chat.completions.create(
    model="deepseek-chat",
    messages=[
        {"role": "system", "content": "You are a helpful assistant"},
        {"role": "user", "content": "Hello"},
    ],
    stream=False
)

print(response.choices[0].message.content)