"""
LLM 客户端抽象层

统一 Anthropic 原生协议和 OpenAI 兼容协议的调用接口，
使 GradingAgent 无需关心底层使用的是 Claude、MiniMax 还是其他模型。

支持的后端：
  - Anthropic 原生 SDK：Claude 系列模型，支持 Prompt Caching、Adaptive Thinking
  - OpenAI 兼容接口：MiniMax (M3)、DeepSeek、Moonshot、通义千问等国内模型

限流降级与多端点轮转：
  - 配置多个 LLM 端点（不同 API key / base_url / provider）
  - API 触发限流（HTTP 429 / 错误码 2062 等）后自动切换到下一个可用端点
  - 被限流的端点进入冷却期，冷却结束后自动恢复
  - 支持优先级排序和 round-robin 负载均衡

设计原则：
  - GradingAgent 统一使用 Anthropic 风格的 Tool 定义（name + description + input_schema）
  - OpenAI 后端自动转换为 OpenAI 风格的 Function Calling 格式
  - 响应统一转换为内部 LLMResponse 数据结构
  - RateLimitAwareClient 对上层完全透明，接口与 BaseLLMClient 一致
"""

import json
import logging
import time as _time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional

from app.config import LLMConfig, LLMEndpointConfig, LLMProvider

logger = logging.getLogger(__name__)


# ─── 统一响应数据结构 ──────────────────────────────────────────────


@dataclass
class ToolCall:
    """统一的 Tool Call 表示"""

    id: str  # tool_use_id / tool_call_id
    name: str  # 工具名称
    input: dict  # 工具输入参数


@dataclass
class TextBlock:
    """文本内容块"""

    text: str


@dataclass
class ThinkingBlock:
    """思考/推理内容块"""

    text: str


@dataclass
class LLMResponse:
    """
    统一的 LLM 响应结构。

    将 Anthropic 和 OpenAI 两种不同的响应格式统一为一个内部表示，
    GradingAgent 只需要处理这一种格式。
    """

    # 停止原因：end_turn / tool_use / max_tokens / pause_turn
    stop_reason: str = "end_turn"

    # 内容块列表
    text_blocks: list[TextBlock] = field(default_factory=list)
    thinking_blocks: list[ThinkingBlock] = field(default_factory=list)
    tool_calls: list[ToolCall] = field(default_factory=list)

    # 原始响应（用于构建 messages 历史）
    raw_response: Any = None

    # Token 使用统计
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_creation_tokens: int = 0

    # 生成该响应的客户端引用（用于 RateLimitAwareClient 正确路由 build_tool_result_message）
    _source_client: Any = None

    @property
    def has_tool_calls(self) -> bool:
        return len(self.tool_calls) > 0

    @property
    def text(self) -> str:
        """合并所有文本块为单一字符串"""
        return "\n".join(b.text for b in self.text_blocks)


# ─── 抽象基类 ──────────────────────────────────────────────────────


class BaseLLMClient(ABC):
    """
    LLM 客户端抽象基类。

    定义 GradingAgent 所需的统一接口，
    子类负责将调用转换为对应后端的协议格式。
    """

    def __init__(self, config: LLMConfig):
        self.config = config

    @abstractmethod
    def create_message(
        self,
        messages: list[dict],
        system: Any = None,
        tools: list[dict] = None,
        max_tokens: int = 16384,
        model: str = None,
    ) -> LLMResponse:
        """
        发送消息并获取响应（同步）。

        Args:
            messages: 对话消息列表（统一使用 Anthropic 格式:
                      [{"role": "user"/"assistant", "content": ...}]）
            system: System Prompt（Anthropic: list[dict], 会自动适配 OpenAI 格式）
            tools: 工具定义列表（Anthropic 格式，OpenAI 后端自动转换）
            max_tokens: 最大输出 token 数
            model: 模型名称（默认使用配置中的 model）

        Returns:
            LLMResponse: 统一的响应结构
        """
        ...

    @abstractmethod
    def build_tool_result_message(
        self,
        assistant_response: LLMResponse,
        tool_results: list[dict],
    ) -> list[dict]:
        """
        构建包含 Tool Results 的消息对，用于追加到 messages 历史。

        不同后端处理 Tool Results 的方式不同：
        - Anthropic: assistant content blocks + user tool_result blocks
        - OpenAI: assistant message with tool_calls + tool role messages

        Args:
            assistant_response: 包含 tool calls 的 assistant 响应
            tool_results: tool 执行结果列表，格式:
                [{"tool_use_id": "...", "content": "..."}]

        Returns:
            list[dict]: 要追加到 messages 列表的新消息
        """
        ...

    @property
    def provider_name(self) -> str:
        return self.config.provider_display_name


