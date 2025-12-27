# ReCode+ 框架

> 融合 ReCode、Pydantic AI 和人机协作的新一代 Agent 框架

## ✨ 特性

- **🔄 递归代码生成**：继承 ReCode 的代码树展开能力
- **✅ 类型安全工具**：集成 Pydantic AI 的工具校验
- **👤 人机协作**：关键节点支持人工审批
- **🗣️ 中间人解释**：每个节点都向用户说明意图
- **📊 实时可视化**：动态展示节点树和执行流程

## 🏗️ 架构

```
用户界面 (Web UI)
    ↕
Mediator Agent (中间人)
    ↓
Planner → NodeTree → Executor
    ↓
Visualizer (可视化)
```

## 🚀 快速开始

### 1. 安装依赖

```bash
cd ReCode
pip install fastapi uvicorn websockets
```

### 2. 启动服务

```bash
cd recode_plus/api
python main.py
```

服务将在 `http://localhost:8000` 启动。

### 3. 打开 Web 界面

在浏览器中打开 `http://localhost:8000/api/index.html`

### 4. 开始对话

在聊天框中输入你的需求，例如：

```
生成一个咖啡广告片，包含3个场景：
1. 清晨的咖啡店
2. 咖啡师制作拿铁
3. 顾客享受咖啡
```

## 📖 使用示例

### 命令行示例

```bash
cd ReCode
python examples/advideo_demo.py
```

### Python 代码示例

```python
from utils.llm import AsyncLLM
from recode_plus.mediator import MediatorAgent

# 创建 Agent
llm = AsyncLLM("default")
mediator = MediatorAgent(llm, project_id="my_project")

# 流式对话
async for event in mediator.chat_stream("生成一个广告片"):
    if event.type == "explanation":
        print(event.content)
    elif event.type == "approval_request":
        # 处理审批请求
        await mediator.approve_tool(event.content["tool_call"]["id"])
```

## 🧪 运行测试

```bash
cd ReCode
python tests/test_recode_plus.py
```

## 📚 核心概念

### NodeTree（节点树）

管理代码节点的树形结构，支持：
- 节点创建和状态更新
- DFS 遍历查找下一个待执行节点
- 事件通知和快照导出

### MediatorAgent（中间人）

协调用户和系统的交互：
- 理解用户意图
- 解释节点状态
- 管理审批流程
- 流式输出事件

### PlannerAgent（规划器）

基于 ReCode 的代码生成能力：
- 创建初始规划
- 展开 STUB 节点
- 生成代码摘要

### ExecutorAgent（执行器）

集成 Pydantic AI 工具：
- 提取工具调用
- 类型安全校验
- 外部任务管理

## 🎨 集成你的工具

### 添加自定义工具

在 `recode_plus/executor.py` 中注册你的工具：

```python
from your_module import your_tool

class ExecutorAgent:
    def _init_tools(self):
        self.tools = {
            "your_tool": your_tool,
            # ... 其他工具
        }
```

### 集成 Pydantic AI 工具

ReCode+ 已经集成了你的图片/视频生成工具：

```python
# 这些工具已自动集成
- propose_image
- propose_video
- execute_image_generation
- execute_video_generation
```

## 📊 可视化

### Web 可视化

访问 `http://localhost:8000/sessions/{session_id}/visualize` 获取 JSON 格式的树数据。

### 控制台可视化

```python
from recode_plus.visualizer import ConsoleVisualizer

viz = ConsoleVisualizer(mediator.tree)
viz.print_tree()
```

输出示例：

```
======================================================
节点树状态
======================================================
└── ✔️ 生成广告片
    ├── ✔️ 规划分镜
    ├── ⚙️ 生成关键帧
    │   ├── ✔️ 场景1
    │   └── ⏳ 场景2
    └── ⏳ 合成视频
======================================================
```

## 🔌 API 文档

### REST API

- `POST /sessions` - 创建会话
- `GET /sessions/{session_id}/tree` - 获取树状态
- `GET /sessions/{session_id}/visualize` - 获取可视化数据
- `POST /sessions/{session_id}/approve` - 批准工具
- `DELETE /sessions/{session_id}` - 删除会话

### WebSocket

连接：`ws://localhost:8000/ws/{session_id}`

发送消息：

```json
{
  "type": "user_message",
  "content": "你的需求"
}
```

接收事件：

```json
{
  "type": "explanation",
  "content": "解释内容",
  "timestamp": "2024-01-01T00:00:00"
}
```

## 🛠️ 配置

### LLM 配置

使用 ReCode 的配置文件 `configs/profiles.yaml`：

```yaml
models:
  default:
    api_key: "your_api_key"
    base_url: "https://api.openai.com/v1"
    model: "gpt-4"
```

### 项目 ID

在创建 MediatorAgent 时指定：

```python
mediator = MediatorAgent(llm, project_id="your_project_id")
```

## 📝 开发路线图

- [x] 核心框架实现
- [x] WebSocket 实时通信
- [x] 人工审批机制
- [x] 控制台可视化
- [ ] React 可视化组件
- [ ] 节点持久化（MongoDB）
- [ ] 任务进度追踪（Redis）
- [ ] 多用户会话管理
- [ ] 审批历史记录
- [ ] 代码执行沙箱

## 🤝 贡献

欢迎提交 Issue 和 Pull Request！

## 📄 许可

MIT License

## 🙏 致谢

- [ReCode](https://github.com/...) - 递归代码生成框架
- [Pydantic AI](https://ai.pydantic.dev/) - 类型安全的 AI 框架
- Your Unified API Gateway - 图片/视频生成工具

