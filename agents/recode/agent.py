"""
ReCode Agent 核心模块

这是 ReCode 的"大脑"，实现了递归代码生成的核心逻辑。

核心思想：
1. 把任务表示为代码树，根节点是 solve(instruction, observation)
2. 执行代码时，如果遇到未定义的函数（占位函数），调用 LLM 展开
3. 展开后的代码变成子节点，继续执行
4. 直到所有代码都变成可执行的原子动作

关键流程：
    初始化 → 执行根节点 → 遇到占位函数 → LLM 展开 → 创建子节点 
    → 执行子节点 → ... → 全部完成
"""

from __future__ import annotations

from pathlib import Path
from enum import Enum
from typing import List, Optional
from datetime import datetime, timezone

from base.agent import Agent
from utils.llm import AsyncLLM
from utils.executor import Executor
from utils.common import parse_xml_tag

from agents.recode.resources.prompts.default_new import EXPAND_PROMPT
from agents.recode.utils import (
    parse_raw_observation,
    split_blocks,
    validate_blocks,
    NodeStatus,
    CodeNode,
    get_variables,
)

# ==================== 默认配置 ====================

DEFAULT_MAX_DEPTH = 10      # 最大递归深度，防止无限展开
DEFAULT_MAX_RETRY = 5       # 最大重试次数
DEFAULT_MAX_REWRITE = 5     # LLM 重新生成代码的最大次数


