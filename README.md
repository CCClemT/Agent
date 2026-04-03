## 使用

### 安装依赖

```python
pip install -r requirements.txt
```

### 配置环境变量

创建.env文件，添加以下配置

```python
# DeepSeek API 密钥
API_KEY=your_deepseek_api_key_here

# MCP 服务器脚本路径（可选，如不需要MCP可留空）
MCP_SERVER_PATH=/path/to/your/mcp/server.py  # 或 .js 文件
```

### 使用方法

```bash
# 启动 Agent，指定工作目录
python agent.py /path/to/your/project_directory
```

