"""
应用配置模块

通过环境变量或 .env 文件加载配置。
支持多种 LLM 后端：
  - Anthropic 原生协议（Claude 系列）
  - OpenAI 兼容协议（MiniMax、DeepSeek、Moonshot、通义千问等国内模型）

支持多端点轮转与限流降级：
  - 配置多个 LLM 端点（不同 provider / API key / base_url）
  - API 触发限流后自动切换到下一个可用端点
  - 限流冷却期自动恢复

支持多模态 Vision 模型独立配置：
  - 文本模型与多模态模型分离配置
  - 文本模型：按优先级顺序降级（超限/fallback）
  - 多模态模型：均衡轮转（round-robin，均摊每日配额）
  - 未配置时使用后端 .env 默认模型
"""

import json
import os
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass


class LLMProvider(str, Enum):
    """LLM 后端协议类型"""

    ANTHROPIC = "anthropic"  # Anthropic 原生 SDK
    OPENAI = "openai"  # OpenAI 兼容接口（适用于 MiniMax、DeepSeek 等）

    @classmethod
    def from_str(cls, value: str) -> "LLMProvider":
        """从字符串解析 Provider 类型，支持模糊匹配"""
        value = value.strip().lower()
        if value in ("anthropic", "claude"):
            return cls.ANTHROPIC
        elif value in (
            "openai",
            "openai_compatible",
            "minimax",
            "deepseek",
            "moonshot",
            "qwen",
        ):
            return cls.OPENAI
        else:
            # 默认：如果 base_url 包含 anthropic 则用 anthropic 协议，否则用 openai
            return cls.OPENAI


class FailoverMode(str, Enum):
    """端点降级/轮转策略"""

    SEQUENTIAL = "sequential"  # 顺序降级：按优先级排序，超限/失败后切换下一个
    ROUND_ROBIN = "round_robin"  # 均衡轮转：每次请求轮流使用，均摊配额


@dataclass
class VisionEndpointConfig:
    """
    单个多模态 Vision 端点配置。

    用于视觉理解模型（如豆包 doubao-seed-2-0）：
    - 每个端点可以是不同的 base_url / api_key / model 组合
    - 支持 round-robin 均衡轮转（均摊每日 token 配额）
    - 支持 OpenAI Responses API（client.responses.create）
    """

    name: str  # 端点标识名
    base_url: str = ""  # API 基础地址
    api_key: str = ""  # API Key
    model: str = ""  # 模型名称
    api_type: str = (
        "chat"  # API 调用类型: "chat" | "responses" (chat = Chat Completions, responses = OpenAI Responses API >= 1.66.0)
    )
    max_tokens: Optional[int] = None  # 单端点输出 token 上限（None 使用客户端默认值）
    priority: int = 0  # 优先级（数值越小优先级越高）

    @property
    def effective_base_url(self) -> Optional[str]:
        if self.base_url:
            return self.base_url.rstrip("/")
        return None

    @property
    def display_name(self) -> str:
        return f"{self.name} ({self.model})"


@dataclass
class LLMEndpointConfig:
    """
    单个 LLM 端点配置。

    用于多端点轮转场景：每个端点可以是不同的 provider、base_url、api_key、model 组合。
    当某个端点触发限流时，系统自动切换到下一个可用端点。
    """

    name: str  # 端点标识名（如 "minimax-primary", "nvidia-1"）
    provider: LLMProvider  # 协议类型
    base_url: Optional[str] = None  # API 基础地址
    api_key: str = ""  # API Key
    model: str = ""  # 模型名称
    enable_thinking: Optional[bool] = None  # 是否启用 thinking（None 则继承主配置）
    temperature: Optional[float] = None  # 温度参数（None 则继承主配置）
    priority: int = 0  # 优先级（数值越小优先级越高）

    @property
    def effective_base_url(self) -> Optional[str]:
        if self.base_url:
            return self.base_url.rstrip("/")
        return None

    @property
    def display_name(self) -> str:
        """显示友好的端点名称"""
        return f"{self.name} ({self.provider.value}://{self.model})"


