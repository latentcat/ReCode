"""
ReCode+ 示例：生成咖啡广告片

演示如何使用 ReCode+ 框架进行递归规划、人类审批和实时可视化
"""

import asyncio
import sys
from pathlib import Path

# 添加路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.llm import AsyncLLM
from recode_plus.mediator import MediatorAgent
from recode_plus.visualizer import ConsoleVisualizer


async def main():
    """主函数"""
    print("=" * 60)
    print("🎬 ReCode+ 示例：生成咖啡广告片")
    print("=" * 60)
    print()
    
    # 1. 创建 LLM（使用 ReCode 的配置）
    print("📝 初始化 LLM...")
    llm = AsyncLLM("default")
    
    # 2. 创建 MediatorAgent
    print("🤖 创建 MediatorAgent...")
    mediator = MediatorAgent(llm, project_id="demo_project")
    
    # 3. 创建控制台可视化器
    console_viz = ConsoleVisualizer(mediator.tree)
    
    # 4. 用户消息
    user_message = """
生成一个 30 秒的咖啡广告片，展现以下场景：
1. 清晨的咖啡店，阳光洒进
2. 咖啡师制作拿铁艺术
3. 顾客享受咖啡的温馨时刻

风格要温暖、高级、电影感。
""".strip()
    
    print(f"💬 用户输入:\n{user_message}\n")
    print("=" * 60)
    print()
    
    # 5. 流式处理
    async for event in mediator.chat_stream(user_message):
        event_type = event.type
        content = event.content
        
        if event_type == "thinking":
            print(f"🤔 [思考] {content}")
        
        elif event_type == "explanation":
            print(f"💡 [解释] {content}")
        
        elif event_type == "node_update":
            action = content.get("action", "update")
            node = content.get("node", {})
            intent = node.get("intent", "N/A")
            status = node.get("status", "N/A")
            
            if action == "created":
                print(f"➕ [节点创建] {intent} (状态: {status})")
            else:
                print(f"🔄 [节点更新] {intent} (状态: {status})")
        
        elif event_type == "approval_request":
            tool_call = content.get("tool_call", {})
            explanation = content.get("explanation", "")
            
            print(f"⏸️  [审批请求] {explanation}")
            print(f"   工具: {tool_call.get('name')}")
            print(f"   参数: {tool_call.get('args')}")
            print(f"   描述: {tool_call.get('description')}")
            
            # 自动批准（演示）
            print(f"   ✅ 自动批准")
            await mediator.approve_tool(tool_call.get("id"))
        
        elif event_type == "task_created":
            task_id = content.get("task_id")
            description = content.get("description")
            print(f"📦 [任务创建] {description} (ID: {task_id})")
        
        elif event_type == "error":
            print(f"❌ [错误] {content}")
        
        elif event_type == "completion":
            print(f"🎉 [完成] {content}")
        
        print()
        
        # 等待一下，便于观察
        await asyncio.sleep(0.5)
    
    # 6. 打印最终树状态
    print("=" * 60)
    print("📊 最终节点树状态")
    print("=" * 60)
    console_viz.print_tree()
    
    # 7. 导出快照
    snapshot = mediator.get_tree_snapshot()
    print(f"节点总数: {len(snapshot['nodes'])}")
    print(f"根节点 ID: {snapshot['root_id']}")
    print()
    
    print("=" * 60)
    print("✅ 示例完成！")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())

