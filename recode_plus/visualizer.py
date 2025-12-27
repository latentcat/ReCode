"""可视化器 - 实时渲染节点树"""

from __future__ import annotations
from typing import Any
import json

from .models import Node, NodeStatus, EventMessage
from .node_tree import NodeTree


class Visualizer:
    """节点树可视化器，生成前端可用的数据"""
    
    def __init__(self, tree: NodeTree):
        """
        Args:
            tree: NodeTree 实例
        """
        self.tree = tree
        self.event_subscribers: list[Any] = []  # WebSocket 连接
    
    def subscribe(self, subscriber: Any):
        """
        订阅节点更新
        
        Args:
            subscriber: WebSocket 连接或回调函数
        """
        self.event_subscribers.append(subscriber)
        
        # 订阅树的事件
        self.tree.on(self._on_tree_event)
    
    def unsubscribe(self, subscriber: Any):
        """取消订阅"""
        if subscriber in self.event_subscribers:
            self.event_subscribers.remove(subscriber)
    
    async def emit_update(self, event: dict):
        """向所有订阅者推送更新"""
        event_json = json.dumps(event)
        
        for subscriber in self.event_subscribers:
            try:
                if hasattr(subscriber, 'send_json'):
                    # WebSocket
                    await subscriber.send_json(event)
                elif hasattr(subscriber, 'send_text'):
                    # WebSocket (text)
                    await subscriber.send_text(event_json)
                elif callable(subscriber):
                    # 回调函数
                    await subscriber(event)
            except Exception as e:
                print(f"Failed to emit update to subscriber: {e}")
    
    def render_tree_json(self) -> dict:
        """
        渲染树为 JSON（用于前端可视化）
        
        Returns:
            {
                "nodes": [...],
                "edges": [...],
                "metadata": {...}
            }
        """
        nodes = []
        edges = []
        
        for node in self.tree.all_nodes():
            nodes.append(self._render_node(node))
            
            # 添加边
            for child in node.children:
                edges.append(self._render_edge(node, child))
        
        return {
            "nodes": nodes,
            "edges": edges,
            "metadata": {
                "total_nodes": len(nodes),
                "completed": sum(1 for n in self.tree.all_nodes() if n.status == NodeStatus.COMPLETED),
                "pending": sum(1 for n in self.tree.all_nodes() if n.status == NodeStatus.PENDING),
                "error": sum(1 for n in self.tree.all_nodes() if n.status == NodeStatus.ERROR),
                "current_node_id": self.tree.current.id if self.tree.current else None,
            }
        }
    
    def render_tree_mermaid(self) -> str:
        """
        渲染树为 Mermaid 语法（用于文档）
        
        Returns:
            Mermaid flowchart 语法字符串
        """
        lines = ["graph TD"]
        
        for node in self.tree.all_nodes():
            # 节点定义
            node_shape = self._get_node_shape(node)
            node_label = self._escape_mermaid(node.intent or node.id)
            lines.append(f"    {node.id}{node_shape[0]}{node_label}{node_shape[1]}")
            
            # 边
            for child in node.children:
                lines.append(f"    {node.id} --> {child.id}")
        
        return "\n".join(lines)
    
    def _render_node(self, node: Node) -> dict:
        """渲染单个节点"""
        return {
            "id": node.id,
            "label": node.intent or node.id,
            "status": node.status.value,
            "depth": node.depth,
            "code": node.code,
            "parent_id": node.parent.id if node.parent else None,
            "children_ids": [child.id for child in node.children],
            
            # 样式相关
            "color": self._get_node_color(node.status),
            "icon": self._get_node_icon(node.status),
            
            # 详细信息
            "details": {
                "approval_required": node.approval_required,
                "approved": node.approved,
                "tool_calls": [tc.to_dict() for tc in node.tool_calls],
                "execution_result": str(node.execution_result) if node.execution_result else None,
                "error": node.error,
                "created_at": node.created_at.isoformat(),
                "updated_at": node.updated_at.isoformat(),
            }
        }
    
    def _render_edge(self, parent: Node, child: Node) -> dict:
        """渲染边"""
        return {
            "from": parent.id,
            "to": child.id,
            "type": "parent-child",
        }
    
    def _get_node_color(self, status: NodeStatus) -> str:
        """根据状态返回颜色"""
        color_map = {
            NodeStatus.PENDING: "#6B7280",       # 灰色
            NodeStatus.PLANNING: "#3B82F6",      # 蓝色
            NodeStatus.PLANNED: "#8B5CF6",       # 紫色
            NodeStatus.WAITING_APPROVAL: "#F59E0B",  # 橙色
            NodeStatus.APPROVED: "#10B981",      # 绿色
            NodeStatus.REJECTED: "#EF4444",      # 红色
            NodeStatus.EXECUTING: "#06B6D4",     # 青色
            NodeStatus.COMPLETED: "#22C55E",     # 深绿
            NodeStatus.ERROR: "#DC2626",         # 深红
            NodeStatus.STUB: "#A855F7",          # 亮紫
        }
        return color_map.get(status, "#6B7280")
    
    def _get_node_icon(self, status: NodeStatus) -> str:
        """根据状态返回图标（emoji）"""
        icon_map = {
            NodeStatus.PENDING: "⏳",
            NodeStatus.PLANNING: "🤔",
            NodeStatus.PLANNED: "📝",
            NodeStatus.WAITING_APPROVAL: "⏸️",
            NodeStatus.APPROVED: "✅",
            NodeStatus.REJECTED: "❌",
            NodeStatus.EXECUTING: "⚙️",
            NodeStatus.COMPLETED: "✔️",
            NodeStatus.ERROR: "❗",
            NodeStatus.STUB: "🔍",
        }
        return icon_map.get(status, "•")
    
    def _get_node_shape(self, node: Node) -> tuple[str, str]:
        """根据节点类型返回 Mermaid 形状"""
        if node.parent is None:
            return ("[", "]")  # 根节点：方形
        elif node.status == NodeStatus.STUB:
            return ("{{", "}}")  # STUB：菱形
        elif node.tool_calls:
            return ("([", "])")  # 有工具调用：圆角矩形
        else:
            return ("[", "]")    # 普通节点：方形
    
    def _escape_mermaid(self, text: str) -> str:
        """转义 Mermaid 特殊字符"""
        # 替换特殊字符
        text = text.replace('"', "'")
        text = text.replace("\n", " ")
        
        # 限制长度
        if len(text) > 50:
            text = text[:47] + "..."
        
        return text
    
    def _on_tree_event(self, event: EventMessage):
        """处理树事件并转发给订阅者"""
        # 异步推送更新
        import asyncio
        
        # 转换事件为前端格式
        frontend_event = {
            "type": "tree_update",
            "event": event.to_dict(),
            "tree_snapshot": self.render_tree_json(),
        }
        
        # 创建任务推送更新
        asyncio.create_task(self.emit_update(frontend_event))