def _parse_endpoints_from_env() -> list[LLMEndpointConfig]:
    """
    从环境变量解析多端点配置。

    支持两种配置方式：

    方式一：JSON 数组格式（推荐，灵活度最高）
        LLM_ENDPOINTS='[
            {"name": "minimax-primary", "provider": "openai",
             "base_url": "https://api.minimaxi.com/v1",
             "api_key": "sk-xxx", "model": "MiniMax-M3", "priority": 0},
            {"name": "nvidia-1", "provider": "openai",
             "base_url": "https://integrate.api.nvidia.com/v1",
             "api_key": "nvapi-xxx", "model": "minimaxai/minimax-m2.1", "priority": 1}
        ]'

    方式二：编号环境变量格式（适合在 .env 中分行书写）
        LLM_ENDPOINT_1_NAME=minimax-primary
        LLM_ENDPOINT_1_PROVIDER=anthropic
        LLM_ENDPOINT_1_BASE_URL=https://api.minimaxi.com/anthropic
        LLM_ENDPOINT_1_API_KEY=replace-me
        LLM_ENDPOINT_1_MODEL=MiniMax-M3
        LLM_ENDPOINT_1_PRIORITY=0
    """
    endpoints = []

    # 方式一：JSON 数组
    json_str = os.getenv("LLM_ENDPOINTS", "").strip()
    if json_str:
        try:
            raw_list = json.loads(json_str)
            for item in raw_list:
                endpoints.append(
                    LLMEndpointConfig(
                        name=item["name"],
                        provider=LLMProvider.from_str(item.get("provider", "openai")),
                        base_url=item.get("base_url"),
                        api_key=item.get("api_key", ""),
                        model=item.get("model", ""),
                        enable_thinking=item.get("enable_thinking"),
                        temperature=item.get("temperature"),
                        priority=item.get("priority", 0),
                    )
                )
            return sorted(endpoints, key=lambda e: e.priority)
        except (json.JSONDecodeError, KeyError):
            pass

    # 方式二：编号环境变量
    idx = 1
    while True:
        prefix = f"LLM_ENDPOINT_{idx}_"
        name = os.getenv(f"{prefix}NAME", "").strip()
        if not name:
            break
        ep = LLMEndpointConfig(
            name=name,
            provider=LLMProvider.from_str(os.getenv(f"{prefix}PROVIDER", "openai")),
            base_url=os.getenv(f"{prefix}BASE_URL"),
            api_key=os.getenv(f"{prefix}API_KEY", ""),
            model=os.getenv(f"{prefix}MODEL", ""),
            enable_thinking={"true": True, "false": False}.get(
                os.getenv(f"{prefix}ENABLE_THINKING", "").lower()
            ),
            temperature=(
                float(os.getenv(f"{prefix}TEMPERATURE"))
                if os.getenv(f"{prefix}TEMPERATURE")
                else None
            ),
            priority=int(os.getenv(f"{prefix}PRIORITY", str(idx))),
        )
        endpoints.append(ep)
        idx += 1

    return sorted(endpoints, key=lambda e: e.priority)


