"""
LLM 调用封装模块

这个模块封装了与大语言模型（如 GPT-4）的交互。

主要类：
- LLMConfig: LLM 配置（API Key、模型名称、参数等）
- CostCalculator: 费用计算器
- AsyncLLM: 异步 LLM 调用器（主要使用的类）

使用示例：
    llm = AsyncLLM("default")  # 使用默认配置
    response, cost = await llm("你好，介绍一下自己")
    print(f"回复: {response}")
    print(f"费用: ${cost}")
"""

import os
import asyncio
import yaml
import random
from pathlib import Path
from typing import Optional, Dict, Any, Tuple, Union, List
from openai import AsyncOpenAI, APIError, APIConnectionError, APITimeoutError, RateLimitError
from pydantic import BaseModel, Field, model_validator, ConfigDict

from utils.common import read_json_file

# ==================== 默认配置路径 ====================

DEFAULT_LLM_PROFILE_PATH = Path("configs/profiles.yaml")  # LLM 配置文件
DEFAULT_PRICE_PATH = Path("configs/prices.json")          # 价格配置文件


class LLMConfig(BaseModel):
    """
    LLM 配置类
    
    使用 Pydantic 进行配置验证，支持从 YAML 文件加载。
    
    属性说明：
        api_key: API 密钥（可从环境变量 OPENAI_API_KEY 获取）
        base_url: API 基础 URL（用于自定义端点，如 Azure）
        model: 模型名称（如 "gpt-4o-mini"）
        temperature: 温度参数（控制随机性，0-2）
        max_tokens: 最大生成 token 数
        timeout: 请求超时时间（秒）
        max_retries: 最大重试次数
        retry_base_delay: 重试基础延迟（秒）
        retry_jitter: 重试延迟抖动因子
        track_costs: 是否追踪费用
    """
    model_config = ConfigDict(extra="forbid", validate_default=True)
    
    api_key: Optional[str] = Field(
        default=None,
        description="OpenAI API key (defaults to OPENAI_API_KEY environment variable)"
    )
    base_url: Optional[str] = Field(
        default=None,
        description="Custom API base URL for OpenAI-compatible endpoints"
    )
    model: str = Field(
        default="gpt-4o-mini", 
        description="Model name to use"
    )
    temperature: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=2.0,
        description="Sampling temperature (omit by default; excluded for o-series)"
    )
    max_tokens: Optional[int] = Field(
        default=None,
        gt=0,
        description="Maximum number of tokens to generate (omit by default)"
    )
    timeout: int = Field(
        default=60, 
        gt=0, 
        description="API request timeout in seconds"
    )
    max_retries: int = Field(
        default=3, 
        ge=0, 
        description="Maximum retry attempts"
    )
    retry_base_delay: float = Field(
        default=1.0, 
        description="Base retry delay in seconds"
    )
    retry_jitter: float = Field(
        default=0.1, 
        description="Retry delay jitter factor"
    )
    track_costs: bool = Field(
        default=True, 
        description="Enable cost tracking"
    )

    @classmethod
    def from_profile(cls, profile: str = "default", config_path: Path = DEFAULT_LLM_PROFILE_PATH) -> "LLMConfig":
        """
        从配置文件加载指定 profile 的配置
        
        参数:
            profile: 配置名称（如 "default", "gpt-4o"）
            config_path: 配置文件路径
        
        返回:
            LLMConfig 实例
        """
        try:
            with config_path.open("r", encoding="utf-8") as f:
                config = yaml.safe_load(f)
            
            profile_config = config.get("models", {}).get(profile, {})
            
            return cls(**{
                k: v for k, v in profile_config.items()
                if v is not None and k in cls.model_fields
            })
            
        except Exception as e:
            return cls()

    @model_validator(mode="after")
    def resolve_api_key(self) -> "LLMConfig":
        """
        验证后处理：如果没有提供 API Key，从环境变量获取
        """
        if not self.api_key:
            self.api_key = os.environ.get("OPENAI_API_KEY")
        return self