# ─── Anthropic 原生客户端 ──────────────────────────────────────────


class AnthropicLLMClient(BaseLLMClient):
    """
    Anthropic 原生 SDK 客户端。

    支持所有 Anthropic 原生特性：
    - Prompt Caching（cache_control）—— 仅 Anthropic 原生端点
    - Adaptive Thinking / Extended Thinking
    - Tool Use
    - Structured Output

    也支持 Anthropic 兼容端点（如 MiniMax /anthropic）：
    - MiniMax: thinking 使用 {"type": "enabled", "budget_tokens": N} 格式
    - MiniMax-M3: 支持 image / video 输入（content block type=image/video）；
      M2.x 及更早系列仅支持文本与工具调用，不支持图片/视频
    - MiniMax: temperature 范围 (0.0, 1.0]
    """

    def __init__(self, config: LLMConfig):
        super().__init__(config)
        import anthropic

        kwargs = {"api_key": config.api_key}
        if config.effective_base_url:
            kwargs["base_url"] = config.effective_base_url

        self.client = anthropic.Anthropic(**kwargs)

        # 检测是否为第三方 Anthropic 兼容端点（如 MiniMax /anthropic）
        self._is_third_party = bool(
            config.effective_base_url
            and "anthropic.com" not in config.effective_base_url.lower()
        )
        self._is_minimax = bool(
            config.effective_base_url and "minimax" in config.effective_base_url.lower()
        )

        logger.info(
            "Anthropic 客户端初始化完成 (model=%s, base_url=%s, third_party=%s)",
            config.model,
            config.effective_base_url or "默认(api.anthropic.com)",
            self._is_third_party,
        )

    def create_message(
        self,
        messages: list[dict],
        system: Any = None,
        tools: list[dict] = None,
        max_tokens: int = 16384,
        model: str = None,
    ) -> LLMResponse:
        kwargs = {
            "model": model or self.config.model,
            "max_tokens": max_tokens,
            "messages": messages,
        }

        if system:
            # 第三方 Anthropic 兼容端点可能不支持 cache_control，
            # 但大多数（包括 MiniMax）能够忽略它，无需特别处理。
            kwargs["system"] = system

        if tools:
            kwargs["tools"] = tools

        # Thinking（深度推理）
        if self.config.enable_thinking:
            if self._is_third_party:
                # 第三方 Anthropic 兼容端点（如 MiniMax）：
                # 使用 {"type": "enabled", "budget_tokens": N} 格式
                # MiniMax 不支持 Anthropic 原生的 "adaptive" 模式
                #
                # 重要：MiniMax 要求 max_tokens >= budget_tokens，
                # 且 max_tokens 包含 thinking 输出。
                # 因此 budget_tokens 应小于 max_tokens。
                thinking_budget = min(max_tokens // 2, 4096)
                kwargs["thinking"] = {
                    "type": "enabled",
                    "budget_tokens": thinking_budget,
                }
            else:
                # Anthropic 原生端点：使用 Adaptive Thinking
                kwargs["thinking"] = {"type": "adaptive"}

        # Temperature（MiniMax 限制范围为 (0.0, 1.0]，推荐 1.0）
        if self.config.temperature is not None and self._is_third_party:
            temp = self.config.temperature
            # MiniMax 不允许 temperature=0.0，最小值用 0.01 替代
            if temp <= 0.0:
                temp = 0.01
            kwargs["temperature"] = temp

        response = self.client.messages.create(**kwargs)
        return self._convert_response(response)

    def build_tool_result_message(
        self,
        assistant_response: LLMResponse,
        tool_results: list[dict],
    ) -> list[dict]:
        """Anthropic 格式：assistant content blocks + user tool_result blocks"""
        raw = assistant_response.raw_response
        messages = []

        # 1. 追加 assistant 完整响应
        # 将原始 SDK 对象序列化为纯 dict 列表，确保第三方兼容端点能正确处理
        content_blocks = self._serialize_content_blocks(raw.content)
        messages.append(
            {
                "role": "assistant",
                "content": content_blocks,
            }
        )

        # 2. 追加 tool results（作为 user 消息）
        #    tr["content"] 可以是：
        #      - str: 纯文本结果（常规情况）
        #      - list[dict]: 多模态结果块数组（如 [{"type":"text",...},{"type":"image",...}]）
        #        M3 / 原生 Claude 支持在 tool_result 中直接携带 image/video block
        messages.append(
            {
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": tr["tool_use_id"],
                        "content": tr["content"],
                    }
                    for tr in tool_results
                ],
            }
        )

        return messages

    def _serialize_content_blocks(self, content) -> list[dict]:
        """
        将 Anthropic SDK 的 content block 对象列表序列化为纯 dict 列表。

        对于第三方 Anthropic 兼容端点（如 MiniMax /anthropic）：
        - ThinkingBlock 包含 `signature` 等非标准字段，直接传递可能导致解析错误
        - 使用 model_dump() 序列化为标准 dict，并移除 null 值和非标准字段
        """
        blocks = []
        for block in content:
            if hasattr(block, "model_dump"):
                d = block.model_dump(exclude_none=True)
            elif hasattr(block, "__dict__"):
                d = {k: v for k, v in block.__dict__.items() if v is not None}
            else:
                d = block
            blocks.append(d)
        return blocks

    def _convert_response(self, response) -> LLMResponse:
        """将 Anthropic 原始响应转换为统一格式"""
        result = LLMResponse(raw_response=response)

        # 停止原因映射
        result.stop_reason = response.stop_reason or "end_turn"

        # 解析内容块
        for block in response.content:
            if block.type == "text":
                result.text_blocks.append(TextBlock(text=block.text))
            elif block.type == "thinking":
                result.thinking_blocks.append(ThinkingBlock(text=block.thinking))
            elif block.type == "tool_use":
                result.tool_calls.append(
                    ToolCall(
                        id=block.id,
                        name=block.name,
                        input=block.input,
                    )
                )

        # Token 统计
        if hasattr(response, "usage") and response.usage:
            result.input_tokens = getattr(response.usage, "input_tokens", 0)
            result.output_tokens = getattr(response.usage, "output_tokens", 0)
            result.cache_read_tokens = getattr(
                response.usage, "cache_read_input_tokens", 0
            )
            result.cache_creation_tokens = getattr(
                response.usage, "cache_creation_input_tokens", 0
            )

        return result


