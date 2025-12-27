"""规划 Agent - 负责生成和展开代码"""

from __future__ import annotations
import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .models import Node, Plan

from .models import Node as NodeModel, Plan as PlanModel


class PlannerAgent:
    """规划 Agent，基于 ReCode 的递归代码生成能力"""
    
    def __init__(self, llm):
        """
        Args:
            llm: AsyncLLM 实例（来自 ReCode）
        """
        self.llm = llm
    
    async def create_plan(self, intent: str, context: dict | None = None) -> PlanModel:
        """
        根据用户意图创建初始规划
        
        Args:
            intent: 用户意图描述
            context: 上下文信息（可选）
        
        Returns:
            Plan 对象
        """
        prompt = self._build_plan_prompt(intent, context)
        response, _ = await self.llm(prompt)
        
        # 解析响应
        code = self._parse_code_block(response)
        summary = self._generate_summary(code)
        estimated_steps = self._estimate_steps(code)
        
        return PlanModel(
            code=code,
            summary=summary,
            estimated_steps=estimated_steps,
        )
    
    async def expand(self, node: Node, context: dict | None = None) -> list[tuple[str, str]]:
        """
        展开 STUB 节点
        
        Args:
            node: 待展开的节点
            context: 上下文信息
        
        Returns:
            [(child_code, child_intent), ...]
        """
        prompt = self._build_expand_prompt(node, context)
        response, _ = await self.llm(prompt)
        
        # 解析响应
        blocks = self._split_blocks(response)
        
        expansions = []
        for block in blocks:
            intent = self._extract_intent(block)
            expansions.append((block, intent))
        
        return expansions
    
    def _build_plan_prompt(self, intent: str, context: dict | None) -> str:
        """构建规划提示词"""
        context_str = ""
        if context:
            context_str = f"\n上下文信息:\n{self._format_context(context)}\n"
        
        return f"""
你是一个 AI 规划师。请为以下任务生成 Python 代码框架。

任务: {intent}
{context_str}
要求:
1. 使用清晰的函数调用表示子任务
2. 对于不确定如何实现的部分，使用占位符函数（之后会展开）
3. 添加注释说明每个步骤的意图
4. 保持代码简洁、逻辑清晰

示例:
```python
def solve(task, obs):
    \"\"\"生成咖啡广告片\"\"\"
    # 第一步：与 AI 导演讨论创意
    creative_direction = ask("请为咖啡广告提供创意方向")
    
    # 第二步：生成关键分镜
    scene1 = generate_key_frame("清晨的咖啡店，阳光洒进")
    scene2 = generate_key_frame("咖啡特写，蒸汽升起")
    scene3 = generate_key_frame("顾客满意的微笑")
    
    # 第三步：合成视频
    final_video = compose_scenes([scene1, scene2, scene3])
    
    return final_video
```

请生成代码（只输出代码，不要其他解释）:
""".strip()
    
    def _build_expand_prompt(self, node: Node, context: dict | None) -> str:
        """构建展开提示词"""
        ancestors_code = self._get_ancestors_code(node)
        context_str = ""
        if context:
            context_str = f"\n\n当前变量:\n{self._format_context(context)}"
        
        return f"""
你是一个 AI 规划师。请展开以下占位函数为具体实现。

父节点代码:
{ancestors_code}

待展开的函数: {node.code}
意图: {node.intent}
{context_str}

要求:
1. 将抽象函数拆解为3-5个具体步骤
2. 每个步骤附带清晰的注释说明意图
3. 如果某个步骤仍然复杂，可以继续使用占位符函数
4. 使用可用的工具函数（如 generate_image、generate_video、ask）

可用工具函数:
- ask(question: str) -> str: 与 AI 导演对话
- generate_image(prompt: str, size: str, ratio: str, images: list) -> str: 生成图片
- generate_video(prompt: str, ratio: str, images: list) -> str: 生成视频

请生成代码（只输出代码块，不要其他解释）:
""".strip()
    
    def _parse_code_block(self, response: str) -> str:
        """从响应中解析代码块"""
        # 尝试提取 ```python ... ``` 代码块
        pattern = r'```(?:python)?\s*\n(.*?)\n```'
        matches = re.findall(pattern, response, re.DOTALL)
        
        if matches:
            return matches[0].strip()
        
        # 如果没有代码块标记，返回整个响应
        return response.strip()
    
    def _split_blocks(self, code: str) -> list[str]:
        """将代码拆分为语句块"""
        # 简单实现：按空行分割
        blocks = []
        current_block = []
        
        for line in code.split('\n'):
            stripped = line.strip()
            
            # 跳过空行和注释
            if not stripped or stripped.startswith('#'):
                if current_block:
                    blocks.append('\n'.join(current_block))
                    current_block = []
                continue
            
            current_block.append(line)
        
        if current_block:
            blocks.append('\n'.join(current_block))
        
        return blocks
    
    def _extract_intent(self, code: str) -> str:
        """从代码中提取意图"""
        # 1. 尝试从注释中提取
        comment_match = re.search(r'#\s*(.+)', code)
        if comment_match:
            return comment_match.group(1).strip()
        
        # 2. 尝试从函数调用中提取
        func_match = re.search(r'(\w+)\s*\(', code)
        if func_match:
            func_name = func_match.group(1)
            # 转换为人类可读的描述
            return self._func_name_to_intent(func_name)
        
        # 3. 使用代码本身
        return code[:50] + "..." if len(code) > 50 else code
    
    def _func_name_to_intent(self, func_name: str) -> str:
        """将函数名转换为意图描述"""
        # 将 snake_case 转换为空格分隔
        words = func_name.replace('_', ' ')
        return words.capitalize()
    
    def _generate_summary(self, code: str) -> str:
        """生成代码摘要"""
        lines = code.split('\n')
        summary_lines = []
        
        for line in lines:
            stripped = line.strip()
            # 提取注释
            if stripped.startswith('#'):
                summary_lines.append(stripped[1:].strip())
        
        if summary_lines:
            return '\n'.join(summary_lines)
        
        # 如果没有注释，返回函数名列表
        func_names = re.findall(r'(\w+)\s*\(', code)
        if func_names:
            return "主要步骤: " + ", ".join(set(func_names))
        
        return "规划已生成"
    
    def _estimate_steps(self, code: str) -> int:
        """预估步数"""
        # 简单统计函数调用数量
        func_calls = re.findall(r'(\w+)\s*\(', code)
        return len(func_calls)
    
    def _get_ancestors_code(self, node: Node) -> str:
        """获取祖先节点的代码"""
        ancestors = []
        current = node.parent
        
        while current:
            ancestors.append(f"# {current.intent}\n{current.code}")
            current = current.parent
        
        ancestors.reverse()
        return '\n\n'.join(ancestors) if ancestors else "# 根节点"
    
    def _format_context(self, context: dict) -> str:
        """格式化上下文为字符串"""
        lines = []
        for key, value in context.items():
            value_str = str(value)
            if len(value_str) > 100:
                value_str = value_str[:100] + "..."
            lines.append(f"  {key} = {value_str}")
        return '\n'.join(lines)

