# ReCode+ 架构设计文档

> 融合 ReCode、Pydantic AI 和人机协作的新一代 Agent 框架

---

## 核心理念

ReCode+ = **递归规划** + **格式化工具** + **人机协作** + **实时可视化**

### 设计目标

1. ✅ **ReCode 的递归代码生成**：自动展开复杂任务为代码树
2. ✅ **Pydantic AI 的类型安全**：工具输入/输出严格校验
3. ✅ **人类审批机制**：关键节点需要人工确认
4. ✅ **中间人解释**：每个节点的意图和状态都向用户说明
5. ✅ **实时可视化**：动态展示节点树和执行流程

---

## 系统架构

```
┌─────────────────────────────────────────────────────────────┐
│                         用户界面 (Web UI)                     │
│  ┌────────────┐  ┌──────────────┐  ┌──────────────────┐     │
│  │ 聊天界面   │  │ 节点树可视化 │  │ 审批面板         │     │
│  └────────────┘  └──────────────┘  └──────────────────┘     │
└─────────────────────────────────────────────────────────────┘
                            ↕ SSE/WebSocket
┌─────────────────────────────────────────────────────────────┐
│                      Mediator Agent (中间人)                  │
│  • 接收用户输入                                               │
│  • 解释节点状态                                               │
│  • 请求人类审批                                               │
│  • 流式输出思考过程                                           │
└─────────────────────────────────────────────────────────────┘
           ↓                    ↓                    ↓
┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐
│  Planner Agent   │  │   Node Tree      │  │ Executor Agent   │
│                  │  │                  │  │                  │
│  • 生成代码规划  │  │  • 管理节点状态  │  │  • 执行工具调用  │
│  • 展开STUB节点  │  │  • 追踪依赖关系  │  │  • Pydantic校验  │
│  • 优化代码结构  │  │  • 持久化树结构  │  │  • 外部任务管理  │
└──────────────────┘  └──────────────────┘  └──────────────────┘
                                ↓
                      ┌──────────────────┐
                      │  Visualizer      │
                      │  • 树形图渲染    │
                      │  • 实时更新      │
                      │  • 状态高亮      │
                      └──────────────────┘
```

---

## 核心组件详解

### 1. NodeTree（节点树管理器）

**职责**：管理代码节点树的状态和生命周期

```python
class NodeTree:
    """增强版代码树，支持状态追踪和可视化"""
    
    @dataclass
    class Node:
        id: str                           # 唯一标识
        code: str                         # 代码内容
        parent: Node | None               # 父节点
        children: list[Node]              # 子节点
        status: NodeStatus                # 状态
        depth: int                        # 深度
        
        # 新增字段
        intent: str                       # 节点意图（给人看）
        tool_calls: list[ToolCall]        # 工具调用记录
        approval_required: bool           # 是否需要审批
        approved: bool                    # 是否已审批
        execution_result: Any             # 执行结果
        created_at: datetime              # 创建时间
        updated_at: datetime              # 更新时间
        
    def add_node(self, parent: Node, code: str, intent: str) -> Node:
        """添加节点并通知可视化器"""
        
    def update_status(self, node: Node, status: NodeStatus):
        """更新节点状态并触发事件"""
        
    def find_next_pending(self) -> Node | None:
        """找到下一个待执行节点（DFS）"""
        
    def export_snapshot(self) -> dict:
        """导出当前树状态用于可视化"""
```

**节点状态机**：

```
PENDING → PLANNING → PLANNED → WAITING_APPROVAL → APPROVED → EXECUTING → COMPLETED
                                       ↓
                                   REJECTED
```

---

### 2. MediatorAgent（中间人 Agent）

**职责**：与用户对话，解释节点状态，协调其他 Agent

