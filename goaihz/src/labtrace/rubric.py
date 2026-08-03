"""Validation and normalization for teacher-provided grading rubrics."""

from __future__ import annotations

import json
import re
from copy import deepcopy
from typing import Any


class RubricError(ValueError):
    """Raised when a rubric cannot be used safely by the grading pipeline."""


_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{1,63}$")
_MAX_RUBRIC_BYTES = 256 * 1024


def load_rubric_json(payload: bytes) -> dict[str, Any]:
    if not payload:
        raise RubricError("评分标准文件为空")
    if len(payload) > _MAX_RUBRIC_BYTES:
        raise RubricError("评分标准文件不能超过 256 KB")
    try:
        raw = json.loads(payload.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RubricError("评分标准必须是 UTF-8 编码的有效 JSON") from exc
    return validate_rubric(raw)


def validate_rubric(raw: Any) -> dict[str, Any]:
    """Return a bounded, JSON-safe rubric accepted by both grading adapters."""
    if not isinstance(raw, dict):
        raise RubricError("评分标准根节点必须是 JSON 对象")

    experiment_id = str(raw.get("experiment_id", "")).strip()
    experiment_name = str(raw.get("experiment_name", "")).strip()
    description = str(raw.get("description", "")).strip()
    criteria = raw.get("criteria")

    if not _ID_PATTERN.fullmatch(experiment_id):
        raise RubricError(
            "experiment_id 必须以字母或数字开头，仅包含字母、数字、下划线或连字符"
        )
    if not 2 <= len(experiment_name) <= 100:
        raise RubricError("experiment_name 长度必须为 2–100 个字符")
    if len(description) > 1_000:
        raise RubricError("description 不能超过 1000 个字符")
    if not isinstance(criteria, list) or not 2 <= len(criteria) <= 12:
        raise RubricError("criteria 必须包含 2–12 个评分维度")

    normalized_criteria: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for index, item in enumerate(criteria, start=1):
        if not isinstance(item, dict):
            raise RubricError(f"第 {index} 个评分维度必须是 JSON 对象")

        criterion_id = str(item.get("id", "")).strip()
        name = str(item.get("name", "")).strip()
        item_description = str(item.get("description", "")).strip()
        if not _ID_PATTERN.fullmatch(criterion_id):
            raise RubricError(
                f"第 {index} 个维度 id 必须以字母或数字开头，仅包含字母、数字、下划线或连字符"
            )
        if criterion_id in seen_ids:
            raise RubricError(f"评分维度 id 重复：{criterion_id}")
        seen_ids.add(criterion_id)
        if not 1 <= len(name) <= 80:
            raise RubricError(f"{criterion_id} 的 name 长度必须为 1–80 个字符")
        if not 1 <= len(item_description) <= 800:
            raise RubricError(f"{criterion_id} 必须提供不超过 800 字的 description")

        try:
            max_score = float(item["max_score"])
        except (KeyError, TypeError, ValueError) as exc:
            raise RubricError(f"{criterion_id} 必须提供数值 max_score") from exc
        if not 0 < max_score <= 100:
            raise RubricError(f"{criterion_id} 的 max_score 必须位于 0–100")

        rules = item.get("rules", [])
        if rules is None:
            rules = []
        if not isinstance(rules, list) or len(rules) > 12:
            raise RubricError(f"{criterion_id} 的 rules 必须是至多 12 项的数组")
        normalized_rules = []
        for rule_index, rule in enumerate(rules, start=1):
            if not isinstance(rule, dict):
                raise RubricError(
                    f"{criterion_id} 的第 {rule_index} 条规则必须是 JSON 对象"
                )
            condition = str(rule.get("condition", "")).strip()
            reason = str(rule.get("reason", "")).strip()
            if not 1 <= len(condition) <= 800:
                raise RubricError(
                    f"{criterion_id} 的第 {rule_index} 条规则缺少有效 condition"
                )
            try:
                score = float(rule["score"])
            except (KeyError, TypeError, ValueError) as exc:
                raise RubricError(
                    f"{criterion_id} 的第 {rule_index} 条规则缺少数值 score"
                ) from exc
            if not 0 <= score <= max_score:
                raise RubricError(f"{criterion_id} 的第 {rule_index} 条规则分数越界")
            normalized_rules.append(
                {
                    "condition": condition,
                    "score": score,
                    "reason": reason[:300],
                }
            )

        normalized_criteria.append(
            {
                "id": criterion_id,
                "name": name,
                "max_score": max_score,
                "weight": 0.0,
                "description": item_description,
                "rules": normalized_rules,
            }
        )

    calculated_total = round(
        sum(float(item["max_score"]) for item in normalized_criteria), 6
    )
    declared_total = raw.get("total_score", calculated_total)
    try:
        total_score = float(declared_total)
    except (TypeError, ValueError) as exc:
        raise RubricError("total_score 必须是数值") from exc
    if not 1 <= total_score <= 200:
        raise RubricError("total_score 必须位于 1–200")
    if abs(calculated_total - total_score) > 0.01:
        raise RubricError(
            f"各维度满分合计为 {calculated_total:g}，与 total_score={total_score:g} 不一致"
        )

    for item in normalized_criteria:
        item["weight"] = round(float(item["max_score"]) / total_score, 6)

    result = {
        "experiment_id": experiment_id,
        "experiment_name": experiment_name,
        "total_score": total_score,
        "description": description,
        "criteria": normalized_criteria,
    }
    for optional_key in ("reference_implementation", "few_shot_examples"):
        if optional_key in raw:
            # These fields are useful prompt context, but bound their serialized size.
            optional_value = deepcopy(raw[optional_key])
            serialized = json.dumps(optional_value, ensure_ascii=False)
            if len(serialized) > 20_000:
                raise RubricError(f"{optional_key} 序列化后不能超过 20000 个字符")
            result[optional_key] = optional_value
    return result


def rubric_summary(rubric: dict[str, Any], *, customized: bool) -> dict[str, Any]:
    return {
        "experiment_id": str(rubric["experiment_id"]),
        "experiment_name": str(rubric["experiment_name"]),
        "total_score": float(rubric["total_score"]),
        "criterion_count": len(rubric.get("criteria") or []),
        "source": "teacher_upload" if customized else "built_in",
    }
