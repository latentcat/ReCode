"""
Agent 基类模块

这个文件定义了所有 Agent 必须实现的接口（抽象基类）。
任何 Agent（如 ReCodeAgent）都需要继承这个类并实现其中的抽象方法。

核心思想：
- Agent 负责根据环境观察(observations)生成动作(actions)
- 这是一个"大脑"的角色，决定下一步做什么
"""

from abc import ABC, abstractmethod
from typing import List


class Agent(ABC):
    """
    Agent 抽象基类
    
    所有 Agent 必须继承此类并实现以下方法：
    - act(): 根据观察返回动作
    - reset(): 重置 Agent 状态
    - report(): 返回运行报告
    
    使用示例：
        agent = MyAgent()
        agent.reset(config, init_info)
        while not done:
            actions = await agent.act(observations)
    """
    
    @abstractmethod
    async def act(self, observations: List[str]) -> List[str]:
        """
        根据环境观察生成动作
        
        这是 Agent 的核心方法，每个循环都会调用。
        
        参数:
            observations: 环境返回的观察列表
                         例如: ["你看到一个苹果在桌子上", "门是关着的"]
        
        返回:
            actions: 要执行的动作列表
                    例如: ["go to table", "take apple"]
                    或者特殊值 ["[FINISH]"] 表示结束
        """
        pass

    @abstractmethod
    def reset(self, running_config: dict, init_info: dict = None) -> None:
        """
        重置 Agent 状态，准备开始新的任务
        
        在每个新任务开始前调用，用于：
        - 清空之前的状态
        - 加载新任务的配置
        - 初始化必要的资源
        
        参数:
            running_config: 运行配置字典，包含：
                - profile: LLM 配置名称
                - max_depth: 最大递归深度
                - max_retry: 最大重试次数
                - 等等...
            
            init_info: 环境初始化信息，包含：
                - env_name: 环境名称 (如 "alfworld")
                - task_type: 任务类型 (如 "put", "clean")
                - observations: 初始观察
                - env: 环境实例引用
        """
        pass

    @abstractmethod
    def report(self) -> dict:
        """
        返回 Agent 的运行报告
        
        在任务结束后调用，用于收集统计信息。
        
        返回:
            报告字典，通常包含：
            - cost: API 调用费用
            - tree: 代码树结构（ReCode 特有）
            - max_depth: 实际达到的最大深度
            - 其他自定义指标
        """
        pass