class ConsoleVisualizer:
    """控制台可视化器（用于调试）"""
    
    def __init__(self, tree: NodeTree):
        self.tree = tree
        self.tree.on(self._on_tree_event)
    
    def print_tree(self):
        """在控制台打印树结构"""
        if not self.tree.root:
            print("(空树)")
            return
        
        print("\n" + "=" * 60)
        print("节点树状态")
        print("=" * 60)
        self._print_node(self.tree.root, prefix="", is_last=True)
        print("=" * 60 + "\n")
    
    def _print_node(self, node: Node, prefix: str, is_last: bool):
        """递归打印节点"""
        # 连接符
        connector = "└── " if is_last else "├── "
        
        # 状态图标
        icon = self._get_status_icon(node.status)
        
        # 打印节点
        intent = node.intent or node.code[:30]
        print(f"{prefix}{connector}{icon} {intent}")
        
        # 打印子节点
        if node.children:
            extension = "    " if is_last else "│   "
            for i, child in enumerate(node.children):
                is_last_child = (i == len(node.children) - 1)
                self._print_node(child, prefix + extension, is_last_child)
    
    def _get_status_icon(self, status: NodeStatus) -> str:
        """获取状态图标"""
        return {
            NodeStatus.PENDING: "⏳",
            NodeStatus.PLANNING: "🤔",
            NodeStatus.PLANNED: "📝",
            NodeStatus.WAITING_APPROVAL: "⏸️",
            NodeStatus.APPROVED: "✅",
            NodeStatus.REJECTED: "❌",
            NodeStatus.EXECUTING: "⚙️",
            NodeStatus.COMPLETED: "✔️",
            NodeStatus.ERROR: "❗",
            NodeStatus.STUB: "🔍",
        }.get(status, "•")
    
    def _on_tree_event(self, event: EventMessage):
        """处理树事件"""
        # 在控制台打印事件
        if event.type == "node_created":
            print(f"[+] 创建节点: {event.content.get('node', {}).get('intent', 'N/A')}")
        elif event.type == "node_status_changed":
            node_id = event.content.get('node_id', 'N/A')
            new_status = event.content.get('new_status', 'N/A')
            print(f"[~] 节点 {node_id} 状态变更: {new_status}")