def _parse_vision_endpoints_from_env() -> list[VisionEndpointConfig]:
    """
    从环境变量解析多模态 Vision 端点配置。

    支持两种配置方式：

    方式一：JSON 数组格式
        VISION_ENDPOINTS='[
            {"name": "doubao-lite", "base_url": "https://ark.cn-beijing.volces.com/api/v3",
             "api_key": "xxx", "model": "doubao-seed-2-0-lite-260215", "api_type": "chat"},
            {"name": "doubao-pro", "base_url": "https://ark.cn-beijing.volces.com/api/v3",
             "api_key": "xxx", "model": "doubao-seed-2-0-pro-260215", "api_type": "chat"}
        ]'

    方式二：编号环境变量格式
        VISION_ENDPOINT_1_NAME=doubao-lite
        VISION_ENDPOINT_1_BASE_URL=https://ark.cn-beijing.volces.com/api/v3
        VISION_ENDPOINT_1_API_KEY=xxx
        VISION_ENDPOINT_1_MODEL=doubao-seed-2-0-lite-260215
        VISION_ENDPOINT_1_API_TYPE=chat
        VISION_ENDPOINT_1_MAX_TOKENS=2048
        VISION_ENDPOINT_1_PRIORITY=0

    API Key 解析顺序：
        1. 端点自身的 api_key 字段
        2. ARK_API_KEY 环境变量（火山引擎通用密钥，适用于 base_url 含 volces.com 的端点）
        3. VISION_API_KEY 环境变量（兜底）
    """
    # 通用 ARK API Key fallback（火山引擎统一密钥）
    ark_api_key = os.getenv("ARK_API_KEY", "")

    def _resolve_api_key(key: str, base_url: str = "") -> str:
        """解析 API Key，支持 ARK_API_KEY fallback"""
        if key:
            return key
        # 火山引擎端点优先使用 ARK_API_KEY
        if ark_api_key and ("volces" in base_url.lower() or "ark" in base_url.lower()):
            return ark_api_key
        return ""

    endpoints = []

    # 方式一：JSON 数组
    json_str = os.getenv("VISION_ENDPOINTS", "").strip()
    if json_str:
        try:
            raw_list = json.loads(json_str)
            for item in raw_list:
                base_url = item.get("base_url", "")
                endpoints.append(
                    VisionEndpointConfig(
                        name=item["name"],
                        base_url=base_url,
                        api_key=_resolve_api_key(item.get("api_key", ""), base_url),
                        model=item.get("model", ""),
                        api_type=item.get("api_type", "chat"),
                        max_tokens=item.get("max_tokens"),
                        priority=item.get("priority", 0),
                    )
                )
            return sorted(endpoints, key=lambda e: e.priority)
        except (json.JSONDecodeError, KeyError):
            pass

    # 方式二：编号环境变量
    idx = 1
    while True:
        prefix = f"VISION_ENDPOINT_{idx}_"
        name = os.getenv(f"{prefix}NAME", "").strip()
        if not name:
            break
        base_url = os.getenv(f"{prefix}BASE_URL", "")
        raw_key = os.getenv(f"{prefix}API_KEY", "")
        ep = VisionEndpointConfig(
            name=name,
            base_url=base_url,
            api_key=_resolve_api_key(raw_key, base_url),
            model=os.getenv(f"{prefix}MODEL", ""),
            api_type=os.getenv(f"{prefix}API_TYPE", "chat"),
            max_tokens=(
                int(os.getenv(f"{prefix}MAX_TOKENS"))
                if os.getenv(f"{prefix}MAX_TOKENS")
                else None
            ),
            priority=int(os.getenv(f"{prefix}PRIORITY", str(idx))),
        )
        endpoints.append(ep)
        idx += 1

    return sorted(endpoints, key=lambda e: e.priority)


@dataclass
class VisionConfig:
    """
    多模态 Vision 模型配置。

    独立于文本模型的配置，专用于图片/视觉理解任务。
    支持豆包（字节火山引擎 ARK）Responses API。

    单端点：
      VISION_API_KEY=your-ark-api-key
      VISION_BASE_URL=https://ark.cn-beijing.volces.com/api/v3
      VISION_MODEL=doubao-seed-2-0-lite-260215

    多端点均衡轮转（均摊每日免费配额）：
      通过 VISION_ENDPOINTS 或 VISION_ENDPOINT_N_* 配置多个端点，
      默认使用 round-robin 策略轮转。
    """

    # 主端点参数
    base_url: str = field(
        default_factory=lambda: os.getenv(
            "VISION_BASE_URL", "https://ark.cn-beijing.volces.com/api/v3"
        )
    )
    api_key: str = field(default_factory=lambda: os.getenv("VISION_API_KEY", ""))
    model: str = field(
        default_factory=lambda: os.getenv("VISION_MODEL", "doubao-seed-2-0-lite-260215")
    )

    # API 调用类型（chat = OpenAI Chat Completions, responses = OpenAI Responses API >= 1.66.0）
    api_type: str = field(default_factory=lambda: os.getenv("VISION_API_TYPE", "chat"))

    # 轮转策略
    failover_mode: FailoverMode = field(
        default_factory=lambda: FailoverMode(
            os.getenv("VISION_FAILOVER_MODE", "round_robin")
        )
    )

    # 多端点配置
    endpoints: list[VisionEndpointConfig] = field(
        default_factory=_parse_vision_endpoints_from_env
    )

    # 限流冷却时间（秒）
    rate_limit_cooldown: int = field(
        default_factory=lambda: int(os.getenv("VISION_RATE_LIMIT_COOLDOWN", "60"))
    )

    # 最大重试次数
    max_retries: int = field(
        default_factory=lambda: int(os.getenv("VISION_MAX_RETRIES", "3"))
    )

    @property
    def is_configured(self) -> bool:
        """是否配置了 Vision 模型（有 API Key 或有端点配置）"""
        return bool(self.api_key) or len(self.endpoints) > 0

    @property
    def effective_base_url(self) -> Optional[str]:
        if self.base_url:
            return self.base_url.rstrip("/")
        return None

    @property
    def has_endpoints(self) -> bool:
        return len(self.endpoints) > 0

    @property
    def provider_display_name(self) -> str:
        if self.base_url and "volces" in self.base_url.lower():
            if self.api_type == "responses":
                return "火山引擎 ARK (Responses API)"
            return "豆包 (Doubao)"
        if self.base_url and "nvidia" in self.base_url.lower():
            return "NVIDIA NIM"
        if self.base_url and "openai" in self.base_url.lower():
            return "OpenAI Vision"
        return "Vision API"

    def validate(self) -> list[str]:
        """校验 Vision 配置，返回错误列表"""
        if not self.is_configured:
            return []  # 未配置不算错误，只是不启用
        errors = []
        if not self.api_key and not self.endpoints:
            errors.append("VISION_API_KEY 未设置，且无 Vision 端点配置")
        return errors