# ─── OpenAI 兼容客户端 ────────────────────────────────────────────


class OpenAICompatibleLLMClient(BaseLLMClient):
    """
    OpenAI 兼容协议客户端。

    支持所有提供 OpenAI 兼容接口的模型服务商：
    - MiniMax（M3, base_url: https://api.minimaxi.com/v1）
    - DeepSeek（base_url: https://api.deepseek.com）
    - Moonshot（base_url: https://api.moonshot.cn/v1）
    - 通义千问（base_url: https://dashscope.aliyuncs.com/compatible-mode/v1）
    - 等等

    自动处理格式转换：
    - Anthropic 风格的 Tool 定义 → OpenAI Function Calling 格式
    - OpenAI 响应 → 统一的 LLMResponse 结构
    - MiniMax Interleaved Thinking → 统一的 ThinkingBlock
    """

    def __init__(self, config: LLMConfig):
        super().__init__(config)
        from openai import OpenAI

        if not config.effective_base_url:
            raise ValueError(
                "OpenAI 兼容模式必须设置 LLM_BASE_URL。\n"
                "示例：\n"
                "  MiniMax: LLM_BASE_URL=https://api.minimaxi.com/v1\n"
                "  DeepSeek: LLM_BASE_URL=https://api.deepseek.com\n"
            )

        self.client = OpenAI(
            api_key=config.api_key,
            base_url=config.effective_base_url,
        )

        # 检测是否为 MiniMax（需要特殊的 reasoning_split 参数）
        self._is_minimax = "minimax" in (config.effective_base_url or "").lower()

        logger.info(
            "OpenAI 兼容客户端初始化完成 (model=%s, base_url=%s, minimax=%s)",
            config.model,
            config.effective_base_url,
            self._is_minimax,
        )

    def create_message(
        self,
        messages: list[dict],
        system: Any = None,
        tools: list[dict] = None,
        max_tokens: int = 16384,
        model: str = None,
    ) -> LLMResponse:
        # 转换 messages 格式
        openai_messages = self._convert_messages(messages, system)

        kwargs = {
            "model": model or self.config.model,
            "max_tokens": max_tokens,
            "messages": openai_messages,
        }

        # 转换 Tool 定义格式
        if tools:
            kwargs["tools"] = self._convert_tools(tools)

        # MiniMax 特殊处理：启用 reasoning_split 获取结构化思考内容；M3 使用 adaptive thinking
        if self._is_minimax and self.config.enable_thinking:
            extra_body = {"reasoning_split": True}
            if "m3" in (model or self.config.model or "").lower():
                extra_body["thinking"] = {"type": "adaptive"}
            kwargs["extra_body"] = extra_body

        # temperature（部分模型不支持在 tool_use 模式下设置 temperature）
        if self.config.temperature is not None:
            kwargs["temperature"] = self.config.temperature

        response = self.client.chat.completions.create(**kwargs)
        return self._convert_response(response)

    def build_tool_result_message(
        self,
        assistant_response: LLMResponse,
        tool_results: list[dict],
    ) -> list[dict]:
        """OpenAI 格式：assistant message + tool role messages"""
        raw = assistant_response.raw_response
        messages = []

        if raw is None:
            # 如果没有原始响应，手动构建 assistant 消息
            assistant_msg = {
                "role": "assistant",
                "content": assistant_response.text or None,
            }
            if assistant_response.tool_calls:
                assistant_msg["tool_calls"] = [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.name,
                            "arguments": json.dumps(tc.input, ensure_ascii=False),
                        },
                    }
                    for tc in assistant_response.tool_calls
                ]
            messages.append(assistant_msg)
        else:
            # 使用原始响应的 message 对象
            choice = raw.choices[0]
            msg = choice.message

            assistant_msg = {"role": "assistant", "content": msg.content}

            # 保留 reasoning_details（MiniMax Interleaved Thinking 历史连续性）
            if hasattr(msg, "reasoning_details") and msg.reasoning_details:
                assistant_msg["reasoning_details"] = msg.reasoning_details

            if msg.tool_calls:
                assistant_msg["tool_calls"] = [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        },
                    }
                    for tc in msg.tool_calls
                ]
            messages.append(assistant_msg)

        # 追加 tool results（每个 tool 一条 message）
        for tr in tool_results:
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tr["tool_use_id"],
                    "content": tr["content"],
                }
            )

        return messages

    # ─── 格式转换 ──────────────────────────────────────────────

    def _convert_messages(
        self,
        messages: list[dict],
        system: Any = None,
    ) -> list[dict]:
        """
        将 Anthropic 风格的消息转换为 OpenAI 格式。

        核心差异：
        - Anthropic: system 是独立参数（list[dict]）
        - OpenAI: system 是 messages 列表中的第一条消息
        """
        openai_messages = []

        # System Prompt 转换
        if system:
            system_text = self._flatten_system_prompt(system)
            openai_messages.append({"role": "system", "content": system_text})

        # 转换每条消息
        for msg in messages:
            role = msg["role"]
            content = msg.get("content", "")

            if role == "user":
                # 检查是否包含 tool_result blocks（Anthropic 格式）
                if isinstance(content, list):
                    # 检查是否是 Anthropic 的 tool_result 列表
                    if (
                        content
                        and isinstance(content[0], dict)
                        and content[0].get("type") == "tool_result"
                    ):
                        # 这些在 OpenAI 格式中已经通过 build_tool_result_message 处理
                        # 这里不应该出现这种情况，但作为安全处理
                        for block in content:
                            openai_messages.append(
                                {
                                    "role": "tool",
                                    "tool_call_id": block.get("tool_use_id", ""),
                                    "content": block.get("content", ""),
                                }
                            )
                    else:
                        # 多模态内容等
                        openai_messages.append({"role": "user", "content": content})
                else:
                    openai_messages.append({"role": "user", "content": content})

            elif role == "assistant":
                # 直接透传（可能包含 tool_calls 等）
                openai_messages.append(msg)

            elif role == "tool":
                # 直接透传
                openai_messages.append(msg)

        return openai_messages

    def _convert_tools(self, anthropic_tools: list[dict]) -> list[dict]:
        """
        将 Anthropic Tool 定义转换为 OpenAI Function Calling 格式。

        Anthropic 格式:
            {"name": "...", "description": "...", "input_schema": {...}}

        OpenAI 格式:
            {"type": "function", "function": {"name": "...", "description": "...", "parameters": {...}}}
        """
        openai_tools = []
        for tool in anthropic_tools:
            openai_tools.append(
                {
                    "type": "function",
                    "function": {
                        "name": tool["name"],
                        "description": tool.get("description", ""),
                        "parameters": tool.get("input_schema", {}),
                    },
                }
            )
        return openai_tools

    def _flatten_system_prompt(self, system: Any) -> str:
        """
        将 Anthropic 的结构化 System Prompt 拍平为纯文本。

        Anthropic 格式（支持 cache_control）:
            [
                {"type": "text", "text": "...", "cache_control": {...}},
                {"type": "text", "text": "..."},
            ]

        OpenAI 格式: 纯字符串
        """
        if isinstance(system, str):
            return system
        if isinstance(system, list):
            parts = []
            for block in system:
                if isinstance(block, dict) and block.get("type") == "text":
                    parts.append(block["text"])
                elif isinstance(block, str):
                    parts.append(block)
            return "\n".join(parts)
        return str(system)

    def _convert_response(self, response) -> LLMResponse:
        """将 OpenAI 响应转换为统一的 LLMResponse"""
        result = LLMResponse(raw_response=response)

        if not response.choices:
            result.stop_reason = "error"
            return result

        choice = response.choices[0]
        msg = choice.message

        # 停止原因映射
        finish_reason = choice.finish_reason
        if finish_reason == "stop":
            result.stop_reason = "end_turn"
        elif finish_reason == "tool_calls":
            result.stop_reason = "tool_use"
        elif finish_reason == "length":
            result.stop_reason = "max_tokens"
        else:
            result.stop_reason = finish_reason or "end_turn"

        # 提取思考内容（MiniMax reasoning_details）
        if hasattr(msg, "reasoning_details") and msg.reasoning_details:
            for detail in msg.reasoning_details:
                reasoning_text = ""
                if isinstance(detail, dict):
                    reasoning_text = detail.get("text") or detail.get("content") or ""
                else:
                    reasoning_text = getattr(detail, "text", "") or getattr(
                        detail, "content", ""
                    )
                if reasoning_text:
                    result.thinking_blocks.append(ThinkingBlock(text=reasoning_text))

        # 提取文本内容
        text_content = msg.content or ""

        # 处理 <think>/<thinking> 标签（MiniMax reasoning_split=False 或多模态时的格式）
        if ("<think>" in text_content and "</think>" in text_content) or (
            "<thinking>" in text_content and "</thinking>" in text_content
        ):
            import re

            thinking_matches = re.findall(
                r"<think(?:ing)?>(.*?)</think(?:ing)?>",
                text_content,
                re.DOTALL,
            )
            for thinking_text in thinking_matches:
                result.thinking_blocks.append(ThinkingBlock(text=thinking_text.strip()))

            # 移除 thinking 标签后的纯文本
            clean_text = re.sub(
                r"<think(?:ing)?>.*?</think(?:ing)?>",
                "",
                text_content,
                flags=re.DOTALL,
            ).strip()
            if clean_text:
                result.text_blocks.append(TextBlock(text=clean_text))
        elif text_content:
            result.text_blocks.append(TextBlock(text=text_content))

        # 提取 Tool Calls
        if msg.tool_calls:
            result.stop_reason = "tool_use"  # 确保正确设置
            for tc in msg.tool_calls:
                try:
                    args = json.loads(tc.function.arguments)
                except (json.JSONDecodeError, TypeError):
                    args = {}
                result.tool_calls.append(
                    ToolCall(
                        id=tc.id,
                        name=tc.function.name,
                        input=args,
                    )
                )

        # Token 统计
        if response.usage:
            result.input_tokens = response.usage.prompt_tokens or 0
            result.output_tokens = response.usage.completion_tokens or 0

        return result


