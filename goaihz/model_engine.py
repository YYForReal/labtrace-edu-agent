"""Real-LLM grading adapter with privacy filtering and deterministic validation."""

from __future__ import annotations

import asyncio
import json
import os
import re
import threading
import time
from collections import Counter, deque
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.agent.llm_client import BaseLLMClient, create_llm_client
from app.config import LLMConfig, LLMProvider
from goaihz.demo_engine import build_demo_trace
from goaihz.src.labtrace.contracts import (
    ContractError,
    CriterionDecision,
    EvidenceRef,
    GradeTrace,
    ReviewDecision,
)
from goaihz.src.labtrace.privacy import find_sensitive_data, pseudonymize

_MODEL_CALLS: deque[float] = deque()
_MODEL_CALLS_LOCK = threading.Lock()
_GENERIC_NAMES = {
    "实验报告",
    "课程报告",
    "学生",
    "匿名学生",
    "本科生",
    "研究生",
    "未知",
}


@dataclass(frozen=True)
class GradingOutcome:
    trace: GradeTrace
    mode: str
    run: dict[str, Any]
    privacy: dict[str, Any]


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def model_runtime_status() -> dict[str, Any]:
    api_key = os.getenv("LLM_API_KEY", os.getenv("ANTHROPIC_API_KEY", "")).strip()
    enabled = _env_bool("LABTRACE_LLM_ENABLED", True)
    configured = bool(enabled and api_key)
    provider = LLMProvider.from_str(os.getenv("LLM_PROVIDER", "anthropic"))
    model = os.getenv("LLM_MODEL", "MiniMax-M3").strip() or "MiniMax-M3"
    base_url = os.getenv("LLM_BASE_URL", "").lower()
    if "minimax" in base_url:
        provider_label = "MiniMax"
    elif provider is LLMProvider.ANTHROPIC:
        provider_label = "Anthropic"
    else:
        provider_label = "OpenAI-compatible"
    daily_limit = max(1, int(os.getenv("LABTRACE_LLM_DAILY_LIMIT", "100")))
    now = time.time()
    with _MODEL_CALLS_LOCK:
        while _MODEL_CALLS and now - _MODEL_CALLS[0] >= 86400:
            _MODEL_CALLS.popleft()
        remaining = max(0, daily_limit - len(_MODEL_CALLS))
    return {
        "configured": configured,
        "enabled": enabled,
        "provider": provider_label,
        "model": model,
        "daily_limit": daily_limit,
        "daily_remaining": remaining,
        "external_processing": configured,
    }


def _claim_model_call() -> bool:
    status = model_runtime_status()
    if not status["configured"] or status["daily_remaining"] <= 0:
        return False
    with _MODEL_CALLS_LOCK:
        now = time.time()
        while _MODEL_CALLS and now - _MODEL_CALLS[0] >= 86400:
            _MODEL_CALLS.popleft()
        if len(_MODEL_CALLS) >= status["daily_limit"]:
            return False
        _MODEL_CALLS.append(now)
    return True


def _safe_student_terms(parsed: dict[str, Any]) -> tuple[str | None, str | None]:
    student_info = parsed.get("student_info") or {}
    raw_name = str(student_info.get("name", "")).strip()
    raw_id = str(student_info.get("student_id", "")).strip()
    name = (
        raw_name
        if 2 <= len(raw_name) <= 30 and raw_name not in _GENERIC_NAMES
        else None
    )
    student_id = raw_id if 4 <= len(raw_id) <= 40 else None
    return name, student_id


def _redact(value: str, *, name: str | None, student_id: str | None) -> str:
    return pseudonymize(
        value,
        student_name=name,
        student_id=student_id,
    )


