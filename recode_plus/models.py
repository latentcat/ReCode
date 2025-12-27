"""数据模型定义"""

from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class NodeStatus(str, Enum):
    """节点状态"""
    PENDING = "pending"              # 等待执行
    PLANNING = "planning"            # 规划中
    PLANNED = "planned"              # 已规划
    WAITING_APPROVAL = "waiting_approval"  # 等待审批
    APPROVED = "approved"            # 已批准
    REJECTED = "rejected"            # 已拒绝
    EXECUTING = "executing"          # 执行中
    COMPLETED = "completed"          # 已完成
    ERROR = "error"                  # 执行错误
    STUB = "stub"                    # 占位符（需要展开）


@dataclass
class ToolCall:
    """工具调用信息"""
    id: str
    name: str
    args: dict[str, Any]
    description: str                 # 给人看的描述
    requires_approval: bool = False
    approved: bool = False
    
    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "args": self.args,
            "description": self.description,
            "requires_approval": self.requires_approval,
            "approved": self.approved,
        }


@dataclass
class ToolResult:
    """工具执行结果"""
    success: bool
    output: Any = None
    task_id: str | None = None
    error: str | None = None
    
    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "output": self.output,
            "task_id": self.task_id,
            "error": self.error,
        }


@dataclass
class Node:
    """节点（代码树的节点）"""
    id: str
    code: str                        # 代码内容
    parent: Node | None = None       # 父节点
    children: list[Node] = field(default_factory=list)
    status: NodeStatus = NodeStatus.PENDING
    depth: int = 0
    
    # 新增字段
    intent: str = ""                 # 节点意图（给人看）
    tool_calls: list[ToolCall] = field(default_factory=list)
    approval_required: bool = False
    approved: bool = False
    execution_result: Any = None
    error: str | None = None
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    
    # 执行上下文
    variables: dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> dict:
        """转换为字典（用于序列化）"""
        return {
            "id": self.id,
            "code": self.code,
            "parent_id": self.parent.id if self.parent else None,
            "children_ids": [child.id for child in self.children],
            "status": self.status.value,
            "depth": self.depth,
            "intent": self.intent,
            "tool_calls": [tc.to_dict() for tc in self.tool_calls],
            "approval_required": self.approval_required,
            "approved": self.approved,
            "execution_result": str(self.execution_result) if self.execution_result else None,
            "error": self.error,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }
    
    def update_status(self, new_status: NodeStatus):
        """更新状态"""
        self.status = new_status
        self.updated_at = datetime.now()
    
    def add_child(self, child: Node):
        """添加子节点"""
        self.children.append(child)
        child.parent = self
        child.depth = self.depth + 1
    
    def next(self) -> Node | None:
        """找到下一个待执行的节点（DFS）"""
        # 1. 先看子节点
        for child in self.children:
            if child.status in (NodeStatus.PENDING, NodeStatus.STUB):
                return child
            # 递归查找
            next_child = child.next()
            if next_child:
                return next_child
        
        # 2. 再看兄弟节点
        if self.parent:
            siblings = self.parent.children
            try:
                my_index = siblings.index(self)
                for sibling in siblings[my_index + 1:]:
                    if sibling.status in (NodeStatus.PENDING, NodeStatus.STUB):
                        return sibling
                    next_sibling = sibling.next()
                    if next_sibling:
                        return next_sibling
            except ValueError:
                pass
            
            # 3. 向上回溯
            return self.parent.next()
        
        return None


@dataclass
class Plan:
    """规划结果"""
    code: str                        # 根节点代码
    summary: str                     # 规划摘要
    estimated_steps: int = 0         # 预估步数
    
    def to_dict(self) -> dict:
        return {
            "code": self.code,
            "summary": self.summary,
            "estimated_steps": self.estimated_steps,
        }


@dataclass
class EventMessage:
    """事件消息（发送给前端）"""
    type: str                        # thinking, explanation, approval_request, node_update
    content: Any
    timestamp: datetime = field(default_factory=datetime.now)
    
    def to_dict(self) -> dict:
        return {
            "type": self.type,
            "content": self.content,
            "timestamp": self.timestamp.isoformat(),
        }

