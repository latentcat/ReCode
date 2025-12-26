"""
日志工具模块

提供结构化的日志记录功能，用于记录 Agent 运行过程和结果。

主要类：
- MultiLineFormatter: 多行日志格式化器
- SimpleLogger: 简单日志记录器

日志目录结构：
    logs/
    └── <run_id>/
        └── running_logs/
            ├── run.log           # 主运行日志
            └── instance_*.log    # 每个实例的单独日志
"""

import os
import logging
from datetime import datetime
from pathlib import Path


class MultiLineFormatter(logging.Formatter):
    """
    多行日志格式化器
    
    让多行日志消息保持正确的格式，不会因为换行而破坏日志结构。
    """
    
    def format(self, record):
        """格式化日志记录"""
        msg = super().format(record)
        
        # 如果消息包含多行，保持原样
        lines = msg.split('\n')
        if len(lines) <= 1:
            return msg
            
        return '\n'.join(lines)


class SimpleLogger:
    """
    简单日志记录器
    
    封装 Python 的 logging 模块，提供统一的日志接口。
    
    特性：
    - 同时输出到文件和控制台
    - 自动创建日志目录
    - 支持多行日志格式化
    - 提供结果和统计信息的专用记录方法
    
    使用示例：
        logger = SimpleLogger(run_id="my_experiment")
        logger.info("开始运行...")
        logger.error("发生错误")
        logger.log_stats({"total_tests": 10, "successful_tests": 8})
    """
    
    def __init__(self, run_id=None, log_level=logging.INFO):
        """
        初始化日志记录器
        
        参数:
            run_id: 运行标识符，用于创建日志目录名
                   如果不提供，使用当前时间戳
            log_level: 日志级别，默认 INFO
        """
        # 生成 run_id
        if run_id is None:
            run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        self.run_id = run_id
        
        # 设置日志目录结构
        self.base_dir = Path("logs") / run_id           # 基础目录: logs/<run_id>/
        self.log_dir = self.base_dir / "running_logs"   # 日志目录: logs/<run_id>/running_logs/
        
        # 创建目录
        self.log_dir.mkdir(parents=True, exist_ok=True)
        
        # 创建 logger 实例（使用 run_id 作为名称避免冲突）
        sanitized_run_id = run_id.replace("/", "_").replace("\\", "_")
        self.logger = logging.getLogger(f"alfworld_run_{sanitized_run_id}")
        self.logger.setLevel(log_level)
        
        # 清除之前的 handlers（防止重复添加）
        self.logger.handlers.clear()
        
        # 创建文件 handler
        log_file = self.log_dir / "run.log"
        file_handler = logging.FileHandler(log_file, mode='w', encoding='utf-8')
        file_handler.setLevel(log_level)
        
        # 创建控制台 handler
        console_handler = logging.StreamHandler()
        console_handler.setLevel(log_level)
        
        # 设置格式化器
        formatter = MultiLineFormatter('%(asctime)s - %(levelname)s - %(message)s')
        file_handler.setFormatter(formatter)
        console_handler.setFormatter(formatter)
        
        # 添加 handlers
        self.logger.addHandler(file_handler)
        self.logger.addHandler(console_handler)
        
        # 记录初始信息
        self.info(f"Starting new run with ID: {run_id}")
        self.info(f"Logs will be saved to: {self.log_dir.absolute()}")
    
    # ==================== 基础日志方法 ====================
    
    def info(self, message):
        """记录信息级别日志"""
        self.logger.info(message)
    
    def error(self, message):
        """记录错误级别日志"""
        self.logger.error(message)
    
    def warning(self, message):
        """记录警告级别日志"""
        self.logger.warning(message)
    
    def debug(self, message):
        """记录调试级别日志"""
        self.logger.debug(message)
    
    # ==================== 专用记录方法 ====================
    
    def log_result(self, result):
        """
        记录单个任务的执行结果
        
        参数:
            result: 结果字典，应包含：
                - task_id: 任务 ID
                - both_success 或 is_success: 是否成功
                - execution_time 或 time: 执行时间
                - game_name: 游戏/任务名称
                - error (可选): 错误信息
        """
        task_id = result.get("task_id", "unknown")
        success = result.get("both_success", result.get("is_success", False))
        exec_time = result.get("execution_time", result.get("time", 0))
        game_name = result.get("game_name", "")
        
        status = "SUCCESS" if success else "FAILED"
        self.info(f"[{status}] {task_id} - {game_name} - {exec_time:.2f}s")
        
        # 如果有错误，单独记录
        if "error" in result:
            self.error(f"Error in {task_id}: {result['error']}")
    
    def log_stats(self, stats):
        """
        记录运行统计信息
        
        参数:
            stats: 统计字典，应包含：
                - total_tests: 总测试数
                - successful_tests: 成功数
                - success_rate: 成功率
                - average_execution_time: 平均执行时间
                - task_types (可选): 按任务类型的统计
        """
        self.info("=" * 50)
        self.info("RUN STATISTICS")
        self.info("=" * 50)
        self.info(f"Total tests: {stats['total_tests']}")
        self.info(f"Successful: {stats['successful_tests']}")
        self.info(f"Success rate: {stats['success_rate']:.1%}")
        self.info(f"Average execution time: {stats['average_execution_time']:.2f}s")
        
        # 按任务类型统计（如果有）
        if stats.get('task_types'):
            self.info("\nSuccess rate by task type:")
            for task_type, type_stats in stats['task_types'].items():
                rate = type_stats['rate']
                total = type_stats['total']
                success = type_stats['success']
                self.info(f"  {task_type}: {success}/{total} ({rate:.1%})")
    
    # ==================== 路径获取方法 ====================
    
    def get_log_dir(self):
        """
        获取日志目录路径
        
        返回: logs/<run_id>/running_logs/
        """
        return self.log_dir

    def get_base_dir(self):
        """
        获取基础目录路径
        
        返回: logs/<run_id>/
        """
        return self.base_dir 