def build_model_evidence(
    parsed: dict[str, Any],
    *,
    external_images: bool = False,
    externally_observed_image_positions: set[int] | None = None,
) -> tuple[list[EvidenceRef], dict[str, Any]]:
    """Build a bounded, pseudonymized evidence catalog for the external model."""
    name, student_id = _safe_student_terms(parsed)
    findings: Counter[str] = Counter()
    catalog: list[EvidenceRef] = []
    max_chars = max(8_000, int(os.getenv("LABTRACE_LLM_EVIDENCE_CHARS", "50000")))
    consumed = 0
    source_suffix = Path(str(parsed.get("file_path", "report.docx"))).suffix.lower()
    source_file = f"anonymous-upload{source_suffix or '.docx'}"

    def add(
        evidence_id: str,
        kind: str,
        locator: str,
        raw_text: str,
        reliability: float,
        verification: str,
        limit: int,
    ) -> None:
        nonlocal consumed
        if consumed >= max_chars:
            return
        for item in find_sensitive_data(raw_text):
            findings[str(item["kind"])] += 1
        text = _redact(raw_text, name=name, student_id=student_id)
        compact = re.sub(r"\s+", " ", text).strip()
        if not compact:
            return
        compact = compact[:limit]
        if consumed + len(compact) > max_chars:
            compact = compact[: max(0, max_chars - consumed)]
        if not compact:
            return
        consumed += len(compact)
        catalog.append(
            EvidenceRef(
                evidence_id=evidence_id,
                kind=kind,
                source_file=source_file,
                locator=locator,
                excerpt=compact,
                reliability=reliability,
                verification=verification,
            )
        )

    for index, item in enumerate(parsed.get("paragraphs") or [], start=1):
        add(
            f"p-{index:04d}",
            "paragraph",
            f"paragraph:{index}",
            str(item.get("text", "")),
            0.96,
            "parser_observed",
            700,
        )
    for index, item in enumerate(parsed.get("tables") or [], start=1):
        rows = item.get("data") or []
        text = "；".join(" | ".join(str(cell) for cell in row) for row in rows[:20])
        add(
            f"t-{index:04d}",
            "table",
            f"table:{int(item.get('index', index - 1)) + 1}",
            text,
            0.94,
            "parser_observed",
            1_500,
        )
    for index, item in enumerate(parsed.get("images") or [], start=1):
        image_observed = (
            index in externally_observed_image_positions
            if externally_observed_image_positions is not None
            else external_images
        )
        context = str(
            item.get("context")
            or item.get("description")
            or "报告包含一张未由文本模型直接查看的图片"
        )
        source_index = int(item.get("index", index - 1))
        locator = f"image:{source_index + 1}"
        docx_paragraph_index = item.get("docx_paragraph_index")
        if isinstance(docx_paragraph_index, int) and docx_paragraph_index >= 0:
            locator += f"@paragraph:{docx_paragraph_index + 1}"
        add(
            f"i-{index:04d}",
            "image_context",
            locator,
            context,
            0.86 if image_observed else 0.55,
            "model_observed" if image_observed else "parser_context_only",
            500,
        )

    named_terms = int(bool(name)) + int(bool(student_id))
    externally_observed_count = (
        len(externally_observed_image_positions)
        if externally_observed_image_positions is not None
        else (len(parsed.get("images") or []) if external_images else 0)
    )
    return catalog, {
        "policy": "redact_before_external_model",
        "detected_sensitive_items": sum(findings.values()) + named_terms,
        "detected_by_kind": dict(sorted(findings.items())),
        "recognized_identity_terms_redacted": named_terms,
        "images_sent_to_text_model": externally_observed_count > 0,
        "external_image_count": externally_observed_count,
        "retention": "任务文件默认保留 24 小时，可立即删除",
    }


def _client_from_environment() -> tuple[BaseLLMClient, LLMConfig]:
    config = LLMConfig(
        provider=LLMProvider.from_str(os.getenv("LLM_PROVIDER", "anthropic")),
        base_url=os.getenv("LLM_BASE_URL") or None,
        api_key=os.getenv("LLM_API_KEY", os.getenv("ANTHROPIC_API_KEY", "")),
        model=os.getenv("LLM_MODEL", "MiniMax-M3"),
        enable_thinking=_env_bool("LABTRACE_LLM_ENABLE_THINKING", False),
        temperature=float(os.getenv("LABTRACE_LLM_TEMPERATURE", "0.05")),
        max_tokens=max(512, int(os.getenv("LABTRACE_LLM_MAX_TOKENS", "3200"))),
        failover_endpoints=[],
    )
    return create_llm_client(config), config


