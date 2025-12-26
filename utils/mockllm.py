"""
模拟 LLM 模块

提供一个模拟的 LLM 实现，用于测试和调试。
用户可以手动输入响应，而不需要真正调用 API。

使用场景：
- 调试 Agent 逻辑时不想花费 API 费用
- 测试 Agent 在特定响应下的行为
- 手动控制 Agent 的决策过程

使用方法：
    mock_llm = MockLLM()
    response = await mock_llm("你好，介绍一下自己")
    # 然后在控制台手动输入响应
"""

import asyncio


class MockLLM:
    """
    模拟 LLM 类
    
    将提示词打印到控制台，然后等待用户手动输入响应。
    
    使用示例：
        mock_llm = MockLLM(name="测试LLM")
        response = await mock_llm("这是提示词")
        # 在控制台看到提示词后，输入你想要的响应
        # 输入空行结束
    """
    
    def __init__(self, name="MockLLM"):
        """
        初始化模拟 LLM
        
        参数:
            name: 显示名称，用于区分多个模拟 LLM 实例
        """
        self.name = name
        
    async def __call__(self, prompt):
        """
        模拟 LLM 调用
        
        1. 打印提示词到控制台
        2. 等待用户输入响应
        3. 用户输入空行结束
        
        参数:
            prompt: 提示词字符串
        
        返回:
            用户输入的响应字符串
        """
        # 显示提示词
        print(f"\n--- {self.name} Prompt ---")
        print(prompt)
        print(f"\n--- Please provide your response (enter an empty line to finish) ---")
        
        # 收集用户输入（支持多行）
        lines = []
        while True:
            line = input()
            if line.strip() == "":
                break
            lines.append(line)
        
        return "\n".join(lines)


# ==================== 测试代码 ====================

async def test_mock_llm():
    """测试模拟 LLM"""
    mock_llm = MockLLM(name="TestLLM")
    
    prompts = [
        "What is the capital of France?",
        "Write a short poem about artificial intelligence."
    ]
    
    for i, prompt in enumerate(prompts, 1):
        print(f"\nTest {i}:")
        response = await mock_llm(prompt)
        print("\nYour response was:")
        print("-" * 40)
        print(response)
        print("-" * 40)
    
    print("\nTest completed successfully!")


if __name__ == "__main__":
    asyncio.run(test_mock_llm())
