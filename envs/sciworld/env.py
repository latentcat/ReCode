"""
ScienceWorld 环境封装模块

ScienceWorld 是一个基于文本的科学实验模拟环境，用于测试 Agent 在虚拟科学实验场景中的推理和操作能力。
本模块将 ScienceWorld 封装为符合 base.environment.Env 接口的环境类。

主要功能：
- 加载不同类型的科学实验任务（如物理、化学实验）
- 执行文本指令与环境交互
- 追踪任务完成状态和奖励分数

支持的动作示例：
- open/close OBJ: 打开/关闭容器
- activate/deactivate OBJ: 激活/停用设备
- connect/disconnect OBJ: 连接/断开电路
- move OBJ to OBJ: 移动物品
- pour OBJ into OBJ: 倒液体
- mix OBJ: 混合化学物质
- teleport to LOC: 传送到指定房间
"""

import contextlib
import json
import os
import random
from pathlib import Path
from typing import Any, Dict, List, Optional, Union
import numpy as np

import yaml
from base.environment import Env
from utils.errors import StepLimitError


class SciWorldEnv(Env):
    """
    ScienceWorld 环境封装类
    
    将第三方 ScienceWorld 库封装为符合 base.Env 接口的环境，
    使其可以被 ReCode Agent 统一调用。
    
    属性:
        env_name: 环境名称标识符，用于日志和配置匹配
        _shared_cache: 类级别缓存，避免多个实例重复读取相同的配置文件
    """
    env_name = "sciworld"
    
    # 类级别共享缓存：避免多个环境实例重复读取配置文件
    # 键为 data_root_dir 的绝对路径，值为加载的配置数据
    _shared_cache: Dict[str, Dict[str, Any]] = {}

    def __init__(
        self,
        config_path: str = "envs/sciworld/base_config.yaml",
        simplification: str = "easy",
        logger: Optional[Any] = None,
    ) -> None:
        """
        初始化 ScienceWorld 环境
        
        Args:
            config_path: 配置文件路径，包含数据目录等设置
            simplification: 任务简化级别，"easy" 表示使用简化版本的任务
            logger: 日志记录器实例
        """
        self.simplification = simplification
        self.logger = logger
        self.config = {}
        
        # 加载配置文件
        if config_path and Path(config_path).exists():
            with open(config_path, 'r') as f:
                self.config = yaml.safe_load(f) or {}

        # 设置数据根目录
        self.data_root_dir = Path(self.config['data_root_dir'])
        root_key = str(self.data_root_dir.resolve())
        
        # 使用共享缓存加载任务配置，避免重复 I/O
        cache = SciWorldEnv._shared_cache.get(root_key)
        if cache is None:
            cache = {
                # taskname2id: 任务名称到ID的映射
                "taskname2id": json.load(open(self.data_root_dir / "taskname2id.json")),
                # max_steps: 每种任务类型的最大允许步数
                "max_steps": json.load(open(self.data_root_dir / "max_steps.json")),
                # indices_by_split: 按数据集划分(train/test/valid)的任务索引缓存
                "indices_by_split": {},
            }
            SciWorldEnv._shared_cache[root_key] = cache
        
        self.taskname2id = cache["taskname2id"]
        self.max_steps_dict = cache["max_steps"]

    def _initialize(self) -> None:
        """
        延迟初始化 ScienceWorld 环境
        
        ScienceWorld 的初始化比较耗时（需要启动 Java 服务），
        因此采用延迟初始化策略，在真正需要时才创建环境实例。
        """
        if self.logger:
            self.logger.info("Initializing ScienceWorld environment")
        
        # 检查 scienceworld 库是否已安装
        try:
            import scienceworld
        except ImportError as e:
            raise ImportError(
                "The 'scienceworld' library is required to use SciWorldEnv. "
                "Please install it with 'pip install scienceworld'."
            ) from e

        # 抑制 ScienceWorld 的启动输出信息（重定向到 /dev/null）
        with open(os.devnull, "w") as devnull, contextlib.redirect_stdout(devnull):
            self.env = scienceworld.ScienceWorldEnv(
                serverPath=None,        # 使用默认服务路径
                envStepLimit=np.inf     # 不限制环境内部步数（由我们自己控制）
            )

        if self.logger:
            self.logger.info("ScienceWorld environment initialized successfully")

    def _load_indices(self, split: str, seed: int) -> List[int]:
        """
        加载指定数据集划分的任务索引列表
        
        Args:
            split: 数据集划分名称 ("train", "test", "valid", "validation")
            seed: 随机种子，用于打乱任务顺序以确保可复现性
            
        Returns:
            打乱后的任务索引列表，每个元素是 (task_name, variation) 元组
        """
        root_key = str(self.data_root_dir.resolve())
        cache = SciWorldEnv._shared_cache.get(root_key)
        
        if cache is None:
            cache = {
                "taskname2id": getattr(self, "taskname2id", {}),
                "max_steps": getattr(self, "max_steps_dict", {}),
                "indices_by_split": {},
            }
            SciWorldEnv._shared_cache[root_key] = cache
        
        indices_cache = cache.setdefault("indices_by_split", {})
        
        # 处理 "validation" 别名
        if split not in indices_cache:
            if split == "validation":
                split = "valid"
            with open(self.data_root_dir / f"{split}_indices.json", "r") as f:
                indices_cache[split] = json.load(f)

        # 使用固定种子打乱顺序，确保实验可复现
        random.seed(seed)
        random.shuffle(indices_cache[split])
        return indices_cache[split]

    def reset(self, running_config: dict, id: Optional[str] = None) -> dict:
        """
        重置环境到初始状态，加载指定的任务
        
        Args:
            running_config: 运行配置字典，包含:
                - split: 数据集划分 ("train", "test", "valid")
                - seed: 随机种子
            id: 任务索引ID（字符串形式的整数）
            
        Returns:
            初始化结果字典:
                - observations: 初始观察列表（包含任务描述和初始状态）
                - env_name: 环境名称
                - env: 环境实例引用
        """
        # 延迟初始化环境
        self._initialize()
        if self.env is None:
            raise RuntimeError("Environment could not be initialized.")
        
        # 加载任务索引
        self.split = running_config.get("split", "train")
        seed = running_config.get("seed", 42)
        self.indices = self._load_indices(self.split, seed)

        # 解析任务ID并加载对应任务
        id_int: Optional[int] = None
        if id is not None:
            try:
                id_int = int(id)
            except ValueError:
                raise ValueError(f"Task ID '{id}' is not a valid integer.")
            if not 0 <= id_int < len(self.indices):
                raise ValueError(
                    f"Task ID {id_int} is out of valid range (0-{len(self.indices) - 1})."
                )
            # indices 中每个元素是 (task_name, variation) 元组
            self.task_name, self.variation = self.indices[id_int]

        # 构建唯一任务标识符
        self.id = f"{self.taskname2id[self.task_name]}_{self.variation}"
        # 获取该任务类型的最大允许步数
        self.max_steps = self.max_steps_dict[self.task_name]

        # 加载任务到 ScienceWorld 环境
        self.env.load(self.task_name, self.variation, self.simplification, generateGoldPath=False)
        obs, info = self.env.reset()

        # 初始化状态追踪变量
        self._step_count = 0      # 已执行步数
        self._done = False        # 是否结束
        self._success = False     # 是否成功
        self._reward = 0.0        # 累计奖励（分数）
        
        # 构建初始观察：任务描述 + 环境状态
        task_description = info.get("taskDesc", "No task description found.")
        observation = f"{task_description}\n{obs}"

        return {"observations": [observation], "env_name": self.env_name, "env": self}

    async def _run(self, single_action: str) -> str:
        """
        执行单个动作并返回环境反馈
        
        这是 Agent 与环境交互的核心方法，由 Executor 在执行代码时调用。
        
        Args:
            single_action: 要执行的动作字符串，如 "open door", "pick up apple"
            
        Returns:
            环境返回的观察结果字符串
            
        Raises:
            StepLimitError: 超过最大步数限制时抛出
        """
        if not single_action:
            return ""

        # 如果环境已结束，直接返回
        if self._done:
            return "The environment has already terminated."

        # 处理特殊的结束动作
        if single_action.strip().lower() == "[finish]":
            self._done = True
            return "You have finished the task." if self._success else "Task failed."

        # 步数计数并检查是否超限
        self._step_count += 1
        if self.max_steps and self._step_count > self.max_steps:
            self._done = True
            raise StepLimitError(f"Step limit of {self.max_steps} exceeded.")

        try:
            # 执行动作，获取环境反馈
            obs, _, done, info = self.env.step(single_action)
            self.logger.info(f"[Score] {info['score']}")
            
            # 更新奖励（取最高分）
            self._reward = info['score'] if info['score'] is not None and info['score'] > self._reward else self._reward
            self._done = done
            
            # 如果任务完成且有正分数，标记为成功
            if info['score'] > 0 and done:
                self._success = True
            
            return obs
            
        except Exception as e:
            if self.logger:
                self.logger.error(f"Error executing action '{single_action}': {e}")
            self._done = True
            self._success = False
            raise

    def is_done(self) -> bool:
        """检查任务是否已结束（成功、失败或超时）"""
        return self._done

    def get_step_count(self) -> int:
        """获取当前已执行的步数"""
        return self._step_count

    def is_success(self) -> bool:
        """检查任务是否成功完成"""
        return self._success

    def report(self):
        """
        生成任务执行报告
        
        Returns:
            包含执行统计信息的字典:
                - success: 是否成功
                - step: 执行步数
                - reward: 获得的分数
                - task_type: 任务类型名称
        """
        return {
            "success": self._success,
            "step": self._step_count,
            "reward": self._reward,
            "task_type": self.task_name,
        }

    async def close(self) -> None:
        """
        关闭环境并释放资源
        
        ScienceWorld 内部可能运行了 Java 进程，
        需要正确清理以避免资源泄漏。
        """
        if self.logger:
            self.logger.info("Closing ScienceWorld environment")
        
        try:
            # 清理 ScienceWorld 环境引用
            if hasattr(self, 'env') and self.env is not None:
                # ScienceWorld 没有显式的 close 方法，通过置空引用让 GC 清理
                self.env = None
                
            # 重置状态变量
            self._step_count = 0
            self._done = False
            self._success = False
            self._reward = 0.0
            
            if self.logger:
                self.logger.info("ScienceWorld environment closed successfully")
                
        except Exception as e:
            if self.logger:
                self.logger.error(f"Error closing ScienceWorld environment: {e}")
            raise