# ─── 限流检测工具 ────────────────────────────────────────────────


def _is_rate_limit_error(exc: Exception) -> bool:
    """
    判断异常是否属于 API 限流错误。

    支持识别以下限流信号：
    - HTTP 429 Too Many Requests（所有标准 API）
    - HTTP 529 Overloaded（Anthropic 过载）
    - MiniMax 错误码 2062（请求频率过高）
    - OpenAI RateLimitError
    - Anthropic RateLimitError
    - 响应体中包含 rate_limit / too many requests 等关键词
    """
    exc_str = str(exc).lower()

    # 直接类型判断（SDK 专属异常）
    exc_type = type(exc).__name__
    if exc_type in ("RateLimitError",):
        return True

    # HTTP 状态码
    status_code = getattr(exc, "status_code", None) or getattr(exc, "status", None)
    if status_code in (429, 529):
        return True

    # MiniMax 自定义错误码
    if "2062" in exc_str:
        return True

    # 关键词匹配
    rate_keywords = [
        "rate limit",
        "rate_limit",
        "too many requests",
        "request limit",
        "quota exceeded",
        "throttl",
        "overloaded",
        "capacity",
    ]
    return any(kw in exc_str for kw in rate_keywords)


def _extract_retry_after(exc: Exception) -> Optional[float]:
    """
    从异常中提取 Retry-After 秒数。

    API 通常通过 HTTP Header 或响应体告知建议的等待时间。
    """
    import re

    # 尝试从 response headers 获取
    response = getattr(exc, "response", None)
    if response is not None:
        headers = getattr(response, "headers", {})
        retry_after = headers.get("retry-after") or headers.get("Retry-After")
        if retry_after:
            try:
                return float(retry_after)
            except (ValueError, TypeError):
                pass

    # 尝试从异常消息中提取数字（如 "retry after 30 seconds"）
    match = re.search(r"retry.{0,10}?(\d+)\s*s", str(exc).lower())
    if match:
        return float(match.group(1))

    return None