```python
class MediatorAgent:
    """中间人 Agent，负责人机交互"""
    
    def __init__(self):
        self.planner = PlannerAgent()
        self.executor = ExecutorAgent()
        self.tree = NodeTree()
        self.conversation_history = []
    
    async def chat_stream(self, user_message: str):
        """
        流式对话接口
        
        Yields:
            - thinking: 思考过程
            - explanation: 对节点的解释
            - approval_request: 审批请求
            - node_update: 节点状态更新
        """
        # 1. 理解用户意图
        intent = await self._understand_intent(user_message)
        yield {"type": "thinking", "content": f"理解到你想要: {intent}"}
        
        # 2. 请求 Planner 生成规划
        if self.tree.is_empty():
            plan = await self.planner.create_plan(intent)
            yield {"type": "explanation", "content": f"我将这样规划任务:\n{plan.summary}"}
            
            # 3. 创建根节点
            root = self.tree.create_root(plan.code, intent)
            yield {"type": "node_update", "node": root.to_dict()}
        
        # 4. 执行循环
        while not self.tree.is_complete():
            current = self.tree.find_next_pending()
            
            # 4.1 展开 STUB 节点
            if current.status == NodeStatus.STUB:
                yield {"type": "thinking", "content": f"正在展开节点: {current.intent}"}
                expansion = await self.planner.expand(current)
                
                # 向用户解释展开
                yield {
                    "type": "explanation", 
                    "content": f"将 '{current.intent}' 拆解为:\n" + 
                               "\n".join(f"- {child.intent}" for child in expansion)
                }
                
                # 添加子节点
                for child_code, child_intent in expansion:
                    child = self.tree.add_node(current, child_code, child_intent)
                    yield {"type": "node_update", "node": child.to_dict()}
            
            # 4.2 执行节点
            elif current.status == NodeStatus.PENDING:
                yield {"type": "thinking", "content": f"执行: {current.intent}"}
                
                # 检测工具调用
                tool_calls = self._extract_tool_calls(current.code)
                
                if tool_calls:
                    for tool_call in tool_calls:
                        # 请求人类审批
                        if tool_call.requires_approval:
                            current.approval_required = True
                            yield {
                                "type": "approval_request",
                                "node_id": current.id,
                                "tool_call": tool_call.to_dict(),
                                "explanation": f"需要你确认: {tool_call.description}"
                            }
                            
                            # 等待审批
                            approved = await self._wait_for_approval(current.id, tool_call.id)
                            
                            if not approved:
                                current.status = NodeStatus.REJECTED
                                yield {"type": "explanation", "content": "已取消该操作"}
                                continue
                        
                        # 执行工具
                        result = await self.executor.execute_tool(tool_call)
                        current.execution_result = result
                        
                        yield {
                            "type": "explanation",
                            "content": f"✓ {tool_call.description} 完成"
                        }
                
                # 更新状态
                current.status = NodeStatus.COMPLETED
                yield {"type": "node_update", "node": current.to_dict()}
    
    async def _understand_intent(self, message: str) -> str:
        """使用 LLM 理解用户意图"""
        # 调用 Pydantic AI Agent
        pass
    
    async def _wait_for_approval(self, node_id: str, tool_call_id: str) -> bool:
        """等待人类审批（通过事件循环）"""
        # 创建 Future，等待前端响应
        pass
```

---

### 3. PlannerAgent（规划 Agent）

**职责**：基于 ReCode 的递归代码生成能力

```python
class PlannerAgent:
    """规划 Agent，负责生成和展开代码"""
    
    def __init__(self, llm: AsyncLLM):
        self.llm = llm
    
    async def create_plan(self, intent: str) -> Plan:
        """
        根据用户意图创建初始规划
        
        Returns:
            Plan {
                code: str,           # 根节点代码
                summary: str,        # 规划摘要（给人看）
                estimated_steps: int # 预估步数
            }
        """
        prompt = f"""
作为 AI 规划师，为以下任务生成 Python 代码框架：

任务: {intent}

要求:
1. 使用函数调用表示子任务（如果不确定如何实现，用占位符）
2. 添加注释说明每个步骤的意图
3. 生成一个简洁的摘要

示例:
```python
def solve(task, obs):
    \"\"\"生成咖啡广告片\"\"\"
    # 第一步：规划分镜
    storyboard = create_storyboard()
    
    # 第二步：生成关键帧
    frames = generate_key_frames(storyboard)
    
    # 第三步：合成视频
    final_video = compose_video(frames)
    
    return final_video
