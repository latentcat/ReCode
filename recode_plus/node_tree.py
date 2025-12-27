"""节点树管理器"""

from __future__ import annotations
import uuid
from typing import Callable
from datetime import datetime

from .models import Node, NodeStatus, EventMessage


class NodeTree:
    """增强版代码树，支持状态追踪和可视化"""
    
    def __init__(self):
        self.root: Node | None = None
        self.nodes: dict[str, Node] = {}  # id -> Node
        self.current: Node | None = None
        self.event_handlers: list[Callable[[EventMessage], None]] = []
    
    def is_empty(self) -> bool:
        """树是否为空"""
        return self.root is None
    
    def is_complete(self) -> bool:
        """所有节点是否都已完成"""
        if not self.root:
            return False
        return all(
            node.status in (NodeStatus.COMPLETED, NodeStatus.REJECTED, NodeStatus.ERROR)
            for node in self.nodes.values()
        )
    
    def create_root(self, code: str, intent: str) -> Node:
        """创建根节点"""
        node = Node(
            id=self._generate_id(),
            code=code,
            intent=intent,
            depth=0,
        )
        self.root = node
        self.nodes[node.id] = node
        self.current = node
        
        self._emit_event(EventMessage(
            type="node_created",
            content={
                "node": node.to_dict(),
                "is_root": True,
            }
        ))
        
        return node
    
    def add_node(self, parent: Node, code: str, intent: str) -> Node:
        """添加子节点"""
        node = Node(
            id=self._generate_id(),
            code=code,
            intent=intent,
        )
        parent.add_child(node)
        self.nodes[node.id] = node
        
        self._emit_event(EventMessage(
            type="node_created",
            content={
                "node": node.to_dict(),
                "parent_id": parent.id,
            }
        ))
        
        return node
    
    def update_status(self, node: Node, status: NodeStatus):
        """更新节点状态"""
        old_status = node.status
        node.update_status(status)
        
        self._emit_event(EventMessage(
            type="node_status_changed",
            content={
                "node_id": node.id,
                "old_status": old_status.value,
                "new_status": status.value,
                "node": node.to_dict(),
            }
        ))
    
    def find_next_pending(self) -> Node | None:
        """找到下一个待执行节点（DFS）"""
        if not self.root:
            return None
        
        # 从当前节点开始查找
        if self.current:
            next_node = self.current.next()
            if next_node:
                self.current = next_node
                return next_node
        
        # 从根节点开始查找
        if self.root.status in (NodeStatus.PENDING, NodeStatus.STUB):
            self.current = self.root
            return self.root
        
        next_node = self.root.next()
        if next_node:
            self.current = next_node
        return next_node
    
    def get_node(self, node_id: str) -> Node | None:
        """根据 ID 获取节点"""
        return self.nodes.get(node_id)
    
    def all_nodes(self) -> list[Node]:
        """获取所有节点"""
        return list(self.nodes.values())
    
    def get_ancestors(self, node: Node) -> list[Node]:
        """获取所有祖先节点"""
        ancestors = []
        current = node.parent
        while current:
            ancestors.append(current)
            current = current.parent
        return ancestors
    
    def get_context(self, node: Node) -> dict:
        """获取节点的上下文（包含所有祖先的变量）"""
        context = {}
        ancestors = self.get_ancestors(node)
        ancestors.reverse()  # 从根节点开始
        
        for ancestor in ancestors:
            context.update(ancestor.variables)
        
        context.update(node.variables)
        return context
    
    def export_snapshot(self) -> dict:
        """导出当前树状态（用于可视化和持久化）"""
        return {
            "root_id": self.root.id if self.root else None,
            "current_id": self.current.id if self.current else None,
            "nodes": {
                node_id: node.to_dict() 
                for node_id, node in self.nodes.items()
            },
            "timestamp": datetime.now().isoformat(),
        }
    
    def on(self, handler: Callable[[EventMessage], None]):
        """注册事件处理器"""
        self.event_handlers.append(handler)
    
    def off(self, handler: Callable[[EventMessage], None]):
        """移除事件处理器"""
        if handler in self.event_handlers:
            self.event_handlers.remove(handler)
    
    def _emit_event(self, event: EventMessage):
        """触发事件"""
        for handler in self.event_handlers:
            try:
                handler(event)
            except Exception as e:
                print(f"Event handler error: {e}")
    
    def _generate_id(self) -> str:
        """生成唯一 ID"""
        return f"node_{uuid.uuid4().hex[:8]}"

