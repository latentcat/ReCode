# ReCode+ 快速启动指南

## 🚀 10 分钟上手 ReCode+

### 步骤 1：准备环境

```bash
cd E:\ShichenPro\ReCode

# 安装额外依赖
pip install fastapi uvicorn websockets
```

### 步骤 2：配置 LLM

确保 `configs/profiles.yaml` 中有配置：

```yaml
models:
  default:
    api_key: "your_openai_api_key"
    base_url: "https://api.openai.com/v1"
    model: "gpt-4o-mini"
    temperature: 0.0
```

### 步骤 3：运行命令行示例

```bash
# 简单测试
python tests/test_recode_plus.py

# 完整示例（生成广告片）
python examples/advideo_demo.py
```

### 步骤 4：启动 Web 服务

```bash
cd recode_plus/api
python main.py
```

看到以下输出表示成功：

```
🚀 ReCode+ 服务启动
INFO:     Uvicorn running on http://0.0.0.0:8000
```

### 步骤 5：打开 Web 界面

在浏览器访问：`http://localhost:8000/index.html`

或使用 API 文档：`http://localhost:8000/docs`

---

## 💡 使用示例

### 示例 1：生成广告片（命令行）

```python
import asyncio
from utils.llm import AsyncLLM
from recode_plus.mediator import MediatorAgent
from recode_plus.visualizer import ConsoleVisualizer

async def main():
    # 创建 Agent
    llm = AsyncLLM("default")
    mediator = MediatorAgent(llm, project_id="demo")
    
    # 添加可视化
    viz = ConsoleVisualizer(mediator.tree)
    
    # 发送请求
    async for event in mediator.chat_stream(
        "生成一个30秒咖啡广告片，包含3个场景"
    ):
        if event.type == "explanation":
            print(f"💡 {event.content}")
        elif event.type == "approval_request":
            # 自动批准
            tool_call_id = event.content["tool_call"]["id"]
            await mediator.approve_tool(tool_call_id)
    
    # 打印树
    viz.print_tree()

asyncio.run(main())
```

### 示例 2：Web 客户端（JavaScript）

```javascript
// 创建会话
const response = await fetch('http://localhost:8000/sessions', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
        session_id: 'my_session',
        project_id: 'my_project'
    })
});

// 连接 WebSocket
const ws = new WebSocket('ws://localhost:8000/ws/my_session');

// 监听消息
ws.onmessage = (event) => {
    const data = JSON.parse(event.data);
    console.log('收到事件:', data.type, data.content);
};

// 发送用户消息
ws.send(JSON.stringify({
    type: 'user_message',
    content: '生成一个广告片'
}));

// 批准工具调用
ws.send(JSON.stringify({
    type: 'approval_response',
    tool_call_id: 'tool_xxx',
    approved: true
}));
```

---

## 🎯 核心工作流

```
1. 用户输入需求
   ↓
2. Planner 创建规划（根节点）
   ↓
3. 遍历节点树
   ├─ STUB 节点 → Planner 展开
   └─ PENDING 节点 → Executor 执行
   ↓
4. 检测工具调用
   ├─ 需要审批 → 等待用户确认
   └─ 不需要 → 直接执行
   ↓
5. 更新节点状态 → 通知可视化器
   ↓
6. 继续下一个节点...
```

---

## 📊 事件类型

| 事件类型 | 说明 | 示例 |
|---------|------|------|
| `thinking` | Agent 的思考过程 | "正在理解你的需求..." |
| `explanation` | 对操作的解释 | "我将这样规划任务..." |
| `node_update` | 节点状态更新 | `{action: "created", node: {...}}` |
| `approval_request` | 请求人工审批 | `{tool_call: {...}, explanation: "..."}` |
| `task_created` | 外部任务创建 | `{task_id: "xxx", description: "..."}` |
| `error` | 错误信息 | "执行失败: ..." |
| `completion` | 任务完成 | "所有任务已完成！" |

---

## 🔧 故障排查

### 问题 1：无法导入 Pydantic AI 工具

**症状**：`ImportError: No module named 'gateway'`

**解决**：检查路径配置

```python
# 在 executor.py 中
agent_path = Path("E:/ShichenPro/mono-playground/python_packages/unified-api")
```

修改为你的实际路径。

### 问题 2：LLM 调用失败

**症状**：`OpenAI API key not found`

**解决**：配置 API Key

```bash
# 方式 1：环境变量
export OPENAI_API_KEY="your_key"

# 方式 2：配置文件
# 编辑 configs/profiles.yaml
```

### 问题 3：WebSocket 连接失败

**症状**：前端显示 "未连接"

**解决**：

1. 确保服务已启动：`python recode_plus/api/main.py`
2. 检查端口是否被占用
3. 查看控制台错误信息

---

## 🎨 自定义配置

### 自定义工具

在 `recode_plus/executor.py` 中添加：

```python
def _init_tools(self):
    self.tools = {
        "my_custom_tool": my_custom_tool_func,
    }

def _is_tool(self, func_name: str) -> bool:
    known_tools = {
        "my_custom_tool",  # 添加你的工具
    }
    return func_name in self.tools or func_name in known_tools
```

### 自定义审批逻辑

在 `recode_plus/mediator.py` 中修改：

```python
def _requires_approval(self, tool_call: ToolCall) -> bool:
    # 自定义规则
    if tool_call.name == "expensive_operation":
        return True
    if tool_call.args.get("cost", 0) > 100:
        return True
    return tool_call.requires_approval
```

---

## 📖 下一步

- 阅读完整架构文档：`RECODE_PLUS_ARCHITECTURE.md`
- 浏览 API 文档：`http://localhost:8000/docs`
- 查看更多示例：`examples/`
- 运行完整测试：`tests/`

---

## 💬 获取帮助

- 查看日志：服务运行时的控制台输出
- 使用调试模式：在代码中添加 `print()` 语句
- 查看节点树：调用 `mediator.get_tree_snapshot()`

---

**祝你使用愉快！🎉**