def _prompt_payload(
    rubric: dict[str, Any],
    profile: dict[str, Any],
    evidence: list[EvidenceRef],
) -> dict[str, Any]:
    compact_rubric = {
        "experiment_id": rubric["experiment_id"],
        "experiment_name": rubric["experiment_name"],
        "total_score": rubric["total_score"],
        "description": rubric.get("description", ""),
        "criteria": rubric["criteria"],
        "reference_implementation": rubric.get("reference_implementation", {}),
        "few_shot_examples": rubric.get("few_shot_examples", []),
    }
    return {
        "task": "依据评分标准逐项评估高校实验报告，只能引用 evidence_catalog 中存在的 evidence_id。",
        "rubric": compact_rubric,
        "document_profile": profile,
        "evidence_catalog": [
            {
                "evidence_id": item.evidence_id,
                "kind": item.kind,
                "locator": item.locator,
                "excerpt": item.excerpt,
                "reliability": item.reliability,
                "verification": item.verification,
            }
            for item in evidence
        ],
        "output_contract": {
            "criteria": [
                {
                    "criterion_id": "必须与 rubric id 完全一致",
                    "score": "0 到该维度 max_score 的数值",
                    "reason": "简洁、具体、指出优点与缺口，不编造材料",
                    "evidence_ids": ["只允许 evidence_catalog 中的 id"],
                    "confidence": "0 到 1；图片仅有上下文时不得高估",
                }
            ],
            "overall_summary": "不超过 300 字",
            "risks": ["需要教师重点复核的事项"],
        },
    }


def _extract_json(text: str) -> dict[str, Any]:
    candidate = text.strip()
    fenced = re.search(r"```(?:json)?\s*(\{.*\})\s*```", candidate, re.S | re.I)
    if fenced:
        candidate = fenced.group(1)
    try:
        value = json.loads(candidate)
    except json.JSONDecodeError:
        start = candidate.find("{")
        end = candidate.rfind("}")
        if start < 0 or end <= start:
            raise ContractError("模型没有返回 JSON 对象")
        try:
            value = json.loads(candidate[start : end + 1])
        except json.JSONDecodeError as exc:
            raise ContractError("模型返回的 JSON 无法解析") from exc
    if not isinstance(value, dict):
        raise ContractError("模型输出根节点必须是 JSON 对象")
    return value