```

请生成代码:
"""
        response = await self.llm(prompt)
        code = parse_code_block(response)
        summary = self._generate_summary(code)
        
        return Plan(code=code, summary=summary, estimated_steps=5)
    
    async def expand(self, node: Node) -> list[tuple[str, str]]:
        """
        展开 STUB 节点
        
        Returns:
            [(child_code, child_intent), ...]
        """
        prompt = f"""
展开以下函数调用为具体实现：

函数: {node.code}
上下文: {self._get_context(node)}

要求:
1. 将抽象函数拆解为具体步骤
2. 每个步骤附带意图说明

请生成代码:
"""
        response = await self.llm(prompt)
        blocks = split_blocks(response)
        
        expansions = []
        for block in blocks:
            intent = self._extract_intent(block)
            expansions.append((block, intent))
        
        return expansions
    
    def _generate_summary(self, code: str) -> str:
        """生成代码摘要（给人看）"""
        # 提取函数调用和注释
        pass
    
    def _extract_intent(self, code: str) -> str:
        """从代码中提取意图"""
        # 解析注释或函数名
        pass
```

---

### 4. ExecutorAgent（执行 Agent）

**职责**：基于 Pydantic AI 的类型安全工具调用

```python
class ExecutorAgent:
    """执行 Agent，负责调用外部工具"""
    
    def __init__(self):
        # 集成你的 Pydantic AI Agent
        from gateway.agent.tools import propose_image, propose_video
        
        self.tools = {
            "propose_image": propose_image,
            "propose_video": propose_video,
        }
    
    async def execute_tool(self, tool_call: ToolCall) -> ToolResult:
        """
        执行工具调用（带 Pydantic 校验）
        
        Args:
            tool_call: ToolCall {
                id: str,
                name: str,
                args: dict,
                requires_approval: bool
            }
        
        Returns:
            ToolResult {
                success: bool,
                output: Any,
                task_id: str | None,
                error: str | None
            }
        """
        tool_func = self.tools.get(tool_call.name)
        
        if not tool_func:
            return ToolResult(success=False, error=f"未知工具: {tool_call.name}")
        
        try:
            # Pydantic 自动校验参数
            if tool_call.name == "propose_image":
                from gateway.agent.models import BananaImageTaskInput
                validated_input = BananaImageTaskInput(**tool_call.args)
                
                # 调用工具（会抛出 CallDeferred）
                task_id = await self._execute_deferred_tool(tool_func, validated_input)
                
                return ToolResult(
                    success=True,
                    task_id=task_id,
                    output=f"已创建任务: {task_id}"
                )
            
            # ... 其他工具
            
        except ValidationError as e:
            return ToolResult(success=False, error=f"参数校验失败: {e}")
        except Exception as e:
            return ToolResult(success=False, error=str(e))
    
    async def _execute_deferred_tool(self, tool_func, validated_input):
        """执行延迟工具（外部执行）"""
        from pydantic_ai import RunContext
        from gateway.agent.models import AgentDependencies
        
        # 创建运行上下文
        deps = AgentDependencies(
            project_id="default",
            auto_execute=True,
            is_paid=False,
        )
        
        ctx = RunContext(deps=deps, tool_call_id=generate_id())
        
        try:
            await tool_func(ctx, validated_input)
        except CallDeferred as cd:
            # 工具已提交到外部队列
            return cd.metadata.get("task_id")
```

---

### 5. Visualizer（可视化器）

**职责**：实时渲染节点树

```python
class Visualizer:
    """节点树可视化器"""
    
    def __init__(self, tree: NodeTree):
        self.tree = tree
        self.subscribers = []  # WebSocket 订阅者
    
    def subscribe(self, ws_connection):
        """订阅节点更新"""
        self.subscribers.append(ws_connection)
    
    async def emit_update(self, event: dict):
        """向所有订阅者推送更新"""
        for subscriber in self.subscribers:
            await subscriber.send_json(event)
    
    def render_tree_json(self) -> dict:
        """渲染树为 JSON（给前端）"""
        return {
            "nodes": [self._render_node(node) for node in self.tree.all_nodes()],
            "edges": [self._render_edge(parent, child) 
                     for parent in self.tree.all_nodes() 
                     for child in parent.children],
        }
    
    def _render_node(self, node: Node) -> dict:
        return {
            "id": node.id,
            "label": node.intent,
            "status": node.status.value,
            "depth": node.depth,
            "code": node.code,
            "approval_required": node.approval_required,
            "tool_calls": [tc.to_dict() for tc in node.tool_calls],
        }
    
    def _render_edge(self, parent: Node, child: Node) -> dict:
        return {
            "from": parent.id,
            "to": child.id,
        }
```

