"""执行 Agent - 负责调用外部工具（基于 Pydantic AI）"""

from __future__ import annotations
import re
import uuid
from typing import Any

from .models import ToolCall, ToolResult, Node


class ExecutorAgent:
    """执行 Agent，负责类型安全的工具调用"""
    
    def __init__(self, project_id: str = "default"):
        """
        Args:
            project_id: 项目 ID（用于工具调用）
        """
        self.project_id = project_id
        self.tools: dict[str, Any] = {}
        self._init_tools()
    
    def _init_tools(self):
        """初始化工具（集成 Pydantic AI 工具）"""
        try:
            # 集成你的 Pydantic AI 工具
            import sys
            from pathlib import Path
            
            agent_path = Path("E:/ShichenPro/mono-playground/python_packages/unified-api")
            if agent_path.exists() and str(agent_path) not in sys.path:
                sys.path.insert(0, str(agent_path))
            
            from gateway.agent.tools import (
                propose_image,
                propose_video,
                execute_image_generation,
                execute_video_generation,
            )
            
            self.tools = {
                "propose_image": propose_image,
                "propose_video": propose_video,
                "execute_image_generation": execute_image_generation,
                "execute_video_generation": execute_video_generation,
            }
        except ImportError as e:
            print(f"Warning: Failed to import Pydantic AI tools: {e}")
            # 使用模拟工具
            self.tools = {
                "generate_image": self._mock_generate_image,
                "generate_video": self._mock_generate_video,
                "ask": self._mock_ask,
            }
    
    def extract_tool_calls(self, code: str) -> list[ToolCall]:
        """
        从代码中提取工具调用
        
        Args:
            code: 代码字符串
        
        Returns:
            工具调用列表
        """
        tool_calls = []
        
        # 正则匹配函数调用: func_name(arg1=val1, arg2=val2)
        pattern = r'(\w+)\s*\((.*?)\)'
        matches = re.finditer(pattern, code, re.DOTALL)
        
        for match in matches:
            func_name = match.group(1)
            args_str = match.group(2)
            
            # 检查是否是已知工具
            if not self._is_tool(func_name):
                continue
            
            # 解析参数
            args = self._parse_args(args_str)
            
            # 创建 ToolCall
            tool_call = ToolCall(
                id=self._generate_id(),
                name=func_name,
                args=args,
                description=self._generate_description(func_name, args),
                requires_approval=self._requires_approval(func_name, args),
            )
            
            tool_calls.append(tool_call)
        
        return tool_calls
    
    async def execute_tool(self, tool_call: ToolCall, context: dict | None = None) -> ToolResult:
        """
        执行工具调用（带 Pydantic 校验）
        
        Args:
            tool_call: 工具调用对象
            context: 执行上下文
        
        Returns:
            工具执行结果
        """
        tool_func = self.tools.get(tool_call.name)
        
        if not tool_func:
            return ToolResult(
                success=False,
                error=f"未知工具: {tool_call.name}"
            )
        
        try:
            # 根据工具类型执行
            if tool_call.name == "propose_image":
                return await self._execute_propose_image(tool_call)
            
            elif tool_call.name == "propose_video":
                return await self._execute_propose_video(tool_call)
            
            elif tool_call.name == "generate_image":
                return await self._execute_generate_image(tool_call)
            
            elif tool_call.name == "generate_video":
                return await self._execute_generate_video(tool_call)
            
            elif tool_call.name == "ask":
                return await self._execute_ask(tool_call, context)
            
            else:
                # 通用执行
                result = await tool_func(**tool_call.args)
                return ToolResult(success=True, output=result)
        
        except Exception as e:
            return ToolResult(success=False, error=f"执行错误: {str(e)}")
    
    async def _execute_propose_image(self, tool_call: ToolCall) -> ToolResult:
        """执行 propose_image 工具"""
        try:
            from gateway.agent.models import BananaImageTaskInput
            from gateway.agent.tools import execute_image_generation
            
            # Pydantic 校验
            validated_input = BananaImageTaskInput(**tool_call.args)
            
            # 执行图片生成
            task_id = await execute_image_generation(
                project_id=self.project_id,
                is_paid=False,
                conversation_id=None,
                tool_call_id=tool_call.id,
                input=validated_input,
            )
            
            return ToolResult(
                success=True,
                task_id=task_id,
                output=f"图片生成任务已创建: {task_id}"
            )
        
        except Exception as e:
            return ToolResult(success=False, error=str(e))
    
    async def _execute_propose_video(self, tool_call: ToolCall) -> ToolResult:
        """执行 propose_video 工具"""
        try:
            from gateway.agent.models import VeoVideoTaskInput
            from gateway.agent.tools import execute_video_generation
            
            # Pydantic 校验
            validated_input = VeoVideoTaskInput(**tool_call.args)
            
            # 执行视频生成
            task_id = await execute_video_generation(
                project_id=self.project_id,
                is_paid=False,
                conversation_id=None,
                tool_call_id=tool_call.id,
                input=validated_input,
            )
            
            return ToolResult(
                success=True,
                task_id=task_id,
                output=f"视频生成任务已创建: {task_id}"
            )
        
        except Exception as e:
            return ToolResult(success=False, error=str(e))
    
    async def _execute_generate_image(self, tool_call: ToolCall) -> ToolResult:
        """执行 generate_image（模拟）"""
        return await self._mock_generate_image(**tool_call.args)
    
    async def _execute_generate_video(self, tool_call: ToolCall) -> ToolResult:
        """执行 generate_video（模拟）"""
        return await self._mock_generate_video(**tool_call.args)
    
    async def _execute_ask(self, tool_call: ToolCall, context: dict | None) -> ToolResult:
        """执行 ask（对话）"""
        return await self._mock_ask(**tool_call.args)
    
    def _is_tool(self, func_name: str) -> bool:
        """检查函数是否是工具"""
        known_tools = {
            "propose_image", "propose_video",
            "generate_image", "generate_video",
            "ask", "finish"
        }
        return func_name in self.tools or func_name in known_tools
    
    def _parse_args(self, args_str: str) -> dict[str, Any]:
        """解析参数字符串"""
        args = {}
        
        if not args_str.strip():
            return args
        
        # 简单解析: key=value, key=value
        # 注意：这是一个简化版本，实际需要更复杂的解析
        pairs = re.findall(r'(\w+)\s*=\s*([^,]+)', args_str)
        
        for key, value in pairs:
            value = value.strip()
            
            # 移除引号
            if value.startswith('"') and value.endswith('"'):
                value = value[1:-1]
            elif value.startswith("'") and value.endswith("'"):
                value = value[1:-1]
            
            # 尝试转换类型
            if value.lower() == 'true':
                value = True
            elif value.lower() == 'false':
                value = False
            elif value.isdigit():
                value = int(value)
            
            args[key] = value
        
        return args
    
    def _generate_description(self, func_name: str, args: dict) -> str:
        """生成工具调用的描述"""
        if func_name == "generate_image":
            prompt = args.get("prompt", "")[:50]
            return f"生成图片: {prompt}..."
        
        elif func_name == "generate_video":
            prompt = args.get("prompt", "")[:50]
            return f"生成视频: {prompt}..."
        
        elif func_name == "ask":
            question = args.get("question", "")[:50]
            return f"提问: {question}..."
        
        else:
            return f"执行 {func_name}"
    
    def _requires_approval(self, func_name: str, args: dict) -> bool:
        """判断是否需要审批"""
        # propose_image 和 propose_video 支持动态审批
        if func_name in ("propose_image", "propose_video"):
            return args.get("request_review", False)
        
        # 其他工具默认不需要审批
        return False
    
    def _generate_id(self) -> str:
        """生成唯一 ID"""
        return f"tool_{uuid.uuid4().hex[:8]}"
    
    # ============ 模拟工具（用于测试） ============
    
    async def _mock_generate_image(self, prompt: str, **kwargs) -> ToolResult:
        """模拟图片生成"""
        return ToolResult(
            success=True,
            task_id=f"img_{uuid.uuid4().hex[:8]}",
            output=f"[模拟] 图片生成中: {prompt}"
        )
    
    async def _mock_generate_video(self, prompt: str, **kwargs) -> ToolResult:
        """模拟视频生成"""
        return ToolResult(
            success=True,
            task_id=f"vid_{uuid.uuid4().hex[:8]}",
            output=f"[模拟] 视频生成中: {prompt}"
        )
    
    async def _mock_ask(self, question: str, **kwargs) -> ToolResult:
        """模拟对话"""
        return ToolResult(
            success=True,
            output=f"[模拟] AI 回复: 关于'{question}'的建议..."
        )