# ─── 端点状态管理 ────────────────────────────────────────────────


@dataclass
class _EndpointState:
    """单个端点的运行时状态"""

    endpoint: LLMEndpointConfig
    client: BaseLLMClient
    is_available: bool = True
    rate_limited_until: float = 0.0  # 限流冷却截止时间戳
    consecutive_failures: int = 0  # 连续失败次数
    total_requests: int = 0  # 总请求数
    total_failures: int = 0  # 总失败数
    last_error: Optional[str] = None  # 最后一次错误信息

    def mark_rate_limited(self, cooldown: float, retry_after: Optional[float] = None):
        """标记为限流状态"""
        wait = retry_after if retry_after and retry_after > 0 else cooldown
        self.rate_limited_until = _time.time() + wait
        self.is_available = False
        self.consecutive_failures += 1
        self.total_failures += 1

    def mark_success(self):
        """标记为成功"""
        self.is_available = True
        self.consecutive_failures = 0
        self.total_requests += 1

    def mark_non_rate_error(self):
        """标记非限流错误（不触发冷却，但记录）"""
        self.consecutive_failures += 1
        self.total_failures += 1

    def check_cooldown(self) -> bool:
        """检查冷却是否结束，如结束则恢复可用"""
        if not self.is_available and _time.time() >= self.rate_limited_until:
            self.is_available = True
            self.rate_limited_until = 0.0
            logger.info("端点 [%s] 冷却结束，恢复可用", self.endpoint.name)
        return self.is_available