class CostCalculator(BaseModel):
    """
    费用计算器
    
    根据模型和 token 使用量计算 API 调用费用。
    价格数据从 configs/prices.json 加载。
    """
    pricing: Dict[str, Dict[str, float]] = Field(
        default_factory=lambda: read_json_file(DEFAULT_PRICE_PATH),
        description="Pricing data in USD per million tokens"
    )
    
    def compute_cost(
        self,
        model: str,
        prompt_tokens: int,
        completion_tokens: int
    ) -> Tuple[float, Dict[str, Any]]:
        """
        计算 API 调用费用
        
        参数:
            model: 模型名称
            prompt_tokens: 输入 token 数
            completion_tokens: 输出 token 数
        
        返回:
            (total_cost, cost_breakdown) 元组
        """
        # 获取价格（如果模型不存在则使用默认价格）
        rates = self.pricing.get(model, self.pricing["default"])
        
        # 计算费用（价格单位是每百万 token）
        input_cost = (prompt_tokens / 1e6) * rates["input"]
        output_cost = (completion_tokens / 1e6) * rates["output"]
        total_cost = input_cost + output_cost
        
        # 构建费用明细
        cost_breakdown = {
            "model": model,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
            "input_cost": input_cost,
            "output_cost": output_cost,
            "total_cost": total_cost,
            "currency": "USD"
        }
        
        return total_cost, cost_breakdown


