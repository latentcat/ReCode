"""
ALFWorld 环境模块

ALFWorld 是一个基于 TextWorld 的家居交互环境，
Agent 需要在虚拟房间中完成各种任务，如：
- 找到物品并放置到指定位置 (put)
- 清洁物品后放置 (clean)
- 加热/冷却物品后放置 (heat/cool)
- 检查物品 (examine)
- 放置两个物品 (puttwo)

这个模块封装了 ALFWorld 环境，使其符合 ReCode 的 Env 接口。

使用示例：
    env = AlfworldEnv(logger=my_logger)
    init_info = env.reset({"split": "test"}, id="0")
    observation = await env.run("go to table 1")
"""

import contextlib
import glob
import os
import re
from typing import Any, Dict, List, Optional, Union, Tuple

import yaml
from alfworld.agents.environment import get_environment

from base.environment import Env
from utils.errors import StepLimitError

import random

# ==================== 默认配置 ====================

# 如果用户没有设置 ALFWORLD_DATA 环境变量，使用默认路径
DEFAULT_ALFWORLD_DATA = os.path.expanduser("~/.cache/alfworld")
if "ALFWORLD_DATA" not in os.environ:
    os.environ["ALFWORLD_DATA"] = DEFAULT_ALFWORLD_DATA

# 任务类型映射：将 ALFWorld 的长名称映射为简短名称
prefixes = {
    'pick_and_place': 'put',           # 拿起并放置
    'pick_clean_then_place': 'clean',  # 清洁后放置
    'pick_heat_then_place': 'heat',    # 加热后放置
    'pick_cool_then_place': 'cool',    # 冷却后放置
    'look_at_obj': 'examine',          # 检查物品
    'pick_two_obj': 'puttwo'           # 放置两个物品
}

DEFAULT_MAX_STEPS = 50  # 默认最大步数


