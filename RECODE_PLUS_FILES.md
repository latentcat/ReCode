# ReCode+ 文件结构

```
E:\ShichenPro\ReCode\
│
├── recode_plus/                      # 🎯 ReCode+ 核心框架
│   ├── __init__.py                   # 模块导出
│   ├── models.py                     # 数据模型（Node, ToolCall, Plan）
│   ├── node_tree.py                  # 节点树管理器
│   ├── mediator.py                   # 中间人 Agent（协调器）
│   ├── planner.py                    # 规划 Agent（代码生成）
│   ├── executor.py                   # 执行 Agent（工具调用）
│   ├── visualizer.py                 # 可视化器（控制台和 JSON）
│   │
│   └── api/                          # 🌐 Web API 服务
│       ├── main.py                   # FastAPI 入口（WebSocket + REST）
│       └── index.html                # Web 演示界面
│
├── examples/                         # 📚 示例代码
│   └── advideo_demo.py               # 广告片生成示例
│
├── tests/                            # 🧪 测试文件
│   └── test_recode_plus.py           # 单元测试
│
├── RECODE_PLUS_ARCHITECTURE.md       # 📖 架构设计文档
├── RECODE_PLUS_README.md             # 📄 项目说明
├── RECODE_PLUS_QUICKSTART.md         # 🚀 快速启动指南
└── RECODE_PLUS_FILES.md              # 📁 本文件
```

---

## 📦 核心模块说明

### 1. `models.py` - 数据模型

定义了所有核心数据结构：

| 类名 | 说明 |
|-----|------|
| `NodeStatus` | 节点状态枚举（PENDING, STUB, EXECUTING, COMPLETED...） |
| `Node` | 节点类（代码、状态、子节点、工具调用...） |
| `ToolCall` | 工具调用信息（名称、参数、是否需要审批） |
| `ToolResult` | 工具执行结果（成功、输出、错误） |
| `Plan` | 规划结果（代码、摘要、预估步数） |
| `EventMessage` | 事件消息（类型、内容、时间戳） |

---

### 2. `node_tree.py` - 节点树管理器

管理代码节点树的生命周期：

| 方法 | 说明 |
|-----|------|
| `create_root()` | 创建根节点 |
| `add_node()` | 添加子节点 |
| `update_status()` | 更新节点状态 |
| `find_next_pending()` | 找到下一个待执行节点（DFS） |
| `export_snapshot()` | 导出树状态快照 |
| `on()` / `off()` | 注册/移除事件监听器 |

**事件系统**：
- `node_created` - 节点创建时触发
- `node_status_changed` - 节点状态变更时触发

---

### 3. `mediator.py` - 中间人 Agent

协调用户和系统的交互，是整个框架的核心：

| 方法 | 说明 |
|-----|------|
| `chat_stream()` | 流式对话接口，生成事件流 |
| `approve_tool()` | 批准工具调用 |
| `reject_tool()` | 拒绝工具调用 |
| `get_tree_snapshot()` | 获取当前树状态 |

**内部流程**：
1. 理解用户意图
2. 创建初始规划（如果树为空）
3. 执行循环：遍历节点树
   - STUB 节点 → 展开
   - PENDING 节点 → 执行
4. 管理审批流程
5. 流式输出事件

---

### 4. `planner.py` - 规划 Agent

基于 ReCode 的代码生成能力：

| 方法 | 说明 |
|-----|------|
| `create_plan()` | 根据用户意图创建初始规划 |
| `expand()` | 展开 STUB 节点为具体实现 |

**提示词策略**：
- 使用清晰的函数调用表示子任务
- 添加注释说明意图
- 保持代码简洁

---

### 5. `executor.py` - 执行 Agent

集成 Pydantic AI 工具，负责类型安全的工具调用：

| 方法 | 说明 |
|-----|------|
| `extract_tool_calls()` | 从代码中提取工具调用 |
| `execute_tool()` | 执行工具（带 Pydantic 校验） |

