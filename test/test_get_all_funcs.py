import asyncio
from typing import Dict, Any
import httpx

# 复制原函数（保持和原代码逻辑一致）
async def get_all_function_addresses(plugin_host: str = "127.0.0.1", plugin_port: int = 13337) -> Dict[str, Any]:
    """
    调用IDA MCP插件，获取当前加载二进制文件的所有函数名和对应首地址
    
    Args:
        plugin_host (str): 可选参数，插件RPC服务地址，默认127.0.0.1
        plugin_port (int): 可选参数，插件RPC服务端口，默认13337
    
    Returns:
        Dict[str, Any]: 
            - 成功：{"func_count": 函数总数, "functions": [{"func_ea": 函数首地址, "func_name": 函数名}]}
            - 失败：{"error": 错误描述（如"未加载二进制文件/插件调用失败"）}
    """
    # 调用插件新增的 /get_all_func_ea 接口，仅需POST空JSON
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                url=f"http://{plugin_host}:{plugin_port}/get_all_func_ea",
                json={}  # 无输入参数，传空JSON符合插件解析逻辑
            )
            response.raise_for_status()  # 捕获4xx/5xx HTTP错误
            return response.json()
    except httpx.HTTPStatusError as e:
        return {"error": f"HTTP请求失败（状态码{response.status_code}）：{str(e)}"}
    except Exception as e:
        return {"error": f"调用插件失败：{str(e)}"}

# 测试主函数
async def test_get_all_function_addresses():
    """测试获取所有函数地址的函数，并格式化输出结果"""
    print("=" * 60)
    print("开始测试 get_all_function_addresses 函数")
    print("=" * 60)
    
    # 配置插件地址和端口（可根据实际情况修改）
    plugin_host = "127.0.0.1"
    plugin_port = 13337
    
    try:
        # 调用测试函数
        result = await get_all_function_addresses()
        
        # 格式化输出结果
        print(f"\n🔌 调用参数：")
        print(f"  - 插件地址: {plugin_host}")
        print(f"  - 插件端口: {plugin_port}")
        
        print(f"\n📊 响应结果：")
        if "error" in result:
            # 失败场景
            print(f"  ❌ 调用失败: {result['error']}")
        else:
            # 成功场景
            print(f"  ✅ 调用成功")
            print(f"  📈 函数总数: {result.get('func_count', 0)}")
            print(f"\n  📋 函数列表（前10个，避免输出过长）:")
            
            # 提取函数列表并展示前10个
            functions = result.get("functions", [])
            for idx, func in enumerate(functions[:10], 1):
                func_ea = func.get("func_ea", "未知地址")
                func_name = func.get("func_name", "未知名称")
                print(f"    {idx:2d}. 地址: {func_ea:<15} 名称: {func_name}")
            
            # 如果有更多函数，提示总数
            if len(functions) > 10:
                print(f"    ... 共 {len(functions)} 个函数，仅展示前10个")
                
    except Exception as e:
        print(f"\n  🚨 测试过程异常: {str(e)}")
    
    print("\n" + "=" * 60)
    print("测试结束")
    print("=" * 60)

# 运行测试
if __name__ == "__main__":
    # 适配不同Python版本的异步运行方式
    try:
        asyncio.run(test_get_all_function_addresses())
    except AttributeError:
        # Python 3.6及以下版本兼容
        loop = asyncio.get_event_loop()
        loop.run_until_complete(test_get_all_function_addresses())