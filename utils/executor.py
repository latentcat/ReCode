"""
Python 代码执行器模块

这是 ReCode 的"手脚"，负责实际执行代码片段。

核心职责：
1. 执行 Python 代码
2. 管理变量存储
3. 调用环境接口（run 函数）
4. 识别占位函数（NeedExpansion 机制）

关键机制 - 占位函数检测：
    当执行 find_and_take(obj) 这样的代码时，
    如果 find_and_take 没有定义，Python 会抛出 NameError。
    Executor 捕获这个错误，判断它是占位函数调用，
    返回 "NeedExpansion" 信号而不是当作真正的错误。
"""

from typing import List, Dict, Any, Callable
import io
import sys
import functools
import asyncio
import types
import re
import threading
import time

from utils.llm import AsyncLLM
from base.environment import Env


def print_output(func):
    """
    装饰器：让函数的返回值自动打印到标准输出
    
    用于 run() 函数，让环境返回的观察自动显示。
    """
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        result = func(*args, **kwargs)
        if result is not None:
            print(result, file=sys.stdout, flush=True)
        return result
    return wrapper


class Executor:
    """
    Python 代码执行器
    
    负责在受控环境中执行代码，管理变量，并与环境交互。
    
    核心特性：
    1. 变量管理：保存和读取执行过程中产生的变量
    2. 环境交互：通过 run() 函数调用环境的动作
    3. 占位函数检测：识别未定义的函数调用
    
    使用示例：
        executor = Executor()
        executor.set_env(my_env)
        executor.set_var('obj', 'apple')
        result = executor.execute("obj_id = find_and_take(obj)")
        # result = {"success": False, "error": "NeedExpansion: ..."}
    """
    
    def __init__(self, env: Env = None, if_run_print: bool = False) -> None:
        """
        初始化执行器
        
        参数:
            env: 环境实例（可以稍后通过 set_env 设置）
            if_run_print: 是否在 run() 调用时自动打印结果
        """
        self.env = env
        self.actions: List[str] = []           # 记录所有执行的动作
        self._variables: Dict[str, Any] = {}   # 变量存储
        self.if_run_print = if_run_print
        
        # 如果需要打印，用装饰器包装 run 方法
        if self.if_run_print:
            self.run = print_output(self.run)
        
        # 基础全局变量：代码执行时可以访问的函数
        self._base_globals = {
            "run": self.run,    # 执行动作的核心函数
            "re": re,           # 正则表达式模块
        }
        
        # 异步事件循环（用于在同步代码中调用异步函数）
        self._loop = None
        self._loop_thread = None
        self._start_loop_thread()

    # ==================== 函数注册方法 ====================

    def register_function(self, name: str, func: Callable):
        """
        注册一个函数到全局命名空间
        
        注册后，执行的代码中可以直接调用这个函数。
        """
        self._base_globals[name] = func
    
    def register_action_function(self, name: str, func: Callable):
        """
        注册一个动作函数（自动包装 run 调用）
        """
        func_with_run = lambda *args, **kwargs: self.run(func(*args, **kwargs))
        self.register_function(name, func_with_run)

    def register_ask_llm(self, llm: AsyncLLM):
        """
        注册 LLM 调用函数
        
        让执行的代码可以通过 ask_llm() 查询 LLM。
        """
        def _ask_llm_sync(query: str) -> str:
            async def _ask_llm(query: str) -> str:
                response, _cost = await llm(prompt=query)
                return response
            return self._submit_coro(_ask_llm(query))
        self.register_function("ask_llm", _ask_llm_sync)

    # ==================== 变量管理方法 ====================

    def skip(self, reason: str):
        """
        跳过操作（占位用）
        """
        return None
    
    def set_var(self, key: str, value: Any):
        """
        设置变量
        
        设置的变量在执行代码时可以访问。
        """
        self._variables[key] = value
    
    def get_var(self, key: str) -> Any:
        """
        获取变量值
        """
        if key not in self._variables:
            return None
        return self._variables.get(key)
    
    def set_env(self, env: Env):
        """
        设置环境实例
        """
        self.env = env
    
    def _is_preserved_variable(self, key: str, value: Any) -> bool:
        """
        判断变量是否应该被保留
        
        过滤掉：
        - 下划线开头的变量
        - 基础全局变量
        - 模块、函数、类等非数据类型
        """
        if key.startswith('_') or key in self._base_globals:
            return False
        return not isinstance(value, (types.ModuleType, types.FunctionType, 
                                    types.BuiltinFunctionType, types.MethodType, type))
    
    def _infer_type_string(self, value: Any, depth: int = 0, max_depth: int = 2) -> str:
        """
        推断值的类型字符串
        
        返回人类可读的类型描述，如 "list[str]", "dict[str, int]"。
        """
        if value is None:
            return "NoneType"
        if depth > max_depth:
            return type(value).__name__
        try:
            if isinstance(value, (bool, int, float, str)):
                return type(value).__name__
            if isinstance(value, list):
                if not value:
                    return "list"
                elem_types = {self._infer_type_string(v, depth + 1, max_depth) for v in value[:5]}
                if len(elem_types) == 1:
                    return f"list[{next(iter(elem_types))}]"
                return "list"
            if isinstance(value, tuple):
                if not value:
                    return "tuple"
                elem_types = [self._infer_type_string(v, depth + 1, max_depth) for v in value[:5]]
                if all(t == elem_types[0] for t in elem_types):
                    return f"tuple[{elem_types[0]}]"
                return f"tuple[{', '.join(elem_types)}]"
            if isinstance(value, set):
                if not value:
                    return "set"
                sample = list(value)[:5]
                elem_types = {self._infer_type_string(v, depth + 1, max_depth) for v in sample}
                if len(elem_types) == 1:
                    return f"set[{next(iter(elem_types))}]"
                return "set"
            if isinstance(value, dict):
                if not value:
                    return "dict"
                items = list(value.items())[:5]
                key_types = {self._infer_type_string(k, depth + 1, max_depth) for k, _ in items}
                val_types = {self._infer_type_string(v, depth + 1, max_depth) for _, v in items}
                if len(key_types) == 1 and len(val_types) == 1:
                    return f"dict[{next(iter(key_types))}, {next(iter(val_types))}]"
                return "dict"
            return type(value).__name__
        except Exception:
            return type(value).__name__

    # ==================== 核心执行方法 ====================
    
    def run(self, action: str) -> str:
        """
        执行环境动作
        
        这是代码中调用 run("go to table") 时实际执行的函数。
        
        参数:
            action: 动作字符串
        
        返回:
            环境返回的观察结果
        """
        if self.env is None:
            raise RuntimeError("Environment not set. Call set_env() first.")
        
        # 调用异步环境方法
        result = self._submit_coro(self.env.run(action))
        
        # 记录动作
        self.actions.append(action)
        
        # 将列表结果合并为字符串
        if isinstance(result, list):
            result = "\n".join(result)
        return result
    
    def get_actions(self) -> List[str]:
        """
        获取并清空动作列表
        """
        actions = self.actions.copy()
        self.actions.clear()
        return actions
    
    def get_variables(self) -> str:
        """
        获取所有变量的格式化字符串
        """
        return "\n".join([
            f"- {key} ({self._infer_type_string(value)}): {value}" 
            for key, value in self._variables.items()
        ])
    
    def reset(self):
        """
        重置执行器状态
        """
        self.actions.clear()
        self._variables.clear()

    # ==================== 异步支持方法 ====================

    def _start_loop_thread(self):
        """
        启动后台事件循环线程
        
        用于在同步代码中执行异步函数（如环境的 run 方法）。
        """
        if self._loop and self._loop.is_running():
            return
            
        def _loop_runner():
            loop = asyncio.new_event_loop()
            self._loop = loop
            asyncio.set_event_loop(loop)
            loop.run_forever()
            
        t = threading.Thread(target=_loop_runner, daemon=True)
        t.start()
        
        # 等待循环启动
        while self._loop is None or not self._loop.is_running():
            time.sleep(0.01)
        self._loop_thread = t

    def _submit_coro(self, coro):
        """
        提交协程到后台事件循环执行
        
        这允许在同步代码中调用异步函数。
        """
        self._start_loop_thread()
        future = asyncio.run_coroutine_threadsafe(coro, self._loop)
        return future.result()

    def close(self):
        """
        关闭执行器，停止事件循环
        """
        if self._loop and self._loop.is_running():
            try:
                self._loop.call_soon_threadsafe(self._loop.stop)
            except Exception:
                pass
            if self._loop_thread:
                self._loop_thread.join(timeout=1)
        self._loop = None
        self._loop_thread = None

    # ==================== 代码执行核心 ====================

    def execute(self, code: str) -> Dict[str, Any]:
        """
        执行一段代码
        
        这是主要的执行入口，封装了 _run_block 并返回结构化结果。
        
        参数:
            code: 要执行的代码字符串
        
        返回:
            字典包含：
            - code: 原始代码
            - stdout: 标准输出列表
            - error: 错误信息（如果有）
            - success: 是否成功
        """
        success, stdout_lines, error_msg = self._run_block(code)
        return {
            "code": code, 
            "stdout": stdout_lines, 
            "error": error_msg, 
            "success": success
        }

    def _run_block(self, block: str) -> tuple[bool, List[str], str]:
        """
        执行代码块的核心方法
        
        这里实现了 ReCode 的核心机制——占位函数检测。
        
        返回:
            (success, stdout_lines, error_msg) 元组
        
        关键逻辑：
            当代码调用未定义的函数时（如 find_and_take），
            Python 会抛出 NameError。
            我们检查这个错误，如果是函数调用，
            返回 "NeedExpansion" 而不是当作真正的错误。
        """
        output = []
        
        # 自定义输出捕获类
        class OutputCapture:
            def __init__(self):
                self.lines = []
            def write(self, text):
                if text and text != '\n':
                    self.lines.extend(line for line in text.splitlines() if line.strip())
            def flush(self): 
                pass

        # 重定向标准输出
        capture = OutputCapture()
        old_stdout = sys.stdout
        sys.stdout = capture
        
        # 构建执行环境：基础全局变量 + 用户变量
        exec_globals = {**self._base_globals, **self._variables}
        
        try:
            # 执行代码
            exec(block, exec_globals)
            
            # 保存新产生的变量
            for key, value in exec_globals.items():
                if self._is_preserved_variable(key, value):
                    self._variables[key] = value
            
            return True, capture.lines, ""
            
        except NameError as e:
            # ========== 关键：占位函数检测 ==========
            # 检查是否是 "name 'xxx' is not defined" 格式
            match = re.search(r"name '(.+?)' is not defined", str(e))
            
            # 如果是，且代码中有 xxx( 这样的函数调用
            if match and f"{match.group(1)}(" in block:
                # 这是占位函数！返回 NeedExpansion 信号
                return False, capture.lines, f"NeedExpansion: `{match.group(1)}` needs to be expanded."
            
            # 否则是真正的 NameError
            return False, capture.lines, f"NameError: {e}"
            
        except Exception as e:
            # 其他异常
            return False, capture.lines, f"{e.__class__.__name__}: {e}"
            
        finally:
            # 恢复标准输出
            sys.stdout = old_stdout
