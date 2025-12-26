"""
环境基类模块

这个文件定义了所有环境必须实现的接口（抽象基类）。
环境负责接收 Agent 的动作并返回观察结果。

核心思想：
- 环境是 Agent 交互的"世界"
- Agent 发出动作 → 环境执行 → 返回观察
- 环境跟踪任务是否完成、是否成功
"""

from abc import ABC, abstractmethod
from typing import Union, List, Any, Optional


class Env(ABC):
    """
    环境抽象基类
    
    所有环境（如 ALFWorld、WebShop）都需要继承此类。
    
    核心属性：
        id: 环境实例的唯一标识
        _step_count: 当前步数计数器
        _done: 是否已结束
        _success: 是否成功完成任务
    
    使用示例：
        env = MyEnv()
        init_info = env.reset(config)
        while not env.is_done():
            observations = await env.run(actions)
    """
    
    # ---------- 核心属性 ----------
    id: str                    # 环境实例 ID
    _step_count: int = 0       # 步数计数
    _done: bool = False        # 是否结束
    _success: bool = False     # 是否成功

    # ---------- 抽象方法（子类必须实现）----------
    
    @abstractmethod
    async def _run(self, action: str) -> Any:
        """
        执行单个动作（子类必须实现）
        
        这是最核心的方法，定义了环境如何响应动作。
        
        参数:
            action: 单个动作字符串，如 "go to table"
        
        返回:
            观察结果，通常是字符串描述
            例如: "你走到了桌子旁边，看到桌上有一个苹果"
        """
        pass

    @abstractmethod
    def reset(self, running_config: dict, id: Optional[str] = None) -> dict:
        """
        重置环境，开始新任务
        
        参数:
            running_config: 运行配置，包含：
                - split: 数据集划分 ("train", "valid", "test")
                - task_types: 任务类型列表
                - seed: 随机种子
            id: 可选的实例 ID
        
        返回:
            初始化信息字典，必须包含：
            {
                "observations": [初始观察],
                "env_name": "环境名称",
                "env": self  # 环境实例引用
            }
        """
        pass

    @abstractmethod
    def report(self) -> dict:
        """
        返回环境报告
        
        返回:
            报告字典，通常包含：
            - success: 是否成功
            - steps: 总步数
            - reward: 奖励值（如果有）
            - task_type: 任务类型
        """
        pass

    # ---------- 通用方法（已实现，子类通常不需要覆盖）----------

    async def run(self, action: List[str]) -> List[str]:
        """
        执行一个或多个动作
        
        这是对外暴露的接口，内部调用 _run() 处理每个动作。
        
        参数:
            action: 动作列表，如 ["go to table", "take apple"]
                   也可以传单个字符串，会自动转为列表
        
        返回:
            observations: 每个动作对应的观察结果列表
        
        特殊行为：
            - 如果任务成功完成，会自动设置 _done = True
            - 如果任务已结束，会停止执行后续动作
        """
        # 兼容单个字符串输入
        if isinstance(action, str):
            action = [action]

        # 空动作直接返回
        if not action:
            return []

        # 依次执行每个动作
        observations: List[Any] = []
        for single_action in action:
            # 调用子类实现的 _run 方法
            observations.append(await self._run(single_action))
            
            # 检查是否成功完成
            if self.is_success():
                self._done = True
            
            # 如果已结束，停止执行后续动作
            if self.is_done():
                break
                
        return observations

    def is_done(self) -> bool:
        """
        检查任务是否结束
        
        结束条件通常包括：
        - 任务成功完成
        - 达到最大步数
        - 发生无法恢复的错误
        """
        return self._done

    def is_success(self) -> bool:
        """
        检查任务是否成功完成
        
        成功的定义取决于具体环境，例如：
        - ALFWorld: 完成指定的物品操作
        - WebShop: 购买到符合要求的商品
        """
        return self._success

    def get_step_count(self) -> int:
        """
        获取当前步数
        
        用于统计和限制最大步数。
        """
        return self._step_count    

    async def close(self) -> None:
        """
        关闭环境，释放资源
        
        子类可以覆盖此方法来：
        - 关闭网络连接
        - 释放浏览器实例
        - 清理临时文件
        """
        pass
