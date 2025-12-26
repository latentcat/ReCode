"""
ReCode 辅助工具模块

这个文件包含 ReCode Agent 使用的核心数据结构和辅助函数。

主要内容：
- CodeNode: 代码树的节点类
- NodeStatus: 节点状态枚举
- 代码解析和验证函数
"""

import ast
from dataclasses import dataclass, field
from enum import Enum
import uuid
from typing import List, Optional, Any
from utils.executor import Executor
import re


def parse_raw_observation(raw_observation: str, env_name: str) -> tuple[str, str]:
    """
    解析环境的原始观察，提取初始状态和任务描述
    
    不同环境的观察格式不同，这个函数负责统一处理。
    
    参数:
        raw_observation: 环境返回的原始观察字符串
        env_name: 环境名称
    
    返回:
        (initial_observation, instruction) 元组
        - initial_observation: 初始环境状态描述
        - instruction: 任务指令描述
    
    示例 (ALFWorld):
        输入: "你在厨房里。看到...\nYour task is to: find apple and put it on table."
        输出: ("你在厨房里。看到...", "find apple and put it on table")
    """
    if env_name == "alfworld" or env_name == "travelplanner":
        # ALFWorld 格式：第一行是环境描述，第二行包含任务
        lines = raw_observation.split("\n")
        if "Your task is to:" in lines[1]:
            task_description = lines[1].split("Your task is to:")[-1].strip().removesuffix(".")
            code = task_description.replace(' ', '_') + '()'
        return lines[0], task_description
    
    elif env_name == "webshop":
        # WebShop 格式：第一行是任务描述
        task_description = raw_observation.strip().split('\n')[0].strip()
        return raw_observation.strip(), task_description
    
    elif env_name == "sciworld":
        # ScienceWorld 格式：前两行是元信息，任务在第二行
        lines = raw_observation.split("\n")
        return '\n'.join(lines[2:]), lines[1]
    
    else:
        raise ValueError(f"Unsupported environment in parse_raw_observation: {env_name}")


class NodeStatus(str, Enum):
    """
    代码节点的状态枚举
    
    状态流转：
        PENDING → 执行 → COMPLETED (成功)
        PENDING → 执行 → STUB (需要展开) → 展开 → 子节点变为 PENDING
        PENDING → 执行 → ERROR (出错)
        STUB → 展开为空 → SKIP
    """
    PENDING = "PENDING"       # 等待执行
    COMPLETED = "COMPLETED"   # 执行成功
    STUB = "STUB"            # 占位函数，需要 LLM 展开
    ERROR = "ERROR"          # 执行出错
    SKIP = "SKIP"            # 跳过（展开为空）


@dataclass
class CodeNode:
    """
    代码树的节点
    
    每个节点代表一段代码，可以是：
    - 占位函数调用：如 find_and_take(obj, locations)
    - 具体代码：如 for loc in locations: run(f"go to {loc}")
    
    属性说明：
        thought: LLM 展开时的思考过程
        code: 这个节点的代码字符串
        id: 唯一标识符（UUID）
        parent: 父节点引用
        children: 子节点列表
        status: 当前状态
        depth: 在树中的深度（根节点为 0）
        error: 如果出错，记录错误信息
        observations: 执行过程中收集的环境观察
    """
    thought: str = ""                                           # LLM 的思考过程
    code: str = ""                                              # 代码内容
    id: str = field(default_factory=lambda: str(uuid.uuid4()))  # 唯一 ID
    parent: Optional['CodeNode'] = None                         # 父节点
    children: List['CodeNode'] = field(default_factory=list)    # 子节点列表
    status: NodeStatus = NodeStatus.PENDING                     # 状态
    depth: int = 0                                              # 深度
    error: str = None                                           # 错误信息
    observations: List[str] = field(default_factory=list)       # 观察列表

    def __post_init__(self):
        """
        初始化后处理：自动计算深度
        """
        self.depth = 0 if not self.parent else self.parent.depth + 1

    def next(self) -> Optional['CodeNode']:
        """
        获取下一个要执行的节点
        
        查找顺序：
        1. 自己的子节点中第一个 PENDING 的
        2. 自己的兄弟节点中第一个 PENDING 的
        3. 向上回溯到父节点，继续找
        
        这实现了深度优先遍历（DFS）的效果。
        
        返回:
            下一个待执行的节点，如果没有则返回 None
        """
        # 1. 先找子节点
        for child in self.children:
            if child.status == NodeStatus.PENDING:
                return child

        # 2. 再找右边的兄弟节点
        if self.parent:
            siblings = self.parent.children
            try:
                current_index = siblings.index(self)
                for i in range(current_index + 1, len(siblings)):
                    if siblings[i].status == NodeStatus.PENDING:
                        return siblings[i]
            except ValueError:
                pass
        
        # 3. 向上回溯
        if self.parent:
            return self.parent.next()
        
        # 4. 没有更多节点了
        return None
    
    def clear(self) -> None:
        """
        清空节点状态（用于重试）
        """
        self.status = NodeStatus.PENDING
        self.code = ""
        self.error = None
        self.observations = []