class AsyncLLM(BaseModel):
    """
    异步 LLM 调用器
    
    这是主要使用的类，封装了与 OpenAI API 的交互。
    
    特性：
    - 异步调用，适合并发场景
    - 自动重试失败请求
    - 费用追踪
    - 支持多种配置 profile
    
    使用示例：
        # 使用默认配置
        llm = AsyncLLM("default")
        
        # 调用 LLM
        response, cost = await llm("你好")
        
        # 查看累计费用
        print(f"Total spent: ${llm.spent}")
    """
    config: LLMConfig = Field(default_factory=LLMConfig)
    cost_calculator: CostCalculator = Field(default_factory=CostCalculator)
    client: Optional[AsyncOpenAI] = Field(default=None, exclude=True)
    spent: float = Field(default=0.0, description="Total accumulated cost for this instance")
    
    model_config = ConfigDict(arbitrary_types_allowed=True)

    def __init__(self, profile_or_config: Union[str, Dict[str, Any]] = "default", **kwargs):
        """
        初始化 LLM 调用器
        
        参数:
            profile_or_config: 配置 profile 名称（字符串）或配置字典
            **kwargs: 额外的配置参数
        """
        if isinstance(profile_or_config, str):
            # 从 profile 加载配置
            config = self._load_profile_config(profile_or_config)
            config.update({k: v for k, v in kwargs.items() if k in LLMConfig.model_fields})
            super().__init__(config=LLMConfig(**config))
        else:
            # 直接使用字典配置
            config_kwargs = profile_or_config if isinstance(profile_or_config, dict) else {}
            config_kwargs.update({k: v for k, v in kwargs.items() if k in LLMConfig.model_fields})
            super().__init__(config=LLMConfig(**config_kwargs))
            
        # 初始化 OpenAI 客户端
        self._initialize_client()
    
    def _load_profile_config(self, profile: str) -> Dict[str, Any]:
        """
        从配置文件加载 profile
        """
        try:
            config_path = DEFAULT_LLM_PROFILE_PATH
            with open(config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
                
            # 先查找 models 下的配置
            if profile in config.get("models", {}):
                return config["models"][profile]
            # 再查找 llm_pool 下的配置
            elif profile in config.get("llm_pool", {}):
                pool_config = config["llm_pool"][profile]
                return {k: v for k, v in pool_config.items() if k in LLMConfig.model_fields}
            else:
                return {}
                
        except Exception as e:
            return {}
        
    def _initialize_client(self) -> None:
        """
        初始化 OpenAI 客户端
        """
        # 确保有 API Key
        if not self.config.api_key:
            self.config.api_key = os.environ.get("OPENAI_API_KEY")
            if not self.config.api_key:
                raise ValueError("Missing required API key. Set OPENAI_API_KEY environment variable.")
        
        # 构建客户端参数
        client_args = {
            "api_key": self.config.api_key,
            "timeout": self.config.timeout
        }
        
        if self.config.base_url:
            client_args["base_url"] = self.config.base_url
            
        self.client = AsyncOpenAI(**client_args)

    async def __call__(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        **generation_args
    ) -> Tuple[str, float]:
        """
        调用 LLM 生成回复
        
        参数:
            prompt: 用户输入的提示词
            system_prompt: 系统提示词（可选）
            **generation_args: 其他生成参数
        
        返回:
            (response_content, cost) 元组
        """
        # 构建消息列表
        messages = self._build_messages(prompt, system_prompt)
        
        # 准备请求参数
        params = self._prepare_params(messages, generation_args)

        # 调用 API（带重试）
        response = await self._retry_api_call(params)
        
        # 提取回复内容
        content = response.choices[0].message.content
        
        # 计算费用
        cost = 0.0
        if self.config.track_costs and (usage := getattr(response, "usage", None)):
            cost, _ = self.cost_calculator.compute_cost(
                response.model,
                usage.prompt_tokens,
                usage.completion_tokens
            )
        
        # 累加费用
        self.spent += cost
        
        return content, cost

    def _build_messages(self, prompt: str, system_prompt: Optional[str]) -> List[Dict[str, str]]:
        """
        构建消息列表
        """
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        return messages

    def _prepare_params(
        self,
        messages: list[Dict[str, str]],
        generation_args: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        准备 API 请求参数
        
        特殊处理：
        - o 系列模型（如 o1）不支持 temperature 参数
        """
        params: Dict[str, Any] = {
            "model": self.config.model,
            "messages": messages,
        }

        # 检查是否是 o 系列模型
        model_name = (self.config.model or "").lower()
        is_o_series = model_name.startswith("o")

        # 只在非 o 系列模型时设置 temperature
        if (self.config.temperature is not None) and (not is_o_series):
            params["temperature"] = self.config.temperature

        if self.config.max_tokens is not None:
            params["max_tokens"] = self.config.max_tokens

        # 合并额外参数
        safe_generation_args = dict(generation_args) if generation_args else {}
        if is_o_series:
            safe_generation_args.pop("temperature", None)

        params.update(safe_generation_args)
        return params

    async def _retry_api_call(self, params: Dict[str, Any]) -> Any:
        """
        带重试的 API 调用
        
        在遇到可恢复的错误时（如网络问题、限流），
        使用指数退避策略重试。
        """
        for attempt in range(self.config.max_retries + 1):
            try:
                return await self.client.chat.completions.create(**params)
            except (APIError, APIConnectionError, APITimeoutError, RateLimitError) as e:
                # 最后一次尝试失败，抛出异常
                if attempt == self.config.max_retries:
                    raise
                # 计算退避时间
                backoff_time = self._calculate_backoff(
                    attempt,
                    self.config.retry_base_delay,
                    self.config.timeout
                )
                await asyncio.sleep(backoff_time)

    def _calculate_backoff(self, attempt: int, base: float, max_wait: float) -> float:
        """
        计算退避时间
        
        使用指数退避 + 随机抖动，防止请求同时重试导致的"惊群效应"。
        """
        delay = base * (2 ** attempt)  # 指数增长
        jitter = delay * self.config.retry_jitter * random.uniform(-1, 1)  # 随机抖动
        return min(delay + jitter, max_wait)


def create_llm_instance(model_name: str) -> AsyncLLM:
    """
    便捷函数：创建 LLM 实例
    """
    return AsyncLLM(profile_or_config=model_name)


# ==================== 测试代码 ====================

async def main():
    """测试 LLM 调用"""
    try:
        llm = AsyncLLM("default")
        prompt = "Hello, what is the capital of France?"
        response, cost = await llm(prompt)
        print("Response:", response)
        print("Cost:", cost)
    except Exception as e:
        print(f"An error occurred: {e}")


if __name__ == "__main__":
    asyncio.run(main())