@dataclass
class LLMConfig:
    """
    LLM 连接配置。

    支持三种使用方式：

    1. Anthropic 原生协议（默认）：
       LLM_PROVIDER=anthropic
       LLM_API_KEY=replace-me
       LLM_MODEL=claude-opus-4-6

    2. OpenAI 兼容协议（MiniMax 等国内模型）：
       LLM_PROVIDER=openai
       LLM_BASE_URL=https://api.minimaxi.com/v1
       LLM_API_KEY=your-minimax-api-key
       LLM_MODEL=MiniMax-M3

    3. MiniMax Anthropic 兼容协议：
       LLM_PROVIDER=anthropic
       LLM_BASE_URL=https://api.minimaxi.com/anthropic
       LLM_API_KEY=your-minimax-api-key
       LLM_MODEL=MiniMax-M3

    多端点轮转（限流降级）：
       通过 LLM_ENDPOINTS 或 LLM_ENDPOINT_N_* 环境变量配置多个端点，
       触发限流时自动切换到下一个可用端点。
    """

    # 协议类型
    provider: LLMProvider = field(
        default_factory=lambda: LLMProvider.from_str(
            os.getenv("LLM_PROVIDER", "anthropic")
        )
    )

    # API 连接参数（核心三要素：base_url + api_key + model）
    base_url: Optional[str] = field(
        default_factory=lambda: os.getenv("LLM_BASE_URL", None)
    )
    api_key: str = field(
        default_factory=lambda: os.getenv(
            "LLM_API_KEY",
            os.getenv("ANTHROPIC_API_KEY", ""),  # 兼容旧配置
        )
    )
    model: str = field(
        default_factory=lambda: os.getenv("LLM_MODEL", "claude-opus-4-6")
    )

    # 辅助模型（用于低延迟任务如学生信息提取、格式校验）
    auxiliary_model: Optional[str] = field(
        default_factory=lambda: os.getenv("LLM_AUXILIARY_MODEL", None)
    )

    # 模型行为参数
    max_tokens: int = field(
        default_factory=lambda: int(os.getenv("LLM_MAX_TOKENS", "16384"))
    )
    temperature: float = field(
        default_factory=lambda: float(os.getenv("LLM_TEMPERATURE", "0.05"))
    )

    # 是否启用深度思考（Adaptive Thinking / Interleaved Thinking）
    enable_thinking: bool = field(
        default_factory=lambda: os.getenv("LLM_ENABLE_THINKING", "true").lower()
        == "true"
    )

    # 文本模型降级策略
    failover_mode: FailoverMode = field(
        default_factory=lambda: FailoverMode(
            os.getenv("LLM_FAILOVER_MODE", "sequential")
        )
    )

    # 多端点轮转配置
    failover_endpoints: list[LLMEndpointConfig] = field(
        default_factory=_parse_endpoints_from_env
    )

    # 限流冷却时间（秒）— 端点触发限流后多久重新加入轮转
    rate_limit_cooldown: int = field(
        default_factory=lambda: int(os.getenv("LLM_RATE_LIMIT_COOLDOWN", "60"))
    )

    # 单次请求最大重试次数（跨端点轮转）
    max_failover_retries: int = field(
        default_factory=lambda: int(os.getenv("LLM_MAX_FAILOVER_RETRIES", "3"))
    )

    def validate(self) -> list[str]:
        """校验 LLM 配置，返回错误列表"""
        errors = []
        if not self.api_key and not self.failover_endpoints:
            errors.append("LLM_API_KEY 未设置，且无备用端点配置")
        if not self.model and not self.failover_endpoints:
            errors.append("LLM_MODEL 未设置，且无备用端点配置")
        return errors

    @property
    def effective_base_url(self) -> Optional[str]:
        """
        获取有效的 base_url。
        Anthropic 原生协议且无自定义 base_url 时返回 None（使用 SDK 默认值）。
        """
        if self.base_url:
            return self.base_url.rstrip("/")
        return None

    @property
    def provider_display_name(self) -> str:
        """显示友好的 Provider 名称"""
        if self.base_url and "minimax" in self.base_url.lower():
            return f"MiniMax ({self.provider.value})"
        if self.base_url and "deepseek" in self.base_url.lower():
            return f"DeepSeek ({self.provider.value})"
        if self.base_url and "nvidia" in self.base_url.lower():
            return f"NVIDIA ({self.provider.value})"
        return self.provider.value.capitalize()

    @property
    def has_failover(self) -> bool:
        """是否配置了多端点轮转"""
        return len(self.failover_endpoints) > 0