def split_blocks(source: str) -> List[str]:
    """
    将代码字符串拆分成独立的语句块
    
    例如：
        输入: '''
        obj = "apple"
        obj_id = find_and_take(obj)
        put_on(obj_id, "table")
        '''
        
        输出: [
            'obj = "apple"',
            'obj_id = find_and_take(obj)',
            'put_on(obj_id, "table")'
        ]
    
    参数:
        source: 源代码字符串
    
    返回:
        代码块列表，每个元素是一个独立的语句
    
    异常:
        ValueError: 如果代码中包含函数定义（def/async def）
        SyntaxError: 如果代码语法错误
    """
    if not source.strip():
        return []

    # 首先尝试用 AST 解析（更准确）
    try:
        tree = ast.parse(source)
        
        # 检查是否有函数定义（不允许）
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                raise ValueError(
                    "Function definitions (def/async def) are not allowed in expanded code"
                )
        
        # 按行号提取每个语句
        lines = source.splitlines(True)
        return [
            "".join(lines[node.lineno - 1 : getattr(node, "end_lineno", node.lineno)])
            for node in tree.body
        ]
    except SyntaxError:
        pass  # AST 解析失败，回退到增量解析

    # 回退方案：使用增量编译
    import codeop
    blocks: List[str] = []
    buf: List[str] = []
    compiler = codeop.CommandCompiler()

    def flush_buf():
        if buf:
            blocks.append("".join(buf))
            buf.clear()

    for line in source.splitlines(True):
        buf.append(line)
        try:
            compiled = compiler("".join(buf), symbol="exec")
        except (SyntaxError, ValueError, OverflowError):
            # 当前缓冲区语法错误，尝试分离
            prev = buf[:-1]
            try:
                prev_compiled = compiler("".join(prev), symbol="exec") if prev else None
            except Exception:
                prev_compiled = None

            if prev and prev_compiled:
                blocks.append("".join(prev))
                buf[:] = [line]
                try:
                    compiler(line, symbol="exec")
                except Exception:
                    blocks.append(line)
                    buf.clear()
                continue

            last = buf.pop()
            blocks.append(last)
            continue

        if compiled is not None:
            flush_buf()

    if buf:
        blocks.append("".join(buf))

    return blocks


def validate_blocks(blocks: List[str]) -> None:
    """
    验证代码块列表是否合法
    
    检查内容：
    1. 每个代码块都是完整的 Python 语句
    2. 不包含函数定义（def/async def）
    
    参数:
        blocks: 代码块列表
    
    异常:
        SyntaxError: 代码块语法错误或不完整
        ValueError: 包含不允许的结构（函数定义）
    """
    import codeop
    compiler = codeop.CommandCompiler()
    
    for block in blocks:
        # 检查语法
        try:
            compiled = compiler(block, symbol="exec")
        except Exception as e:
            raise SyntaxError(f"Invalid Python block: {e}")
        
        # 检查是否完整
        if compiled is None:
            raise SyntaxError("Incomplete Python block produced by EXPAND.")
        
        # 检查是否包含函数定义
        try:
            tree = ast.parse(block)
        except SyntaxError as e:
            raise e
        
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                raise ValueError("Function definitions (def/async def) are not allowed in expanded code")


def get_variables(executor: Executor, code: str) -> str:
    """
    从代码中提取使用的变量，并获取它们的当前值
    
    这个函数用于构建 LLM 提示词，告诉 LLM 当前有哪些变量可用。
    
    参数:
        executor: 代码执行器（包含变量存储）
        code: 要分析的代码
    
    返回:
        变量列表的格式化字符串，每行一个变量：
        "- var_name (type): value"
    
    示例:
        输入代码: "find_and_take(obj, locations)"
        返回: "- obj (str): apple\n- locations (list[str]): ['cabinet 1', 'table 1']"
    """
    if not code:
        raise ValueError("No code provided to get_variables")

    def try_literal_eval(node: ast.AST):
        """尝试将 AST 节点求值为字面量"""
        try:
            return ast.literal_eval(node)
        except Exception:
            return None

    discovered_var_names: List[str] = []
    discovered_var_set = set()

    # 解析代码
    try:
        tree = ast.parse(code)
    except Exception:
        raise ValueError("Invalid code when getting variables")

    def collect_from_call(call: ast.Call):
        """从函数调用中收集变量名"""
        nonlocal discovered_var_names, discovered_var_set
        
        # 收集位置参数
        for arg in call.args:
            if isinstance(arg, ast.Name):
                var_name = arg.id
                if var_name not in discovered_var_set:
                    discovered_var_set.add(var_name)
                    discovered_var_names.append(var_name)
            
            # 收集关键字参数
            for kw in call.keywords:
                if kw.arg is None:
                    continue
                
                # 尝试解析字面量值
                literal_value = try_literal_eval(kw.value)
                if literal_value is not None:
                    executor.set_var(kw.arg, literal_value)
                    if kw.arg not in discovered_var_set:
                        discovered_var_set.add(kw.arg)
                        discovered_var_names.append(kw.arg)
                    continue
                
                # 如果是变量引用
                if isinstance(kw.value, ast.Name):
                    var_name = kw.value.id
                    if var_name not in discovered_var_set:
                        discovered_var_set.add(var_name)
                        discovered_var_names.append(var_name)

    # 遍历 AST 寻找函数调用
    for stmt in getattr(tree, "body", []):
        if isinstance(stmt, ast.Assign) and isinstance(stmt.value, ast.Call):
            collect_from_call(stmt.value)
            break
        if isinstance(stmt, ast.AnnAssign) and isinstance(getattr(stmt, "value", None), ast.Call):
            collect_from_call(stmt.value)
            break
        if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Call):
            collect_from_call(stmt.value)
            break

    # 如果还没找到，遍历整个树
    if not discovered_var_names:
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                collect_from_call(node)
                break

    if not discovered_var_names:
        return ""

    # 格式化输出
    lines: List[str] = []
    for name in discovered_var_names:
        value = executor.get_var(name)
        
        # 获取类型字符串
        if hasattr(executor, "_infer_type_string"):
            value_type = executor._infer_type_string(value)
        else:
            value_type = type(value).__name__ if value is not None else "NoneType"
        
        lines.append(f"- {name} ({value_type}): {value}")

    return "\n".join(lines)
