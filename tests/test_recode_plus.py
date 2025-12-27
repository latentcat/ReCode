"""
ReCode+ 简单测试

测试核心组件的基本功能
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from recode_plus.models import Node, NodeStatus, Plan
from recode_plus.node_tree import NodeTree
from recode_plus.planner import PlannerAgent
from recode_plus.executor import ExecutorAgent
from utils.llm import AsyncLLM


async def test_node_tree():
    """测试 NodeTree"""
    print("=" * 60)
    print("测试: NodeTree")
    print("=" * 60)
    
    tree = NodeTree()
    
    # 创建根节点
    root = tree.create_root(
        code="def solve(task, obs): pass",
        intent="生成广告片"
    )
    
    assert tree.root == root
    assert not tree.is_complete()
    
    # 添加子节点
    child1 = tree.add_node(root, "step1()", "步骤1")
    child2 = tree.add_node(root, "step2()", "步骤2")
    
    assert len(root.children) == 2
    assert child1.depth == 1
    
    # 更新状态
    tree.update_status(child1, NodeStatus.COMPLETED)
    assert child1.status == NodeStatus.COMPLETED
    
    # 查找下一个节点
    next_node = tree.find_next_pending()
    assert next_node == child2
    
    # 导出快照
    snapshot = tree.export_snapshot()
    assert len(snapshot["nodes"]) == 3
    
    print("✅ NodeTree 测试通过")
    print()


async def test_planner():
    """测试 PlannerAgent"""
    print("=" * 60)
    print("测试: PlannerAgent")
    print("=" * 60)
    
    llm = AsyncLLM("default")
    planner = PlannerAgent(llm)
    
    # 创建规划
    plan = await planner.create_plan("生成一个咖啡广告片")
    
    print(f"生成的计划:")
    print(f"- 代码:\n{plan.code}")
    print(f"- 摘要: {plan.summary}")
    print(f"- 预估步数: {plan.estimated_steps}")
    
    assert len(plan.code) > 0
    assert len(plan.summary) > 0
    
    print("✅ PlannerAgent 测试通过")
    print()


async def test_executor():
    """测试 ExecutorAgent"""
    print("=" * 60)
    print("测试: ExecutorAgent")
    print("=" * 60)
    
    executor = ExecutorAgent()
    
    # 提取工具调用
    code = 'result = generate_image(prompt="咖啡杯", size="2K")'
    tool_calls = executor.extract_tool_calls(code)
    
    print(f"提取的工具调用: {len(tool_calls)}")
    for tc in tool_calls:
        print(f"- {tc.name}({tc.args})")
    
    assert len(tool_calls) == 1
    assert tool_calls[0].name == "generate_image"
    
    # 执行工具（模拟）
    result = await executor.execute_tool(tool_calls[0])
    
    print(f"执行结果:")
    print(f"- 成功: {result.success}")
    print(f"- 输出: {result.output}")
    
    assert result.success
    
    print("✅ ExecutorAgent 测试通过")
    print()


async def main():
    """运行所有测试"""
    print("\n🧪 ReCode+ 单元测试\n")
    
    await test_node_tree()
    await test_planner()
    await test_executor()
    
    print("=" * 60)
    print("🎉 所有测试通过！")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())

