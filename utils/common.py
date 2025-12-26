"""
通用工具函数模块

这个文件包含一些常用的辅助函数，被项目的多个模块共享使用。

主要功能：
- 文件读写（JSON、YAML）
- 文本解析（代码块、XML 标签）
"""

import json
import yaml
from pathlib import Path
from typing import Any, List, Dict, Optional
from pydantic_core import to_jsonable_python
import re


def read_json_file(json_file: str, encoding="utf-8") -> List[Any]:
    """
    读取 JSON 文件
    
    参数:
        json_file: JSON 文件路径
        encoding: 文件编码，默认 utf-8
    
    返回:
        解析后的 Python 对象（通常是 list 或 dict）
    
    异常:
        FileNotFoundError: 文件不存在
        ValueError: JSON 解析失败
    
    示例:
        data = read_json_file("configs/prices.json")
        print(data["gpt-4o"]["input"])  # 获取 GPT-4o 的输入价格
    """
    # 检查文件是否存在
    if not Path(json_file).exists():
        raise FileNotFoundError(f"json_file: {json_file} not exist, return []")

    # 读取并解析 JSON
    with open(json_file, "r", encoding=encoding) as fin:
        try:
            data = json.load(fin)
        except Exception:
            raise ValueError(f"read json file: {json_file} failed")
    return data


def write_json_file(json_file: str, data: list, encoding: str = None, indent: int = 4):
    """
    写入 JSON 文件
    
    参数:
        json_file: 目标文件路径
        data: 要写入的数据
        encoding: 文件编码（默认系统编码）
        indent: 缩进空格数，默认 4
    
    特性:
        - 自动创建不存在的父目录
        - 支持中文（ensure_ascii=False）
        - 使用 pydantic 的 to_jsonable_python 处理复杂对象
    
    示例:
        results = [{"task": "put", "success": True}]
        write_json_file("logs/results.json", results)
    """
    # 确保目标目录存在
    folder_path = Path(json_file).parent
    if not folder_path.exists():
        folder_path.mkdir(parents=True, exist_ok=True)

    # 写入 JSON，使用 pydantic 辅助序列化复杂对象
    with open(json_file, "w", encoding=encoding) as fout:
        json.dump(data, fout, ensure_ascii=False, indent=indent, default=to_jsonable_python)


def read_yaml_file(yaml_file: str, encoding='utf-8') -> Dict[str, Any]:
    """
    读取 YAML 文件
    
    参数:
        yaml_file: YAML 文件路径
        encoding: 文件编码，默认 utf-8
    
    返回:
        解析后的字典
    
    异常:
        FileNotFoundError: 文件不存在
        ValueError: YAML 解析失败
    
    示例:
        config = read_yaml_file("configs/profiles.yaml")
        api_key = config["models"]["default"]["api_key"]
    """
    if not Path(yaml_file).exists():
        raise FileNotFoundError(f"yaml_file: {yaml_file} not exist, return empty dict")
    
    with open(yaml_file, "r", encoding=encoding) as f:
        try:
            data = yaml.safe_load(f)
        except Exception:
            raise ValueError(f"read yaml file: {yaml_file} failed")
    return data

    
def parse_code_block(text: str, lang: str = "python") -> Optional[str]:
    """
    从 Markdown 格式的文本中提取代码块
    
    用于解析 LLM 返回的代码，LLM 通常会用 ```python``` 包裹代码。
    
    参数:
        text: 包含代码块的文本
        lang: 代码语言标记，默认 "python"
    
    返回:
        提取的代码字符串，如果没找到返回 None
    
    示例:
        response = '''
        这是一些解释文字。
        
        ```python
        for i in range(10):
            print(i)
        ```
        '''
        code = parse_code_block(response)
        # 返回: "for i in range(10):\n    print(i)"
    """
    # 正则匹配 ```lang ... ``` 格式
    pattern = rf"```{lang}\s*\n(.*?)\n```"
    match = re.search(pattern, text, re.DOTALL)
    if match:
        return match.group(1).strip()
    return None


def parse_xml_tag(response: str, xml_tag: str) -> str:
    """
    从文本中提取指定 XML 标签的内容
    
    ReCode 使用 XML 标签来结构化 LLM 的输出，例如：
    - <think>思考过程</think>
    - <execute>要执行的代码</execute>
    
    参数:
        response: 包含 XML 标签的文本
        xml_tag: 要提取的标签名（不包含尖括号）
    
    返回:
        标签内的内容，如果没找到返回空字符串
    
    示例:
        response = '''
        <think>
        我需要先找到苹果，然后放到桌子上。
        </think>
        
        <execute>
        apple_id = find_and_take("apple")
        put_on(apple_id, "table")
        </execute>
        '''
        
        thought = parse_xml_tag(response, "think")
        # 返回: "我需要先找到苹果，然后放到桌子上。"
        
        code = parse_xml_tag(response, "execute")
        # 返回: "apple_id = find_and_take(\"apple\")\nput_on(apple_id, \"table\")"
    """
    # 正则匹配 <tag>...</tag> 格式
    pattern = rf"<{xml_tag}>(.*?)</{xml_tag}>"
    match = re.search(pattern, response, re.DOTALL)
    return match.group(1).strip() if match else ""