# ─── RateLimitAwareClient（限流感知客户端）──────────────────────


class RateLimitAwareClient(BaseLLMClient):
    """
    限流感知的 LLM 客户端包装器。

    在多个 LLM 端点之间实现自动轮转与限流降级：

    工作机制：
    1. 按优先级排序所有端点，优先使用高优先级端点
    2. 请求发出后如果触发限流错误（429 / 2062 / RateLimitError）：
       a. 将当前端点标记为"限流中"，进入冷却期
       b. 自动切换到下一个可用端点重试
       c. 如果所有端点都不可用，等待最短冷却期结束后重试
    3. 非限流错误直接向上抛出（不触发端点切换）
    4. 冷却期结束后端点自动恢复可用

    对上层调用者完全透明 -- 接口与 BaseLLMClient 完全一致。
    """

    def __init__(self, config: LLMConfig):
        super().__init__(config)
        self._endpoint_states: list[_EndpointState] = []
        self._current_index: int = 0
        self._last_success_index: int = 0  # 记录最后一次成功的端点索引

        # 构建主端点（来自 LLM_PROVIDER / LLM_API_KEY / LLM_BASE_URL）
        if config.api_key:
            primary = LLMEndpointConfig(
                name="primary",
                provider=config.provider,
                base_url=config.base_url,
                api_key=config.api_key,
                model=config.model,
                priority=-1,  # 主端点优先级最高
            )
            primary_client = _create_single_client(config, primary)
            self._endpoint_states.append(
                _EndpointState(endpoint=primary, client=primary_client)
            )

        # 构建备用端点
        for ep in config.failover_endpoints:
            ep_config = LLMConfig(
                provider=ep.provider,
                base_url=ep.base_url,
                api_key=ep.api_key,
                model=ep.model,
                enable_thinking=(
                    ep.enable_thinking
                    if ep.enable_thinking is not None
                    else config.enable_thinking
                ),
                temperature=(
                    ep.temperature if ep.temperature is not None else config.temperature
                ),
                max_tokens=config.max_tokens,
            )
            try:
                ep_client = _create_single_client(ep_config, ep)
                self._endpoint_states.append(
                    _EndpointState(endpoint=ep, client=ep_client)
                )
            except Exception as e:
                logger.warning("初始化端点 [%s] 失败，跳过: %s", ep.name, e)

        if not self._endpoint_states:
            raise ValueError(
                "没有可用的 LLM 端点。请检查 LLM_API_KEY 或 LLM_ENDPOINTS 配置。"
            )

        logger.info(
            "RateLimitAwareClient 初始化完成: %d 个端点 [%s]",
            len(self._endpoint_states),
            ", ".join(s.endpoint.name for s in self._endpoint_states),
        )

    # ─── 公开接口（对上层透明） ────────────────────────────────

    def create_message(
        self,
        messages: list[dict],
        system: Any = None,
        tools: list[dict] = None,
        max_tokens: int = 16384,
        model: str = None,
    ) -> LLMResponse:
        """
        发送消息，自动轮转限流降级。

        尝试流程：
        1. 从当前可用端点发送请求
        2. 成功则返回；限流则切换下一个端点重试
        3. 所有端点都限流时，等待最短冷却期后重试
        4. 超过最大重试次数后抛出最后一个异常
        """
        max_retries = self.config.max_failover_retries
        last_exc = None

        for attempt in range(max_retries + len(self._endpoint_states)):
            state = self._pick_available_endpoint()

            if state is None:
                # 所有端点都在冷却中，等待最短冷却期
                wait_time = self._wait_for_earliest_recovery()
                if wait_time <= 0:
                    # 冷却已结束，立即重试
                    continue
                logger.warning("所有端点均在限流冷却中，等待 %.1f 秒...", wait_time)
                _time.sleep(wait_time)
                continue

            try:
                logger.debug(
                    "使用端点 [%s] 发送请求 (attempt=%d)",
                    state.endpoint.name,
                    attempt + 1,
                )

                # 如果调用方没有指定 model，使用端点自己的 model
                effective_model = model or state.endpoint.model or self.config.model

                response = state.client.create_message(
                    messages=messages,
                    system=system,
                    tools=tools,
                    max_tokens=max_tokens,
                    model=effective_model,
                )
                state.mark_success()

                # 记录成功端点的索引和客户端引用
                self._last_success_index = self._endpoint_states.index(state)
                response._source_client = state.client

                logger.info(
                    "请求成功: 端点=[%s], tokens=%d+%d",
                    state.endpoint.name,
                    response.input_tokens,
                    response.output_tokens,
                )
                return response

            except Exception as e:
                last_exc = e
                state.last_error = str(e)[:500]

                if _is_rate_limit_error(e):
                    retry_after = _extract_retry_after(e)
                    cooldown = self.config.rate_limit_cooldown
                    state.mark_rate_limited(cooldown, retry_after)

                    logger.warning(
                        "端点 [%s] 触发限流 (错误: %s)，冷却 %.0f 秒，尝试切换...",
                        state.endpoint.name,
                        str(e)[:200],
                        retry_after or cooldown,
                    )
                    continue  # 尝试下一个端点
                else:
                    # 非限流错误，直接抛出（不切换端点）
                    state.mark_non_rate_error()
                    logger.error(
                        "端点 [%s] 非限流错误: %s",
                        state.endpoint.name,
                        str(e)[:200],
                    )
                    raise

        # 所有重试用尽
        raise RuntimeError(
            f"所有 LLM 端点均不可用 (尝试 {max_retries} 次轮转后放弃)。"
            f"最后错误: {last_exc}"
        )

    def build_tool_result_message(
        self,
        assistant_response: LLMResponse,
        tool_results: list[dict],
    ) -> list[dict]:
        """
        构建工具结果消息。

        必须使用**生成该 response 的同一个客户端**来构建，
        否则 Anthropic 格式的 raw_response 会被 OpenAI 客户端误解析（反之亦然）。
        """
        # 优先使用生成该响应的客户端
        source_client = assistant_response._source_client
        if source_client is not None:
            return source_client.build_tool_result_message(
                assistant_response, tool_results
            )

        # 兜底：使用第一个端点
        logger.warning(
            "build_tool_result_message: 未找到 source_client，使用第一个端点"
        )
        return self._endpoint_states[0].client.build_tool_result_message(
            assistant_response, tool_results
        )

    # ─── 端点选择策略 ──────────────────────────────────────────

    def _pick_available_endpoint(self) -> Optional[_EndpointState]:
        """
        选择下一个可用端点。

        策略（Sticky-First）：
        1. 优先使用上次成功的端点，保持 Agentic Loop 中消息格式一致
           （避免 Anthropic ↔ OpenAI 格式切换导致的不兼容错误）
        2. 如果上次成功的端点不可用（被限流），轮转查找同协议端点
        3. 最后才降级到不同协议的端点
        """
        n = len(self._endpoint_states)

        # 1. 优先使用上次成功的端点
        last_state = self._endpoint_states[self._last_success_index]
        last_state.check_cooldown()
        if last_state.is_available:
            return last_state

        # 2. 上次端点不可用，优先查找同协议的其他端点
        last_provider = last_state.endpoint.provider
        for i in range(n):
            idx = (self._last_success_index + 1 + i) % n
            state = self._endpoint_states[idx]
            state.check_cooldown()
            if state.is_available and state.endpoint.provider == last_provider:
                return state

        # 3. 同协议端点都不可用，降级到任意可用端点
        for i in range(n):
            state = self._endpoint_states[i]
            state.check_cooldown()
            if state.is_available:
                return state

        return None

    def _wait_for_earliest_recovery(self) -> float:
        """
        计算最短等待时间（到最早一个端点冷却结束）。

        Returns:
            float: 需要等待的秒数，0 表示有端点已恢复
        """
        now = _time.time()
        earliest = float("inf")
        for state in self._endpoint_states:
            if not state.is_available and state.rate_limited_until > 0:
                remaining = state.rate_limited_until - now
                if remaining <= 0:
                    state.check_cooldown()
                    return 0
                earliest = min(earliest, remaining)
        return earliest if earliest != float("inf") else 0

    # ─── 状态查询（用于监控和测试） ──────────────────────────

    @property
    def endpoint_count(self) -> int:
        """端点总数"""
        return len(self._endpoint_states)

    @property
    def available_count(self) -> int:
        """当前可用端点数"""
        return sum(1 for s in self._endpoint_states if s.check_cooldown())

    @property
    def active_endpoint_name(self) -> str:
        """当前活跃端点名"""
        state = self._pick_available_endpoint()
        return state.endpoint.name if state else "(全部不可用)"

    def get_status(self) -> list[dict]:
        """获取所有端点状态（用于监控 API）"""
        statuses = []
        now = _time.time()
        for state in self._endpoint_states:
            state.check_cooldown()
            remaining = max(0, state.rate_limited_until - now)
            statuses.append(
                {
                    "name": state.endpoint.name,
                    "provider": state.endpoint.provider.value,
                    "model": state.endpoint.model,
                    "available": state.is_available,
                    "cooldown_remaining": round(remaining, 1),
                    "consecutive_failures": state.consecutive_failures,
                    "total_requests": state.total_requests,
                    "total_failures": state.total_failures,
                    "last_error": state.last_error,
                }
            )
        return statuses

    @property
    def provider_name(self) -> str:
        return f"RateLimitAware ({self.endpoint_count} endpoints)"