@dataclass
class AppConfig:
    """应用全局配置"""

    # LLM 配置（文本模型）
    llm: LLMConfig = field(default_factory=LLMConfig)

    # Vision 配置（多模态模型）
    vision: VisionConfig = field(default_factory=VisionConfig)

    # 并发控制
    max_concurrency: int = field(
        default_factory=lambda: int(os.getenv("MAX_CONCURRENCY", "3"))
    )
    max_agent_iterations: int = field(
        default_factory=lambda: int(os.getenv("MAX_AGENT_ITERATIONS", "20"))
    )

    # 文件存储
    upload_dir: str = field(
        default_factory=lambda: os.getenv(
            "UPLOAD_DIR", os.path.join(os.path.dirname(__file__), "..", "_uploads")
        )
    )
    output_dir: str = field(
        default_factory=lambda: os.getenv(
            "OUTPUT_DIR", os.path.join(os.path.dirname(__file__), "..", "_outputs")
        )
    )

    # 评分标准目录
    rubrics_dir: str = field(
        default_factory=lambda: os.getenv(
            "RUBRICS_DIR",
            os.path.join(os.path.dirname(__file__), "..", "config", "rubrics"),
        )
    )

    # Agent Skills 脚本根目录
    skills_dir: str = field(
        default_factory=lambda: os.path.join(
            os.path.dirname(__file__), "..", "agent_skills"
        )
    )

    # 签名配置文件路径
    signature_config_path: str = field(
        default_factory=lambda: os.path.join(
            os.path.dirname(__file__), "..", "config", "signature.json"
        )
    )

    # 签名图片资源目录
    signature_assets_dir: str = field(
        default_factory=lambda: os.path.join(
            os.path.dirname(__file__), "..", "config", "assets"
        )
    )

    # Human-in-the-loop
    confidence_threshold: float = field(
        default_factory=lambda: float(os.getenv("CONFIDENCE_THRESHOLD", "0.7"))
    )

    # 视频分析
    ffmpeg_path: str = field(default_factory=lambda: os.getenv("FFMPEG_PATH", "ffmpeg"))
    ffprobe_path: str = field(
        default_factory=lambda: os.getenv("FFPROBE_PATH", "ffprobe")
    )
    max_video_frames: int = 8

    # 服务器
    host: str = field(default_factory=lambda: os.getenv("HOST", "0.0.0.0"))
    port: int = field(default_factory=lambda: int(os.getenv("PORT", "11314")))
    debug: bool = field(
        default_factory=lambda: os.getenv("DEBUG", "false").lower() == "true"
    )

    def validate(self) -> list[str]:
        """校验全部配置，返回错误列表"""
        errors = self.llm.validate()
        errors.extend(self.vision.validate())
        if not os.path.isdir(self.rubrics_dir):
            errors.append(f"评分标准目录不存在: {self.rubrics_dir}")
        return errors


def get_config() -> AppConfig:
    """获取应用配置的便捷函数"""
    return AppConfig()
