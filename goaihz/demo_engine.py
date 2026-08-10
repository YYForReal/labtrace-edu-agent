"""Deterministic, evidence-grounded grading adapter for reliable live demos.

This module intentionally does not pretend to be an LLM. It exercises the real
document parser and the same evidence/review contracts as the production Agent,
while using explicit rules so the competition demo remains runnable without an
API key or network connection.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict
from pathlib import Path
from typing import Any

from app.agent.tool_registry import ToolRegistry
from goaihz.src.labtrace.contracts import (
    CriterionDecision,
    EvidenceRef,
    GradeTrace,
    ReviewDecision,
)


ROOT = Path(__file__).resolve().parent
DEFAULT_RUBRIC_PATH = ROOT / "config" / "rubrics" / "general_lab_report_v1.json"


CRITERION_RULES: dict[str, dict[str, Any]] = {
    "objective_and_principle": {
        "keywords": ("实验目标", "实验目的", "实验原理", "理论原理", "研究目标"),
        "preferred_score": 13,
        "reason": "报告明确说明实验目标和核心原理，目标与任务关系清楚，但理论推导仍可补充。",
        "confidence": 0.91,
    },
    "method_and_process": {
        "keywords": ("实验方法", "实验步骤", "实验环境", "参数设置", "操作步骤"),
        "preferred_score": 16,
        "reason": "主要步骤、环境和参数记录完整，能够复现实验主流程，少量控制变量说明仍不充分。",
        "confidence": 0.88,
    },
    "data_and_evidence": {
        "keywords": ("实验数据", "实验结果", "结果数据", "数据记录", "运行结果"),
        "preferred_score": 20,
        "reason": "报告提供重复实验数据和结果图，证据能够支撑主要完成情况，但图表标注尚不完整。",
        "confidence": 0.84,
    },
    "analysis_and_validation": {
        "keywords": ("结果分析", "误差分析", "误差来源", "结果验证", "异常分析"),
        "preferred_score": 10,
        "reason": "能够描述主要趋势并提到误差，但缺少定量不确定性、异常点解释和充分验证。",
        "confidence": 0.68,
    },
    "conclusion_and_reflection": {
        "keywords": ("实验结论", "结论与反思", "总结与反思", "实验总结", "改进方向"),
        "preferred_score": 11,
        "reason": "结论回应了主要实验目标并提出改进方向，但与前文数据的逐项引用仍可加强。",
        "confidence": 0.82,
    },
    "report_quality": {
        "keywords": ("实验报告", "图 1", "表 1", "图1", "表1"),
        "preferred_score": 4,
        "reason": "报告结构清楚、图表和单位基本规范，仍有少量图表标注与引用格式问题。",
        "confidence": 0.9,
    },
}

PROFILE_OVERRIDES: dict[str, dict[str, dict[str, Any]]] = {
    "allergen": {
        "objective_and_principle": {
            "preferred_score": 12,
            "reason": "目标明确指向过敏原蛋白 Ara h 1 的教学检测，也说明了 ELISA 原理；但对标准曲线适用条件的解释还不够完整。",
            "confidence": 0.89,
        },
        "method_and_process": {
            "preferred_score": 15,
            "reason": "样品、阴阳性对照和三次平行测定流程可定位，但关键孵育条件与移液误差控制记录不足。",
            "confidence": 0.84,
        },
        "data_and_evidence": {
            "preferred_score": 19,
            "reason": "表格、标准曲线与对照结果形成了基本证据链；图表仍缺少误差棒和检出限标注。",
            "confidence": 0.82,
        },
        "analysis_and_validation": {
            "preferred_score": 8,
            "reason": "报告描述了吸光度变化，却没有定量讨论重复性、回收率和异常值，因此必须由教师重点复核。",
            "confidence": 0.62,
        },
        "conclusion_and_reflection": {
            "preferred_score": 10,
            "reason": "结论回应了教学实验目标并提出复测建议，但不能据此作出任何临床诊断。",
            "confidence": 0.8,
        },
        "report_quality": {
            "preferred_score": 4,
            "reason": "结构与单位基本规范，教学用途和非诊断边界标注清楚。",
            "confidence": 0.9,
        },
    },
    "game_dev": {
        "objective_and_principle": {
            "preferred_score": 13,
            "reason": "实验目标围绕 Unity 抛射、碰撞和摄像机跟随展开，核心组件关系说明清楚。",
            "confidence": 0.9,
        },
        "method_and_process": {
            "preferred_score": 18,
            "reason": "环境、组件参数、脚本步骤和验证流程完整，能够复现主要玩法闭环。",
            "confidence": 0.9,
        },
        "data_and_evidence": {
            "preferred_score": 21,
            "reason": "运行数据、测试场景和示意图能够支撑功能完成情况；仍可增加帧时间分布与失败日志。",
            "confidence": 0.86,
        },
        "analysis_and_validation": {
            "preferred_score": 9,
            "reason": "报告识别了高速穿透和镜头抖动风险，但缺少边界场景的批量测试与性能量化。",
            "confidence": 0.66,
        },
        "conclusion_and_reflection": {
            "preferred_score": 10,
            "reason": "总结对应实验目标并给出对象池与自动化测试方向，反思仍可关联更多测试证据。",
            "confidence": 0.81,
        },
        "report_quality": {
            "preferred_score": 4,
            "reason": "章节、参数与图表引用较规范，示例数据来源边界标注清楚。",
            "confidence": 0.9,
        },
    },
}


def _detect_profile(parsed: dict[str, Any]) -> str:
    text = "\n".join(
        str(item.get("text", "")) for item in parsed.get("paragraphs") or []
    )
    if any(keyword in text for keyword in ("Ara h 1", "ELISA", "过敏原")):
        return "allergen"
    if any(keyword in text for keyword in ("Unity", "Rigidbody", "碰撞检测")):
        return "game_dev"
    return "general"


def load_demo_rubric(path: Path = DEFAULT_RUBRIC_PATH) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def parse_report(file_path: str) -> dict[str, Any]:
    registry = ToolRegistry(config={"rubrics_dir": str(DEFAULT_RUBRIC_PATH.parent)})
    result = registry._tool_parse_document(
        {"file_path": file_path, "extract_images": True}
    )
    if result.get("error"):
        raise ValueError(str(result["error"]))
    return result


def _normalized_paragraphs(parsed: dict[str, Any]) -> list[dict[str, Any]]:
    paragraphs = []
    for index, item in enumerate(parsed.get("paragraphs") or []):
        text = str(item.get("text", "")).strip()
        if text:
            paragraphs.append(
                {
                    "index": index,
                    "text": text,
                    "style": str(item.get("style", "")),
                    "level": item.get("level"),
                }
            )
    return paragraphs


def _find_paragraph(
    paragraphs: list[dict[str, Any]], keywords: tuple[str, ...]
) -> dict[str, Any] | None:
    for item in paragraphs:
        if item.get("level") is not None:
            continue
        if any(
            item["text"].startswith(f"{keyword}：")
            or item["text"].startswith(f"{keyword}:")
            for keyword in keywords
        ):
            return item
    for item in paragraphs:
        if item.get("level") is not None:
            continue
        if any(keyword in item["text"] for keyword in keywords):
            return item
    return None


def _excerpt(text: str, limit: int = 120) -> str:
    compact = re.sub(r"\s+", " ", text).strip()
    return compact if len(compact) <= limit else compact[: limit - 1] + "…"


def _table_evidence(parsed: dict[str, Any]) -> tuple[str, str] | None:
    tables = parsed.get("tables") or []
    if not tables:
        return None
    target = max(tables, key=lambda item: int(item.get("rows", 0)))
    data = target.get("data") or []
    preview = "；".join(" | ".join(str(cell) for cell in row) for row in data[:3])
    return f"table:{int(target.get('index', 0)) + 1}", _excerpt(preview)


def _image_evidence(parsed: dict[str, Any]) -> tuple[str, str] | None:
    images = parsed.get("images") or []
    if not images:
        return None
    target = images[0]
    # Parser indices are zero-based; locators are teacher-facing and one-based.
    index = int(target.get("index", 0)) + 1
    context = target.get("context") or target.get("description") or "报告内嵌结果图"
    return f"image:{index}", _excerpt(str(context))


def build_demo_trace(
    parsed: dict[str, Any],
    *,
    trace_id: str,
    submission_alias: str,
    rubric: dict[str, Any] | None = None,
) -> GradeTrace:
    rubric = rubric or load_demo_rubric()
    paragraphs = _normalized_paragraphs(parsed)
    evidence: list[EvidenceRef] = []
    decisions: list[CriterionDecision] = []
    evidence_counter = 1
    evidence_by_locator: dict[tuple[str, str], str] = {}
    profile_overrides = PROFILE_OVERRIDES.get(_detect_profile(parsed), {})

    def add_evidence(kind: str, locator: str, text: str, reliability: float) -> str:
        nonlocal evidence_counter
        evidence_key = (kind, locator)
        if evidence_key in evidence_by_locator:
            return evidence_by_locator[evidence_key]

        prefix = {"paragraph": "p", "table": "t", "chart": "i"}.get(kind, "ev")
        try:
            source_index = int(locator.rsplit(":", 1)[-1])
        except (TypeError, ValueError):
            source_index = evidence_counter
        evidence_id = f"{prefix}-{source_index:04d}"
        evidence_counter += 1
        evidence_by_locator[evidence_key] = evidence_id
        evidence.append(
            EvidenceRef(
                evidence_id=evidence_id,
                kind=kind,
                source_file=Path(str(parsed.get("file_path", "uploaded-report"))).name,
                locator=locator,
                excerpt=_excerpt(text),
                reliability=reliability,
                verification="parser_observed",
            )
        )
        return evidence_id

    table_item = _table_evidence(parsed)
    image_item = _image_evidence(parsed)

    for criterion in rubric.get("criteria", []):
        criterion_id = str(criterion["id"])
        rule = {
            **CRITERION_RULES.get(criterion_id, {}),
            **profile_overrides.get(criterion_id, {}),
        }
        paragraph = _find_paragraph(paragraphs, tuple(rule.get("keywords", ())))
        evidence_ids: list[str] = []

        if paragraph:
            evidence_ids.append(
                add_evidence(
                    "paragraph",
                    f"paragraph:{paragraph['index'] + 1}",
                    paragraph["text"],
                    0.96,
                )
            )

        if criterion_id in {"method_and_process", "data_and_evidence"} and table_item:
            locator, text = table_item
            evidence_ids.append(add_evidence("table", locator, text, 0.95))

        if criterion_id == "data_and_evidence" and image_item:
            locator, text = image_item
            evidence_ids.append(add_evidence("chart", locator, text, 0.8))

        max_score = float(criterion["max_score"])
        if evidence_ids:
            score = min(float(rule.get("preferred_score", max_score * 0.75)), max_score)
            reason = str(rule.get("reason", "报告提供了与该维度相关的可定位证据。"))
            confidence = float(rule.get("confidence", 0.78))
        else:
            score = 0
            reason = "未在当前材料中找到足以支撑该维度得分的可定位证据。"
            confidence = 0.45

        decisions.append(
            CriterionDecision(
                criterion_id=criterion_id,
                criterion_name=str(criterion["name"]),
                max_score=max_score,
                score=score,
                reason=reason,
                evidence_ids=tuple(evidence_ids),
                confidence=confidence,
            )
        )

    low_confidence = [
        item.criterion_name for item in decisions if item.confidence < 0.75
    ]
    review_reasons = [
        f"{name}维度置信度低于 0.75，需要教师确认课程是否要求更严格的定量验证。"
        for name in low_confidence
    ]
    if not review_reasons:
        review_reasons = ["正式成绩发布前由教师进行最终确认。"]

    trace = GradeTrace(
        trace_id=trace_id,
        rubric_id=str(rubric["experiment_id"]),
        submission_alias=submission_alias,
        evidence=tuple(evidence),
        criteria=tuple(decisions),
        model_total_score=sum(item.score for item in decisions),
        needs_human_review=bool(low_confidence),
        review_reasons=tuple(review_reasons),
        review=ReviewDecision(status="pending", reviewer_role="teacher"),
    )
    trace.validate()
    return trace


def build_learning_feedback(trace: GradeTrace) -> dict[str, Any]:
    weakest = sorted(
        trace.criteria,
        key=lambda item: (item.score / item.max_score, item.confidence),
    )[:2]
    return {
        "student_focus": [
            {
                "criterion_id": item.criterion_id,
                "criterion_name": item.criterion_name,
                "score_rate": round(item.score / item.max_score, 4),
                "next_action": _next_action(item.criterion_id),
            }
            for item in weakest
        ],
        "message": "建议先完成最薄弱维度的一次针对性修订，再重新提交证据；该建议由教师确认后反馈给学生。",
    }


def _next_action(criterion_id: str) -> str:
    actions = {
        "objective_and_principle": "补充一段“原理如何支撑本次实验步骤”的解释。",
        "method_and_process": "列出环境、参数、控制变量和可复现步骤。",
        "data_and_evidence": "为每个主要结论补充对应数据、图表或运行结果。",
        "analysis_and_validation": "增加定量误差、不确定性或对照验证，并解释异常点。",
        "conclusion_and_reflection": "让每条结论回应实验目标并引用前文证据。",
        "report_quality": "检查图表标题、单位、正文引用和引用来源。",
    }
    return actions.get(criterion_id, "根据教师批注补充可验证证据。")


def trace_payload(trace: GradeTrace) -> dict[str, Any]:
    payload = trace.to_dict()
    payload["criteria"] = [asdict(item) for item in trace.criteria]
    payload["evidence"] = [asdict(item) for item in trace.evidence]
    payload["review"] = asdict(trace.review)
    return payload