# ─── 内部工厂函数 ────────────────────────────────────────────────


def _create_single_client(
    config: LLMConfig,
    endpoint: Optional[LLMEndpointConfig] = None,
) -> BaseLLMClient:
    """
    为单个端点创建原始 LLM 客户端（不含限流包装）。

    自动检测逻辑：
    1. 如果 base_url 包含 "/anthropic"，使用 Anthropic 客户端
    2. 否则根据 provider 字段选择
    """
    if endpoint:
        # 为端点构建独立的 LLMConfig
        ep_config = LLMConfig(
            provider=endpoint.provider,
            base_url=endpoint.base_url,
            api_key=endpoint.api_key,
            model=endpoint.model,
            enable_thinking=(
                endpoint.enable_thinking
                if endpoint.enable_thinking is not None
                else config.enable_thinking
            ),
            temperature=(
                endpoint.temperature
                if endpoint.temperature is not None
                else config.temperature
            ),
            max_tokens=config.max_tokens,
        )
    else:
        ep_config = config

    provider = ep_config.provider

    # 自动检测：如果 base_url 包含 "/anthropic" 但 provider 是 openai，自动纠正
    if ep_config.base_url:
        url = ep_config.base_url.lower()
        if "/anthropic" in url and provider == LLMProvider.OPENAI:
            logger.warning(
                "base_url 包含 '/anthropic' 但 provider 设为 'openai'，"
                "自动切换为 Anthropic 协议。"
            )
            provider = LLMProvider.ANTHROPIC
            ep_config.provider = LLMProvider.ANTHROPIC

    if provider == LLMProvider.ANTHROPIC:
        return AnthropicLLMClient(ep_config)
    elif provider == LLMProvider.OPENAI:
        return OpenAICompatibleLLMClient(ep_config)
    else:
        raise ValueError(f"不支持的 LLM Provider: {provider}")


# ─── 公开工厂函数 ────────────────────────────────────────────────


def create_llm_client(config: LLMConfig) -> BaseLLMClient:
    """
    根据配置创建对应的 LLM 客户端。

    决策逻辑：
    - 如果配置了多端点（LLM_ENDPOINTS），返回 RateLimitAwareClient
      支持限流自动降级轮转
    - 如果只有单端点，返回原始客户端（AnthropicLLMClient 或 OpenAICompatibleLLMClient）

    Args:
        config: LLM 配置

    Returns:
        BaseLLMClient: 对应的客户端实例
    """
    if config.has_failover:
        return RateLimitAwareClient(config)

    # 无备用端点，返回单客户端
    return _create_single_client(config)