def _trace_from_model_output(
    output: dict[str, Any],
    *,
    rubric: dict[str, Any],
    evidence_catalog: list[EvidenceRef],
    trace_id: str,
    submission_alias: str,
) -> GradeTrace:
    expected = {str(item["id"]): item for item in rubric["criteria"]}
    for wrapper_key in ("result", "grading_result", "grade_trace"):
        wrapped = output.get(wrapper_key)
        if isinstance(wrapped, dict) and isinstance(wrapped.get("criteria"), list):
            output = wrapped
            break
    raw_criteria = output.get("criteria")
    if not isinstance(raw_criteria, list):
        raise ContractError("模型输出缺少 criteria 数组")
    received_ids = [
        str(item.get("criterion_id", item.get("id", ""))).strip()
        for item in raw_criteria
        if isinstance(item, dict)
    ]
    if len(received_ids) != len(set(received_ids)):
        raise ContractError("模型输出包含重复 criterion_id")
    if set(received_ids) != set(expected):
        raise ContractError("模型输出的评分维度与 rubric 不一致")

    evidence_map = {item.evidence_id: item for item in evidence_catalog}
    decisions: list[CriterionDecision] = []
    used_ids: set[str] = set()
    for raw in raw_criteria:
        criterion_id = str(raw.get("criterion_id", raw.get("id", ""))).strip()
        definition = expected[criterion_id]
        max_score = float(definition["max_score"])
        try:
            score = round(float(raw["score"]), 2)
            claimed_confidence = float(raw.get("confidence", 0))
        except (KeyError, TypeError, ValueError) as exc:
            raise ContractError(f"{criterion_id}: score/confidence 不是数值") from exc
        if not 0 <= score <= max_score:
            raise ContractError(f"{criterion_id}: score 越界")

        raw_evidence_ids = raw.get("evidence_ids", [])
        if isinstance(raw_evidence_ids, str):
            raw_evidence_ids = re.split(r"[,，;；\s]+", raw_evidence_ids.strip())
        if not isinstance(raw_evidence_ids, list):
            raise ContractError(f"{criterion_id}: evidence_ids 必须是数组")
        evidence_ids = tuple(
            dict.fromkeys(
                str(item).strip() for item in raw_evidence_ids if str(item).strip()
            )
        )
        unknown = set(evidence_ids) - set(evidence_map)
        if unknown:
            raise ContractError(f"{criterion_id}: 引用了未知证据")
        if score > 0 and not evidence_ids:
            raise ContractError(f"{criterion_id}: 正分缺少证据")
        reason = re.sub(r"\s+", " ", str(raw.get("reason", ""))).strip()[:600]
        if not reason:
            raise ContractError(f"{criterion_id}: 缺少评分理由")

        if evidence_ids:
            observed_quality = sum(
                evidence_map[item].reliability for item in evidence_ids
            ) / len(evidence_ids)
            confidence = min(claimed_confidence, 0.35 + 0.65 * observed_quality, 0.94)
        else:
            confidence = min(claimed_confidence, 0.5)
        confidence = round(max(0.0, confidence), 4)
        used_ids.update(evidence_ids)
        decisions.append(
            CriterionDecision(
                criterion_id=criterion_id,
                criterion_name=str(definition["name"]),
                max_score=max_score,
                score=score,
                reason=reason,
                evidence_ids=evidence_ids,
                confidence=confidence,
            )
        )

    decisions.sort(key=lambda item: list(expected).index(item.criterion_id))
    evidence = tuple(item for item in evidence_catalog if item.evidence_id in used_ids)
    low_confidence = [
        item.criterion_name for item in decisions if item.confidence < 0.75
    ]
    review_reasons = [
        f"{name}维度置信度低于 0.75，需要教师核对证据与课程要求。"
        for name in low_confidence
    ]
    risks = output.get("risks")
    if isinstance(risks, list):
        review_reasons.extend(
            re.sub(r"\s+", " ", str(item)).strip()[:240]
            for item in risks[:3]
            if str(item).strip()
        )
    review_reasons.append("真实模型生成的结果仅为建议分，正式成绩必须由教师终审。")

    trace = GradeTrace(
        trace_id=trace_id,
        rubric_id=str(rubric["experiment_id"]),
        submission_alias=submission_alias,
        evidence=evidence,
        criteria=tuple(decisions),
        model_total_score=round(sum(item.score for item in decisions), 2),
        needs_human_review=True,
        review_reasons=tuple(dict.fromkeys(review_reasons)),
        review=ReviewDecision(status="pending", reviewer_role="teacher"),
    )
    trace.validate()
    return trace


