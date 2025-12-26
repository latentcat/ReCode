"""
自定义异常模块

定义项目中使用的自定义异常类。
"""


class StepLimitError(Exception):
    """
    步数限制异常
    
    当环境执行的步数超过最大允许步数时抛出。
    用于防止 Agent 陷入无限循环或执行过长。
    
    使用示例：
        if step_count > max_steps:
            raise StepLimitError(f"Step limit of {max_steps} exceeded.")
    """
    pass 