---

## 数据流示例

### 场景：用户要生成广告片

```
1. 用户输入: "生成一个咖啡广告片"
   ↓
2. MediatorAgent 理解意图
   → 输出: [thinking] "理解到你想要生成广告片"
   ↓
3. PlannerAgent 创建规划
   → 输出: [explanation] "我将这样规划任务: 1.规划分镜 2.生成图片 3.生成视频"
   → 创建根节点: solve()
   → 输出: [node_update] {node: {...}}
   ↓
4. 执行根节点
   → 遇到 STUB: create_storyboard()
   ↓
5. 展开 STUB
   → PlannerAgent 生成展开代码
   → 输出: [explanation] "将'规划分镜'拆解为: - 分析需求 - 生成3个分镜"
   → 创建子节点
   → 输出: [node_update] {node: {...}}
   ↓
6. 执行子节点: generate_image()
   → 检测到工具调用
   → 输出: [approval_request] {tool: "propose_image", args: {...}}
   ↓
7. 等待用户审批
   → 用户点击"批准"
   ↓
8. ExecutorAgent 执行工具
   → 调用 propose_image()
   → 创建任务
   → 输出: [explanation] "✓ 图片生成任务已创建"
   → 输出: [node_update] {node: {status: "COMPLETED"}}
   ↓
9. 继续下一个节点...
```

---

## 技术栈

### 后端
- **FastAPI**: HTTP + SSE + WebSocket
- **Pydantic AI**: 工具管理和类型校验
- **ReCode**: 代码生成逻辑
- **Redis**: 任务队列和 Pub/Sub
- **MongoDB**: 持久化节点树

### 前端
- **React**: UI 框架
- **D3.js / ReactFlow**: 节点树可视化
- **TailwindCSS**: 样式

---

## API 设计

### WebSocket 接口

```typescript
// 连接 WebSocket
ws = new WebSocket("ws://localhost:8000/recode-plus/stream")

// 发送消息
ws.send(JSON.stringify({
  type: "user_message",
  content: "生成一个咖啡广告片"
}))

// 接收事件
ws.onmessage = (event) => {
  const data = JSON.parse(event.data)
  
  switch (data.type) {
    case "thinking":
      // 显示思考过程
      break
    case "explanation":
      // 显示解释
      break
    case "approval_request":
      // 显示审批面板
      break
    case "node_update":
      // 更新节点树
      break
  }
}

// 发送审批响应
ws.send(JSON.stringify({
  type: "approval_response",
  node_id: "node_123",
  tool_call_id: "tool_456",
  approved: true
}))
```

### REST 接口

```
GET  /recode-plus/tree/{session_id}        # 获取当前树状态
POST /recode-plus/approve                  # 批准工具调用
POST /recode-plus/reject                   # 拒绝工具调用
GET  /recode-plus/history/{session_id}     # 获取历史记录
```

---

## 文件结构

```
ReCode+/
├── recode_plus/
│   ├── __init__.py
│   ├── mediator.py               # MediatorAgent
│   ├── planner.py                # PlannerAgent
│   ├── executor.py               # ExecutorAgent
│   ├── node_tree.py              # NodeTree
│   ├── visualizer.py             # Visualizer
│   ├── models.py                 # 数据模型
│   └── events.py                 # 事件系统
├── api/
│   ├── main.py                   # FastAPI 入口
│   ├── websocket.py              # WebSocket 处理
│   └── rest.py                   # REST API
├── web/                          # 前端
│   ├── src/
│   │   ├── components/
│   │   │   ├── ChatPanel.tsx
│   │   │   ├── TreeView.tsx
│   │   │   └── ApprovalPanel.tsx
│   │   └── App.tsx
│   └── package.json
└── examples/
    └── advideo_demo.py           # 广告片生成示例
```

---

## 下一步

1. 实现核心组件（NodeTree、MediatorAgent）
2. 集成 Pydantic AI 工具
3. 实现可视化前端
4. 测试广告片生成场景