def build_model_trace(
    parsed: dict[str, Any],
    *,
    trace_id: str,
    submission_alias: str,
    rubric: dict[str, Any],
    allow_external_images: bool = False,
    client: BaseLLMClient | None = None,
    config: LLMConfig | None = None,
) -> tuple[GradeTrace, dict[str, Any], dict[str, Any]]:
    available_images = parsed.get("images_for_vision") or []
    max_images = max(0, min(8, int(os.getenv("LABTRACE_LLM_MAX_IMAGES", "4"))))
    max_image_bytes = max(
        256 * 1024,
        min(
            12 * 1024 * 1024, int(os.getenv("LABTRACE_LLM_MAX_IMAGE_BYTES", "6291456"))
        ),
    )
    selected_images = []
    selected_image_bytes = 0
    if allow_external_images:
        for image in available_images[:max_images]:
            size = int(image.get("size_bytes", 0))
            media_type = str(image.get("media_type", ""))
            if (
                not image.get("base64")
                or media_type
                not in {"image/jpeg", "image/png", "image/gif", "image/webp"}
                or selected_image_bytes + size > max_image_bytes
            ):
                continue
            selected_images.append(image)
            selected_image_bytes += size
    external_images = bool(selected_images)
    image_evidence_id_by_source_index = {
        int(item.get("index", position)): f"i-{position:04d}"
        for position, item in enumerate(parsed.get("images") or [], start=1)
    }
    selected_image_evidence_ids = [
        image_evidence_id_by_source_index.get(
            int(image.get("index", position)),
            f"i-{position:04d}",
        )
        for position, image in enumerate(selected_images, start=1)
    ]
    observed_positions = {
        int(evidence_id.split("-", 1)[1]) for evidence_id in selected_image_evidence_ids
    }
    evidence, privacy = build_model_evidence(
        parsed,
        external_images=external_images,
        externally_observed_image_positions=observed_positions,
    )
    if not evidence:
        raise ContractError("解析结果中没有可供模型判断的证据")
    if client is None or config is None:
        client, config = _client_from_environment()

    payload = _prompt_payload(
        rubric,
        parsed.get("document_profile") or {},
        evidence,
    )
    image_boundary = (
        "教师已显式授权发送随附图片；可以直接观察这些图片，但不得识别或输出个人身份。"
        if external_images
        else "图片证据当前只有解析器提取的邻近文本，不等同于看过图片。"
    )
    system = (
        "你是高校实验报告证据化批改 Agent。必须遵守教师 rubric，不得按篇幅猜分，"
        "不得编造未出现的实验步骤、数据、图片内容或结论。每个正分都必须绑定现有证据 ID。"
        f"{image_boundary}"
        "仅输出一个严格 JSON 对象，不输出 Markdown、思考过程或额外文字。"
    )
    prompt_text = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    if external_images:
        content: list[dict[str, Any]] = [{"type": "text", "text": prompt_text}]
        for image, evidence_id in zip(
            selected_images,
            selected_image_evidence_ids,
            strict=True,
        ):
            content.extend(
                [
                    {
                        "type": "text",
                        "text": (
                            f"以下图片对应 evidence_id={evidence_id}；"
                            "可结合图像内容与邻近文本判断，但不得识别或输出个人身份。"
                        ),
                    },
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": str(image["media_type"]),
                            "data": str(image["base64"]),
                        },
                    },
                ]
            )
        user_content: str | list[dict[str, Any]] = content
    else:
        user_content = prompt_text
    messages = [{"role": "user", "content": user_content}]
    max_attempts = max(1, min(3, int(os.getenv("LABTRACE_LLM_MAX_ATTEMPTS", "3"))))
    total_input = 0
    total_output = 0
    started = time.monotonic()
    last_error: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        response = client.create_message(
            messages=messages,
            system=system,
            max_tokens=config.max_tokens,
            model=config.model,
        )
        total_input += response.input_tokens
        total_output += response.output_tokens
        try:
            output = _extract_json(response.text)
            trace = _trace_from_model_output(
                output,
                rubric=rubric,
                evidence_catalog=evidence,
                trace_id=trace_id,
                submission_alias=submission_alias,
            )
            return (
                trace,
                {
                    "adapter": "model_grading_v1",
                    "provider": (
                        "MiniMax"
                        if "minimax" in (config.effective_base_url or "").lower()
                        else config.provider_display_name
                    ),
                    "model": config.model,
                    "attempts": attempt,
                    "latency_ms": round((time.monotonic() - started) * 1000),
                    "tokens": {"input": total_input, "output": total_output},
                    "structured_output_validated": True,
                    "vision_mode": (
                        "opt_in_images_and_text"
                        if external_images
                        else "text_and_image_context"
                    ),
                    "images_sent": len(selected_images),
                },
                privacy,
            )
        except (ContractError, KeyError, TypeError, ValueError) as exc:
            last_error = exc
            if attempt >= max_attempts:
                break
            messages.extend(
                [
                    {"role": "assistant", "content": response.text[:20_000]},
                    {
                        "role": "user",
                        "content": (
                            "上一个 JSON 未通过确定性校验。"
                            f"具体错误：{re.sub(r'\\s+', ' ', str(exc))[:240]}。"
                            "请重新输出完整 JSON，"
                            "确保维度完整、分数不越界、正分均引用现有 evidence_id。"
                        ),
                    },
                ]
            )
    raise ContractError(
        f"模型输出在 {max_attempts} 次尝试后仍未通过契约校验"
    ) from last_error


