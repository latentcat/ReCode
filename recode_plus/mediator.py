"""中间人 Agent - 协调人机交互"""

from __future__ import annotations
import asyncio
from typing import AsyncGenerator
from collections.abc import Awaitable

from .models import Node, NodeStatus, EventMessage, ToolCall
from .node_tree import NodeTree
from .planner import PlannerAgent
from .executor import ExecutorAgent


class MediatorAgent:
    """
    中间人 Agent，负责：
    1. 与用户对话
    2. 解释节点状态
    3. 协调 Planner 和 Executor
    4. 管理人类审批流程
    """
    
    def __init__(self, llm, project_id: str = "default"):
        """
        Args:
            llm: AsyncLLM 实例
            project_id: 项目 ID
        """
        self.tree = NodeTree()
        self.planner = PlannerAgent(llm)
        self.executor = ExecutorAgent(project_id)
        self.conversation_history: list[dict] = []
        
        # 审批管理
        self.pending_approvals: dict[str, asyncio.Future] = {}  # tool_call_id -> Future
        
        # 订阅树事件
        self.tree.on(self._on_tree_event)
    
    async def chat_stream(
        self, 
        user_message: str
    ) -> AsyncGenerator[EventMessage, None]:
        """
        流式对话接口
        
        Args:
            user_message: 用户消息
        
        Yields:
            EventMessage: 事件消息
        """
        # 1. 记录对话
        self.conversation_history.append({
            "role": "user",
            "content": user_message,
        })
        
        # 2. 理解用户意图
        yield EventMessage(
            type="thinking",
            content="正在理解你的需求..."
        )
        
        intent = await self._understand_intent(user_message)
        
        yield EventMessage(
            type="explanation",
            content=f"我理解到你想要: {intent}"
        )
        
        # 3. 如果树为空，创建初始规划
        if self.tree.is_empty():
            yield EventMessage(
                type="thinking",
                content="正在规划任务..."
            )
            
            plan = await self.planner.create_plan(intent)
            
            yield EventMessage(
                type="explanation",
                content=f"我将这样规划任务:\n\n{plan.summary}\n\n预计需要 {plan.estimated_steps} 步"
            )
            
            # 创建根节点
            root = self.tree.create_root(plan.code, intent)
            
            yield EventMessage(
                type="node_update",
                content={
                    "action": "created",
                    "node": root.to_dict(),
                }
            )
        
        # 4. 执行循环
        async for event in self._execute_loop():
            yield event
        
        # 5. 检查是否完成
        if self.tree.is_complete():
            yield EventMessage(
                type="completion",
                content="所有任务已完成！"
            )
    
    async def approve_tool(self, tool_call_id: str) -> bool:
        """
        批准工具调用
        
        Args:
            tool_call_id: 工具调用 ID
        
        Returns:
            是否成功批准
        """
        if tool_call_id in self.pending_approvals:
            future = self.pending_approvals[tool_call_id]
            future.set_result(True)
            del self.pending_approvals[tool_call_id]
            return True
        return False
    
    async def reject_tool(self, tool_call_id: str) -> bool:
        """
        拒绝工具调用
        
        Args:
            tool_call_id: 工具调用 ID
        
        Returns:
            是否成功拒绝
        """
        if tool_call_id in self.pending_approvals:
            future = self.pending_approvals[tool_call_id]
            future.set_result(False)
            del self.pending_approvals[tool_call_id]
            return True
        return False
    
    def get_tree_snapshot(self) -> dict:
        """获取当前树状态快照"""
        return self.tree.export_snapshot()
    
    async def _execute_loop(self) -> AsyncGenerator[EventMessage, None]:
        """执行循环：遍历节点树并执行"""
        max_iterations = 100
        iteration = 0
        
        while not self.tree.is_complete() and iteration < max_iterations:
            iteration += 1
            
            # 找到下一个待执行节点
            current = self.tree.find_next_pending()
            
            if not current:
                break
            
            yield EventMessage(
                type="thinking",
                content=f"[深度 {current.depth}] 准备执行: {current.intent}"
            )
            
            # 根据节点状态执行不同操作
            if current.status == NodeStatus.STUB:
                # 展开 STUB 节点
                async for event in self._expand_node(current):
                    yield event
            
            elif current.status == NodeStatus.PENDING:
                # 执行节点
                async for event in self._execute_node(current):
                    yield event
            
            else:
                # 跳过其他状态
                pass
            
            # 短暂休息，避免过于密集
            await asyncio.sleep(0.1)
    
    async def _expand_node(self, node: Node) -> AsyncGenerator[EventMessage, None]:
        """展开 STUB 节点"""
        yield EventMessage(
            type="explanation",
            content=f"正在展开节点: {node.intent}"
        )
        
        # 更新状态
        self.tree.update_status(node, NodeStatus.PLANNING)
        
        # 获取上下文
        context = self.tree.get_context(node)
        
        # 请求 Planner 展开
        try:
            expansions = await self.planner.expand(node, context)
            
            # 向用户解释展开
            explanation_lines = [f"将 '{node.intent}' 拆解为:"]
            for i, (code, intent) in enumerate(expansions, 1):
                explanation_lines.append(f"{i}. {intent}")
            
            yield EventMessage(
                type="explanation",
                content="\n".join(explanation_lines)
            )
            
            # 添加子节点
            for child_code, child_intent in expansions:
                child = self.tree.add_node(node, child_code, child_intent)
                
                yield EventMessage(
                    type="node_update",
                    content={
                        "action": "created",
                        "node": child.to_dict(),
                    }
                )
            
            # 更新状态为已规划
            self.tree.update_status(node, NodeStatus.PLANNED)
        
        except Exception as e:
            yield EventMessage(
                type="error",
                content=f"展开失败: {str(e)}"
            )
            self.tree.update_status(node, NodeStatus.ERROR)
            node.error = str(e)
    
    async def _execute_node(self, node: Node) -> AsyncGenerator[EventMessage, None]:
        """执行节点"""
        yield EventMessage(
            type="thinking",
            content=f"执行: {node.intent}"
        )
        
        # 提取工具调用
        tool_calls = self.executor.extract_tool_calls(node.code)
        
        if not tool_calls:
            # 没有工具调用，直接标记完成
            self.tree.update_status(node, NodeStatus.COMPLETED)
            yield EventMessage(
                type="explanation",
                content=f"✓ {node.intent} 完成"
            )
            return
        
        # 执行每个工具调用
        for tool_call in tool_calls:
            node.tool_calls.append(tool_call)
            
            # 检查是否需要审批
            if tool_call.requires_approval:
                # 请求人类审批
                yield EventMessage(
                    type="approval_request",
                    content={
                        "node_id": node.id,
                        "tool_call": tool_call.to_dict(),
                        "explanation": f"需要你确认: {tool_call.description}",
                    }
                )
                
                # 等待审批
                approved = await self._wait_for_approval(tool_call.id)
                
                if not approved:
                    self.tree.update_status(node, NodeStatus.REJECTED)
                    yield EventMessage(
                        type="explanation",
                        content="已取消该操作"
                    )
                    return
                
                tool_call.approved = True
            
            # 执行工具
            self.tree.update_status(node, NodeStatus.EXECUTING)
            
            yield EventMessage(
                type="explanation",
                content=f"正在执行: {tool_call.description}"
            )
            
            context = self.tree.get_context(node)
            result = await self.executor.execute_tool(tool_call, context)
            
            if result.success:
                node.execution_result = result.output
                
                # 如果有 task_id，记录下来
                if result.task_id:
                    node.variables[f"task_{tool_call.name}"] = result.task_id
                
                yield EventMessage(
                    type="explanation",
                    content=f"✓ {tool_call.description} 完成"
                )
                
                if result.task_id:
                    yield EventMessage(
                        type="task_created",
                        content={
                            "task_id": result.task_id,
                            "tool_call_id": tool_call.id,
                            "description": tool_call.description,
                        }
                    )
            else:
                node.error = result.error
                self.tree.update_status(node, NodeStatus.ERROR)
                
                yield EventMessage(
                    type="error",
                    content=f"✗ {tool_call.description} 失败: {result.error}"
                )
                return
        
        # 所有工具调用完成
        self.tree.update_status(node, NodeStatus.COMPLETED)
    
    async def _wait_for_approval(self, tool_call_id: str) -> bool:
        """等待人类审批"""
        # 创建一个 Future
        future: asyncio.Future[bool] = asyncio.Future()
        self.pending_approvals[tool_call_id] = future
        
        # 等待结果（带超时）
        try:
            approved = await asyncio.wait_for(future, timeout=300.0)  # 5分钟超时
            return approved
        except asyncio.TimeoutError:
            # 超时，视为拒绝
            if tool_call_id in self.pending_approvals:
                del self.pending_approvals[tool_call_id]
            return False
    
    async def _understand_intent(self, message: str) -> str:
        """理解用户意图（简化版）"""
        # 在完整实现中，这里可以调用 LLM 进行意图识别
        # 目前直接返回消息本身
        return message
    
    def _on_tree_event(self, event: EventMessage):
        """处理树事件（可用于日志、持久化等）"""
        # 这里可以添加日志记录、持久化等逻辑
        pass