class ReCodeAgent(Agent):
    """
    ReCode Agent 主类
    
    通过递归代码生成来解决任务，统一规划和执行。
    
    核心属性：
        llm: 大语言模型调用器
        executor: Python 代码执行器
        root: 代码树的根节点
        current_node: 当前正在处理的节点
        
    使用示例：
        agent = ReCodeAgent(logger=my_logger)
        agent.reset(config, init_info)
        while not done:
            await agent.act(observations)
    """
    
    def __init__(
        self,
        logger=None,
        task_type: str = None,
    ) -> None:
        """
        初始化 ReCode Agent
        
        参数:
            logger: 日志记录器，用于输出调试信息
            task_type: 任务类型（如 "put", "clean"），用于加载对应的 few-shot 示例
        """
        self.logger = logger
        self.llm = AsyncLLM()                           # LLM 调用器
        self.executor = Executor(if_run_print=True)     # 代码执行器

        # 代码树相关状态
        self.root: Optional[CodeNode] = None            # 根节点
        self.current_node: Optional[CodeNode] = None    # 当前节点
        self.previous_node: Optional[CodeNode] = None   # 上一个节点（用于调试）
        self.task_type: str = task_type                 # 任务类型
        self.is_start = False                           # 是否已开始
 
    def reset(self, running_config: dict, init_info: dict = None) -> None:
        """
        重置 Agent，准备开始新任务
        
        这个方法会：
        1. 清空之前的状态（代码树等）
        2. 加载运行配置（深度限制、重试次数等）
        3. 加载环境相关的资源（提示词、示例）
        4. 将执行器与环境关联
        
        参数:
            running_config: 运行配置字典
            init_info: 环境初始化信息
        """
        # 1. 清空状态
        self.root = None
        self.current_node = None
        self.previous_node = None
        self.is_start = False

        # 2. 加载配置
        self.max_depth: int = running_config.get('max_depth') or DEFAULT_MAX_DEPTH
        self.max_retry: int = running_config.get('max_retry') or DEFAULT_MAX_RETRY
        self.max_rewrite: int = running_config.get('max_rewrite') or DEFAULT_MAX_REWRITE
        
        # 3. 获取任务类型（优先从 init_info 获取，其次从 config）
        if init_info and 'task_type' in init_info and init_info['task_type']:
            self.task_type = init_info['task_type'].lower()
        elif 'task_type' in running_config:
            self.task_type = running_config['task_type'].lower()

        # 4. 加载 LLM 配置
        if "profile" in running_config and running_config['profile']:
            self.logger.info(f"Using profile: {running_config['profile']}")
            self.llm = AsyncLLM(running_config['profile'])

        # 5. 获取环境信息并关联执行器
        assert 'env_name' in init_info, "Envrioment must be specified"
        self.env_name = init_info['env_name']
        
        # ALFWorld 特殊处理：增加最大步数
        if self.env_name == "alfworld":
            self.logger.info("Setting max steps to 80")
            init_info['env'].set_max_steps(80)
        
        # 将环境注入执行器
        self.executor.set_env(init_info['env'])

        # 6. 加载提示词和示例
        self._load_resources()

    def _load_resources(self):
        """
        加载环境特定的资源文件
        
        加载内容：
        - available_actions: 可用动作的描述（告诉 LLM 有哪些原子动作）
        - fewshots: 少样本示例（告诉 LLM 应该怎么展开代码）
        """
        # 加载动作描述
        resources_path = Path("agents/recode/resources/prompts") / self.env_name
        self.available_actions = open(resources_path / "actions.txt", "r").read()

        # 加载 few-shot 示例（不同环境有不同的加载策略）
        fewshots_path = Path("agents/recode/resources/fewshots") / self.env_name
        if self.env_name == "alfworld":
            # ALFWorld 根据任务类型加载不同的示例
            self.fewshots = open(fewshots_path / f"{self.task_type}.txt", "r").read()
        elif self.env_name == "webshop":
            self.fewshots = open(fewshots_path / "base.txt", "r").read()
        elif self.env_name == "sciworld":
            self.fewshots = open(fewshots_path / "base.txt", "r").read()
        else:
            raise ValueError(f"Unsupported environment in _load_resources: {self.env_name}")

    async def act(self, observations: List[str]) -> List[str]:
        """
        Agent 的主循环方法
        
        每次被调用时：
        1. 如果是第一次调用，初始化代码树
        2. 如果当前节点需要展开，调用 LLM
        3. 执行当前节点的代码
        4. 根据执行结果更新状态，移动到下一个节点
        
        参数:
            observations: 环境观察（第一次调用时用于初始化）
        
        返回:
            如果任务结束返回 ["[FINISH]"]，否则返回空（动作在执行器中处理）
        """
        # 第一次调用：初始化代码树
        if not self.is_start:
            assert len(observations) == 1, "Only one observation is allowed for the first node"
            self._init_code_tree(observations[0])
            self.is_start = True

        # 处理需要展开的节点
        if self.current_node.status == NodeStatus.STUB:
            await self._handle_stub()
        elif self.current_node.status == NodeStatus.ERROR:
            return ["[FINISH]"]

        # 检查是否还有节点要执行
        if not self.current_node:
            return ["[FINISH]"]
        
        # 执行当前节点的代码
        self.logger.info(f"[Execute]\n{self.current_node.code}")
        result = self._execute(self.current_node.code)
        
        # 保存执行输出
        self.current_node.observations.extend(result["stdout"]) if result["stdout"] else None
        self.logger.info(f"[Exec Result]\n{result}")

        # 根据执行结果更新状态
        if result["success"]:
            # 执行成功：标记完成，移动到下一个节点
            self.logger.info(f"[Execution Stdout] {result['stdout']}")
            self.current_node.status = NodeStatus.COMPLETED
            self.previous_node = self.current_node
            self.current_node = self.current_node.next()
            if not self.current_node:
                return ["[FINISH]"]
        else:
            # 执行失败：判断是需要展开还是真正的错误
            if "NeedExpansion" in result["error"]:
                # 占位函数，需要展开
                self.current_node.status = NodeStatus.STUB
            else:
                # 真正的错误
                self.current_node.status = NodeStatus.ERROR
                self.current_node.error = result["error"]

    async def _handle_stub(self) -> None:
        """
        处理需要展开的节点（占位函数）
        
        流程：
        1. 检查是否超过最大深度
        2. 调用 _expand() 让 LLM 生成展开代码
        3. 将展开的代码创建为子节点
        4. 移动到下一个待执行的节点
        """
        # 深度检查，防止无限递归
        if self.current_node and self.current_node.depth >= self.max_depth:
            if self.logger:
                self.logger.warning("Max depth reached - terminating.")
            self.current_node = None
            return

        # 调用 LLM 展开
        new_blocks = await self._expand()
        self.logger.info("[NEW_BLOCKS]\n" + "\n".join(new_blocks)) if new_blocks else None

        if self.current_node:
            if new_blocks is None:
                # 展开失败，终止
                self.current_node = None
                return
            if new_blocks:
                # 为每个代码块创建子节点
                for block in new_blocks:
                    child_node = CodeNode(code=block, parent=self.current_node)
                    self.current_node.children.append(child_node)
            else: 
                # 空展开，跳过此节点
                self.current_node.status = NodeStatus.SKIP

        # 移动到下一个节点
        self.current_node = self.current_node.next()

    async def _expand(self) -> Optional[List[str]]:
        """
        调用 LLM 展开占位函数
        
        流程：
        1. 构建提示词（包含可用动作、示例、当前任务、变量）
        2. 调用 LLM 获取响应
        3. 解析响应中的 <think> 和 <execute> 标签
        4. 验证生成的代码是否合法
        5. 如果不合法，重试（最多 max_rewrite 次）
        
        返回:
            成功：代码块列表
            失败：None
        """
        attempt = 0
        retry_hint_added = False
        
        while True:
            # 构建提示词
            user_prompt = self._build_expand_prompt()
            
            # 如果是重试，添加错误提示
            if retry_hint_added:
                user_prompt += (
                    "\n\n[Important] Your previous expansion produced syntactically invalid code and/or included disallowed constructs (e.g., def/async def). "
                    "Strictly follow the rules: output a single valid Python code block, and do not use def or async def."
                )
            
            if self.logger:
                self.logger.info("[LLM_IN]\n" + user_prompt)
            
            # 调用 LLM
            response, _cost = await self.llm(user_prompt)
            
            if self.logger:
                self.logger.info("[LLM_OUT]\n" + response.strip())

            # 解析响应
            thought = parse_xml_tag(response, "think").strip()
            self.current_node.thought = thought
            expanded_code = parse_xml_tag(response, "execute").strip()

            # 验证代码
            try:
                blocks = split_blocks(expanded_code)
                validate_blocks(blocks)
                return blocks
            except (SyntaxError, ValueError) as e:
                # 验证失败，重试
                attempt += 1
                retry_hint_added = True
                
                if attempt >= self.max_rewrite:
                    if self.logger:
                        self.logger.info(
                            f"[STOP] Reached max re-expands ({self.max_rewrite}). Last error: {e}. Ending episode."
                        )
                    return None
                    
                if self.logger:
                    self.logger.info(
                        f"[RE-EXPAND {attempt}/{self.max_rewrite}] Split/validation failed due to: {e}. Re-asking EXPAND..."
                    )

    def _execute(self, code: str) -> dict:
        """
        执行代码片段
        
        委托给 Executor 执行，返回结果字典。
        """
        return self.executor.execute(code)

    def _init_code_tree(self, observation: str) -> None:
        """
        初始化代码树
        
        把任务转化为代码树的根节点：solve(instruction, observation)
        
        参数:
            observation: 环境的初始观察
        """
        self.logger.info(f"[OBSERVATIONS]\n{observation}")
        
        # 解析原始观察，提取任务描述
        initial_observation, instruction = parse_raw_observation(observation, self.env_name)
        
        # 将解析结果存入执行器的变量空间
        self.executor.set_var('observation', initial_observation)
        self.executor.set_var('instruction', instruction)
        
        # 创建根节点 - 这是一个占位函数，会在第一次执行时触发展开
        self.root = CodeNode(code=f"solve(instruction, observation)")
        self.current_node = self.root
        
    def _build_expand_prompt(self) -> str:
        """
        构建 LLM 展开提示词
        
        提示词包含：
        - 可用的原子动作列表
        - 少样本示例
        - 当前要展开的任务
        - 可用的变量及其值
        """
        examples = self.fewshots if self.fewshots else "(No Examples)"
        task = self.current_node.code
        variables = get_variables(self.executor, self.current_node.code)
        variables = variables if variables else "(No Variables)"
        
        return EXPAND_PROMPT.format(
            available_actions=self.available_actions,
            examples=examples,
            task=task,
            variables=variables
        )

    def _get_max_depth(self, node: Optional[CodeNode]) -> int:
        """
        递归获取代码树的最大深度
        
        用于统计实际达到的最深层级。
        """
        if node is None:
            return 0
        max_depth = node.depth
        for child in node.children:
            child_max = self._get_max_depth(child)
            if child_max > max_depth:
                max_depth = child_max
        return max_depth

    def _get_formatted_tree(self) -> dict:
        """
        将代码树格式化为可序列化的字典
        
        用于保存执行轨迹，便于分析和可视化。
        """
        version = "recode.plan.v1"

        # 元数据
        meta = {
            "env_name": getattr(self, "env_name", None),
            "task_type": getattr(self, "task_type", None),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "max_depth": getattr(self, "max_depth", None),
            "max_retry": getattr(self, "max_retry", None),
            "max_rewrite": getattr(self, "max_rewrite", None),
        }

        # 遍历树，收集所有节点和边
        nodes = {}
        edges = []
        root_id = self.root.id if self.root else None

        if self.root:
            stack = [self.root]
            while stack:
                node = stack.pop()
                nodes[node.id] = {
                    "code": node.code,
                    "thought": getattr(node, "thought", None),
                    "status": node.status.value if isinstance(node.status, Enum) else node.status,
                    "depth": node.depth,
                    "observations": list(node.observations) if node.observations else [],
                    "error": node.error,
                }
                for child in node.children:
                    edges.append([node.id, child.id])
                # 逆序压栈以保持 DFS 顺序
                for child in reversed(node.children):
                    stack.append(child)

        return {
            "version": version,
            "meta": meta,
            "root_id": root_id,
            "nodes": nodes,
            "edges": edges,
        }

    def report(self) -> dict:
        """
        返回 Agent 运行报告
        
        返回:
            包含以下字段的字典：
            - cost: LLM 调用总费用
            - tree: 完整的代码树结构
            - max_depth: 实际达到的最大深度
        """
        return {
            'cost': self.llm.spent,
            'tree': self._get_formatted_tree(),
            'max_depth': self._get_max_depth(self.root)
        }