async def grade_report_with_adapter(
    parsed: dict[str, Any],
    *,
    trace_id: str,
    submission_alias: str,
    rubric: dict[str, Any],
    allow_external_images: bool = False,
) -> GradingOutcome:
    status = model_runtime_status()
    if not status["configured"]:
        trace = build_demo_trace(
            parsed,
            trace_id=trace_id,
            submission_alias=submission_alias,
            rubric=rubric,
        )
        _, privacy = build_model_evidence(parsed)
        return GradingOutcome(
            trace=trace,
            mode="deterministic_demo",
            run={
                "adapter": "deterministic_rules_v1",
                "provider": "none",
                "model": "none",
                "fallback": False,
                "structured_output_validated": True,
            },
            privacy={**privacy, "policy": "local_processing_only"},
        )
    if not _claim_model_call():
        trace = build_demo_trace(
            parsed,
            trace_id=trace_id,
            submission_alias=submission_alias,
            rubric=rubric,
        )
        _, privacy = build_model_evidence(parsed)
        return GradingOutcome(
            trace=trace,
            mode="deterministic_fallback",
            run={
                "adapter": "deterministic_rules_v1",
                "provider": status["provider"],
                "model": status["model"],
                "fallback": True,
                "fallback_code": "daily_model_quota_exhausted",
                "structured_output_validated": True,
            },
            privacy={**privacy, "policy": "local_processing_only"},
        )

    timeout_seconds = max(
        15, min(180, int(os.getenv("LABTRACE_LLM_TIMEOUT_SECONDS", "90")))
    )
    try:
        trace, run, privacy = await asyncio.wait_for(
            asyncio.to_thread(
                build_model_trace,
                parsed,
                trace_id=trace_id,
                submission_alias=submission_alias,
                rubric=rubric,
                allow_external_images=allow_external_images,
            ),
            timeout=timeout_seconds,
        )
        return GradingOutcome(
            trace=trace,
            mode="model_agent",
            run={**run, "fallback": False},
            privacy=privacy,
        )
    except Exception as exc:
        trace = build_demo_trace(
            parsed,
            trace_id=trace_id,
            submission_alias=submission_alias,
            rubric=rubric,
        )
        _, privacy = build_model_evidence(parsed)
        if isinstance(exc, ContractError):
            contract_error = (
                exc.__cause__ if isinstance(exc.__cause__, ContractError) else exc
            )
            fallback_detail = re.sub(r"\s+", " ", str(contract_error)).strip()[:180]
        elif isinstance(exc, (TimeoutError, asyncio.TimeoutError)):
            fallback_detail = f"模型调用超过 {timeout_seconds} 秒"
        else:
            fallback_detail = "模型传输或运行异常"
        return GradingOutcome(
            trace=trace,
            mode="deterministic_fallback",
            run={
                "adapter": "deterministic_rules_v1",
                "provider": status["provider"],
                "model": status["model"],
                "fallback": True,
                "fallback_code": (
                    "model_timeout"
                    if isinstance(exc, (TimeoutError, asyncio.TimeoutError))
                    else f"model_{type(exc).__name__.lower()}"
                ),
                "fallback_detail": fallback_detail,
                "structured_output_validated": True,
            },
            privacy={**privacy, "policy": "local_processing_after_model_failure"},
        )