**集成的工具**：
- `propose_image` - 图片生成（你的 Pydantic AI 工具）
- `propose_video` - 视频生成（你的 Pydantic AI 工具）
- `generate_image` - 图片生成（模拟）
- `generate_video` - 视频生成（模拟）
- `ask` - 对话（模拟）

---

### 6. `visualizer.py` - 可视化器

实时渲染节点树：

| 类 | 说明 |
|----|------|
| `Visualizer` | Web 可视化（JSON 输出） |
| `ConsoleVisualizer` | 控制台可视化（树形图） |

**功能**：
- 订阅节点树事件
- 实时推送更新到 WebSocket
- 生成前端可用的 JSON 数据
- 生成 Mermaid 流程图语法

---

### 7. `api/main.py` - Web API 服务

FastAPI 服务，提供 REST API 和 WebSocket：

**REST 接口**：
- `POST /sessions` - 创建会话
- `GET /sessions/{id}/tree` - 获取树状态
- `POST /sessions/{id}/approve` - 批准工具
- `DELETE /sessions/{id}` - 删除会话

**WebSocket 接口**：
- `/ws/{session_id}` - 实时通信

---

## 🔗 模块依赖关系

```
MediatorAgent
    ├── NodeTree (管理节点)
    ├── PlannerAgent (规划代码)
    │   └── AsyncLLM (ReCode)
    └── ExecutorAgent (执行工具)
        └── Pydantic AI Tools (你的工具)

Visualizer
    └── NodeTree (订阅事件)

FastAPI
    ├── MediatorAgent (会话管理)
    └── Visualizer (实时推送)
```

---

## 📝 数据流示例

```
用户输入: "生成广告片"
    ↓
Mediator.chat_stream()
    ↓
Planner.create_plan()
    → 返回 Plan(code="def solve()...", summary="...")
    ↓
NodeTree.create_root()
    → 创建根节点
    → 触发 "node_created" 事件
    ↓
Visualizer 接收事件
    → 推送到 WebSocket
    ↓
前端更新 UI
    ↓
Mediator 执行循环
    ↓
Executor.extract_tool_calls()
    → 检测到 generate_image()
    ↓
Executor.execute_tool()
    → 调用 Pydantic AI 工具
    → 返回 ToolResult(task_id="xxx")
    ↓
NodeTree.update_status(COMPLETED)
    → 触发 "node_status_changed" 事件
    ↓
Visualizer 推送更新
    ↓
前端显示完成状态
```

---

## 🎯 扩展点

### 1. 添加新工具

在 `executor.py` 中注册：

```python
def _init_tools(self):
    self.tools["your_tool"] = your_tool_func
```

### 2. 自定义节点类型

在 `models.py` 中扩展 `Node` 类：

```python
@dataclass
class CustomNode(Node):
    custom_field: str = ""
```

### 3. 添加新事件类型

在 `models.py` 中定义新的事件类型，然后在相应模块中触发。

### 4. 持久化

在 `node_tree.py` 中添加数据库操作：

```python
def save_to_db(self):
    snapshot = self.export_snapshot()
    db.save(snapshot)
```

---

## 🚀 启动顺序

1. **开发阶段**：
   ```bash
   python tests/test_recode_plus.py
   ```

2. **命令行演示**：
   ```bash
   python examples/advideo_demo.py
   ```

3. **Web 服务**：
   ```bash
   cd recode_plus/api
   python main.py
   ```

4. **访问界面**：
   ```
   http://localhost:8000/index.html
   ```

---

## 📊 性能考虑

- **节点树大小**：建议限制最大深度（如 10 层）
- **WebSocket 连接数**：使用连接池管理
- **LLM 调用频率**：添加缓存和限流
- **事件推送频率**：批量发送更新（如每 100ms）

---

## 🔐 安全考虑

- **API Key 保护**：不要硬编码，使用环境变量
- **工具执行权限**：限制可执行的工具
- **输入验证**：使用 Pydantic 校验所有输入
- **会话隔离**：每个会话独立的命名空间

---

**文档更新日期**: 2024-12