class AlfworldEnv(Env):
    """
    ALFWorld 环境类
    
    封装 ALFWorld 游戏环境，提供统一的接口供 ReCode Agent 使用。
    
    核心功能：
    - 加载和管理游戏文件
    - 执行动作并返回观察
    - 跟踪任务完成状态
    
    属性说明：
        env_name: 环境名称标识 ("alfworld")
        max_steps: 最大允许步数
        task_type: 当前任务类型 (put/clean/heat/cool/examine/puttwo)
        game_name: 当前游戏的名称
    """
    
    env_name = "alfworld"
    
    # 类级别缓存：避免重复加载游戏文件列表
    _cached_game_files: Dict[Tuple[str, str, Optional[Tuple[str, ...]]], List[str]] = {}

    def __init__(
        self,
        base_config_path: str = "envs/alfworld/base_config.yaml",
        specific_game_file: Optional[str] = None,
        task_types: Optional[List[str]] = None,
        logger: Optional[Any] = None,
        max_steps: Optional[int] = DEFAULT_MAX_STEPS,
    ) -> None:
        """
        初始化 ALFWorld 环境
        
        参数:
            base_config_path: ALFWorld 配置文件路径
            specific_game_file: 指定要加载的游戏文件（可选）
            task_types: 要过滤的任务类型列表（可选）
            logger: 日志记录器
            max_steps: 最大步数限制
        """
        self.base_config_path = base_config_path
        self.specific_game_file = specific_game_file
        self.logger = logger
        self.task_types: Optional[List[str]] = [t.lower() for t in task_types] if task_types else None

        self.max_steps: Optional[int] = max_steps
        self._step_count: int = 0

        self.env: Optional[Any] = None  # 底层 ALFWorld 环境实例
        self.game_files: Optional[List[str]] = None  # 游戏文件列表
        self.game_name: str = "unknown_game"
        self._done: bool = False
        self._success: bool = False

    def _get_game_files(self, seed: int = 42) -> List[str]:
        """
        获取当前 split 的所有游戏文件列表
        
        使用缓存避免重复扫描文件系统。
        
        参数:
            seed: 随机种子，用于打乱游戏顺序
        
        返回:
            游戏文件路径列表
        """
        if self.game_files is not None:
            return self.game_files

        # 构建缓存键
        cache_key: Tuple[str, str, Optional[Tuple[str, ...]]] = (
            os.path.abspath(self.base_config_path),
            self.split,
            tuple(sorted(self.task_types)) if self.task_types else None,
        )
        
        # 检查缓存
        if cache_key in AlfworldEnv._cached_game_files:
            self.game_files = AlfworldEnv._cached_game_files[cache_key]
            return self.game_files

        # 加载配置
        with open(self.base_config_path) as reader:
            config = yaml.safe_load(reader)

        # 根据 split 确定数据路径
        if self.split == "test":
            data_path_key = "eval_ood_data_path"
        elif self.split == "valid":
            data_path_key = "eval_id_data_path"
        else:
            data_path_key = "data_path"

        data_path = config["dataset"].get(data_path_key)
        if data_path:
            data_path = os.path.expandvars(data_path)

        if not data_path or not os.path.isdir(data_path):
            raise FileNotFoundError(f"Data path for split '{self.split}' not found or is not a valid directory: {data_path}")
        
        # 扫描游戏文件
        search_path = os.path.join(data_path, "**", "traj_data.json")
        game_files = glob.glob(search_path, recursive=True)

        # 按任务类型过滤
        if self.task_types:
            def _extract_mapped_task_type(path: str) -> Optional[str]:
                """从路径中提取任务类型"""
                try:
                    parts = os.path.normpath(path).split(os.sep)
                    task_dir = parts[-3].lower()
                except Exception:
                    return None

                for k, v in prefixes.items():
                    if task_dir.startswith(k):
                        return v
                return task_dir

            filtered: List[str] = []
            for gf in game_files:
                mapped = _extract_mapped_task_type(gf)
                if mapped and mapped in self.task_types:
                    filtered.append(gf)

            game_files = filtered

        if self.logger and not game_files:
            self.logger.warning(
                f"No game files found for split '{self.split}' at path '{search_path}'"
                + (f" after applying task_type filter {self.task_types}" if self.task_types else "")
            )

        # 过滤掉没有 PDDL 文件的游戏
        filtered_with_pddl: List[str] = []
        missing_pddl_count = 0
        for traj_path in game_files:
            pddl_path = traj_path.replace("traj_data.json", "game.tw-pddl")
            if os.path.exists(pddl_path):
                filtered_with_pddl.append(traj_path)
            else:
                missing_pddl_count += 1

        game_files = filtered_with_pddl

        if self.logger and missing_pddl_count:
            self.logger.info(
                f"Skipped {missing_pddl_count} game(s) without corresponding game.tw-pddl files."
            )

        # 打乱顺序
        random.seed(seed)
        random.shuffle(game_files) 

        # 缓存结果
        self.game_files = game_files
        AlfworldEnv._cached_game_files[cache_key] = game_files
        return self.game_files

    def _normalize_split_for_alfworld(self, split: str) -> str:
        """
        将用户的 split 名称映射到 ALFWorld 期望的名称
        
        ALFWorld 使用：
        - "train": 训练集
        - "eval_in_distribution": 验证集（同分布）
        - "eval_out_of_distribution": 测试集（异分布）
        """
        s = (split or "train").lower()
        if s in {"valid", "valid_seen", "eval_id", "eval_in_distribution"}:
            return "eval_in_distribution"
        if s in {"test", "valid_unseen", "eval_ood", "eval_out_of_distribution"}:
            return "eval_out_of_distribution"
        return "train"

    def _initialize(self) -> None:
        """
        初始化 ALFWorld 环境
        
        可以针对特定游戏文件或任务类型进行初始化。
        """
        normalized_split = self._normalize_split_for_alfworld(self.split)

        if self.logger:
            self.logger.info(f"Initializing ALFWorld environment with split: {normalized_split}")
            if self.specific_game_file:
                self.logger.info(f"Target game file: {self.specific_game_file}")

        # 加载配置
        with open(self.base_config_path) as reader:
            config = yaml.safe_load(reader)

        env_type = config["env"]["type"]
        env_class = get_environment(env_type)

        # 配置特定游戏或任务类型
        if self.specific_game_file:
            self._configure_for_specific_game(config, self.specific_game_file)
            pddl_game_file = self.specific_game_file.replace("traj_data.json", "game.tw-pddl")
            config.setdefault("env", {})
            config["env"]["external_game_files"] = [pddl_game_file]
        elif self.task_types:
            filtered_traj_files = self._get_game_files()
            filtered_pddl_files = [f.replace("traj_data.json", "game.tw-pddl") for f in filtered_traj_files]
            config.setdefault("env", {})
            config["env"]["external_game_files"] = filtered_pddl_files

        # 静默初始化（抑制 ALFWorld 的输出）
        with open(os.devnull, "w") as devnull, contextlib.redirect_stdout(
            devnull
        ), contextlib.redirect_stderr(devnull):
            alfworld_env = env_class(config, train_eval=normalized_split)

            # 设置游戏文件列表
            if self.specific_game_file:
                pddl_game_file = self.specific_game_file.replace("traj_data.json", "game.tw-pddl")
                alfworld_env.game_files = [pddl_game_file]
                alfworld_env.num_games = 1
            elif self.task_types:
                filtered_traj_files = self._get_game_files()
                filtered_pddl_files = [f.replace("traj_data.json", "game.tw-pddl") for f in filtered_traj_files]
                alfworld_env.game_files = filtered_pddl_files
                alfworld_env.num_games = len(filtered_pddl_files)
                if self.logger:
                    self.logger.info(
                        f"Task-type filter active. Loaded {len(filtered_pddl_files)} games for types {self.task_types}."
                    )

            self.env = alfworld_env.init_env(batch_size=1)

        if self.logger:
            self.logger.info("ALFWorld environment initialized successfully")

    def _configure_for_specific_game(self, config: Dict[str, Any], game_file: str) -> None:
        """
        修改配置以加载特定游戏文件
        """
        if not os.path.exists(game_file):
            raise FileNotFoundError(f"Specific game file not found: {game_file}")

        if self.split == "eval_out_of_distribution":
            data_path_key = "eval_ood_data_path"
        elif self.split == "eval_in_distribution":
            data_path_key = "eval_id_data_path"
        else:
            data_path_key = "data_path"

        split_root_dir = os.path.dirname(os.path.dirname(os.path.dirname(game_file)))
        config["dataset"][data_path_key] = split_root_dir

        num_games_key = data_path_key.replace("data_path", "num_games").replace("eval_id", "num_eval").replace("eval_ood", "num_eval")
        if num_games_key in config["dataset"]:
            del config["dataset"][num_games_key]

        pddl_game_file = game_file.replace("traj_data.json", "game.tw-pddl")
        if not os.path.exists(pddl_game_file):
            if self.logger:
                self.logger.warning(
                    f"PDDL file not found for {game_file}. Enabling regen_game_files so it will be generated."
                )

            if "env" not in config:
                config["env"] = {}

            config["env"]["regen_game_files"] = True

    def reset(self, running_config: dict, id: Optional[str] = None) -> dict:
        """
        重置环境，开始新任务
        
        参数:
            running_config: 运行配置，包含：
                - split: 数据集划分 ("train"/"valid"/"test")
                - seed: 随机种子
                - task_type: 任务类型过滤
            id: 任务 ID（游戏文件索引）
        
        返回:
            初始化信息字典：
            {
                "observations": [初始观察],
                "task_type": 任务类型,
                "env_name": "alfworld",
                "env": self
            }
        """
        if self.logger:
            self.logger.info("Resetting ALFWorld environment")
        
        # 解析配置
        seed = running_config.get("seed", 42) if running_config else 42
        task_type_filter = running_config.get("task_type", None) if running_config else None
        self.split = running_config.get("split", "train") if running_config else "train"
        self.id = id
        id_int: Optional[int] = None

        # 处理任务 ID
        if id is not None:
            try:
                id_int = int(id)
            except ValueError:
                raise ValueError(f"Task ID '{id}' is not a valid integer.")
            
            if self.game_files is None:
                self.game_files = self._get_game_files(seed)
            
            if not 0 <= id_int < len(self.game_files):
                raise ValueError(
                    f"Task ID {id_int} is out of valid range (0-{len(self.game_files) - 1})."
                )
            
            # 按任务类型过滤
            if task_type_filter:
                game_files = []
                for game_file in self.game_files:
                    task_type = game_file.split("/")[-3]
                    if task_type in task_type_filter:
                        game_files.append(game_file)
                self.game_files = game_files

            # 设置特定游戏文件
            self.specific_game_file = self.game_files[id_int]
            
            # 提取任务类型
            self.task_type = self.specific_game_file.split("/")[-3]
            for k, v in prefixes.items():
                if self.task_type.startswith(k):
                    self.task_type = v
                    break
            
            if self.logger:
                self.logger.info(f"Task type: {self.task_type}")
            
            self.env = None  # 强制重新初始化
            
            if self.logger:
                self.logger.info(f"Set to run specific game file for ID {id}: {self.specific_game_file}")

        # 初始化环境
        if self.env is None:
            self._initialize()

        if self.env is None:
            raise ValueError("Environment could not be initialized.")

        # 重置环境
        ob_raw, info_raw = self.env.reset()
        
        # 重置状态
        self._step_count = 0
        self._done = False
        self._success = False

        # 提取游戏名称
        self.game_name = "unknown_game"
        if "extra.gamefile" in info_raw and info_raw["extra.gamefile"]:
            try:
                self.game_name = "/".join(info_raw["extra.gamefile"][0].split("/")[-3:-1])
            except Exception as e:
                if self.logger:
                    self.logger.warning(f"Could not parse game name from info: {e}")

        # 处理观察（去除开头的描述部分）
        obs = "\n".join(ob_raw[0].split("\n\n")[1:])
        
        return {"observations": [obs], "task_type": self.task_type, "env_name": self.env_name, "env": self}

    def set_max_steps(self, max_steps: int) -> None:
        """设置最大步数限制"""
        self.max_steps = max_steps

    async def _run(self, single_action: str) -> str:
        """
        执行单个动作
        
        参数:
            single_action: 动作字符串，如 "go to table 1"
        
        返回:
            观察结果字符串
        
        支持的动作包括：
        - go to <location>: 前往某位置
        - take <object> from <location>: 拿取物品
        - put <object> in/on <location>: 放置物品
        - open/close <object>: 打开/关闭
        - examine <object>: 检查物品
        - use <object>: 使用物品（如加热、冷却）
        """
        if not single_action:
            return ""

        # 处理结束信号
        if single_action.strip() == "[FINISH]":
            self._done = True
            return "Episode terminated by agent."

        if self._done:
            return "The environment has already terminated."

        # 检查步数限制
        self._step_count += 1
        if self.max_steps is not None and self._step_count > self.max_steps:
            self._done = True
            raise StepLimitError(f"Step limit of {self.max_steps} exceeded.")

        # 处理 put 动作的 in/on 问题（ALFWorld 只接受 in/on）
        pattern = r"^(put\s+\S+(?:\s+\S+)*\s+)(in|on)(\s+\S+(?:\s+\S+)*)$"
        match = re.match(pattern, single_action.strip())
        if match:
            single_action = f"{match.group(1)}in/on{match.group(3)}"

        def _process_ob(ob: str) -> str:
            """处理观察结果，去除位置前缀"""
            if ob.startswith('You arrive at loc '):
                ob = ob[ob.find('. ')+2:]
            return ob

        try:
            # 执行动作
            obs_raw, _, done, info = self.env.step([single_action])
            processed_obs = _process_ob(obs_raw[0])
            self._done = bool(done[0])
            self._success = "won" in info and bool(info["won"][0])
            return processed_obs
        except Exception as e:
            if self.logger:
                self.logger.error(f"Error executing command '{single_action}': {e}")
            self._done = True
            self._success = False
            return f"Error: {e}"
        
    def report(self) -> dict:
        """
        返回环境报告
        
        返回:
            包含以下字段的字典：
            - success: 是否成功完成任务
            - steps: 执行的总步数
            - task_type: 任务类型
            - reward: 奖励值（成功为 1，失败为 0）
        """
        return {
            "success": self._success,
            "steps": self._step_count,
            "task_type": self.task_type,
            "reward": int(self._success)
        }

    async def close(self) -> None:
        """
        关闭环境，释放资源
        """
        if self.logger:
            self.logger.info("Closing ALFWorld environment")
        
        try:
            # 清理 ALFWorld 环境
            if hasattr(self, 'env') and self.env is not None:
                self.env = None
                
            # 重置状态
            self._step_count = 0
            self._done = False
            self._success = False
            self.game_files = None
            self.game_name = "unknown_game"
            
            if self.logger:
                self.logger.info("ALFWorld environment closed successfully")
                
        except Exception as e:
            if self.logger:
                self.logger.error(f"Error closing ALFWorld environment: {e}")
            raise
