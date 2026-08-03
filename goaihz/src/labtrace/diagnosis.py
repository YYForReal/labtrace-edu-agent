"""Deterministic class-level diagnosis built from reviewed criterion scores."""

from __future__ import annotations

from collections import defaultdict
from statistics import mean
from typing import Any, Iterable


def _teacher_action(criterion_id: str, average_rate: float) -> str:
    action_map = {
        "objective_and_principle": "用概念图或反例重新连接实验目标、关键原理与操作任务。",
        "method_and_process": "补充可复现实验记录模板，课堂示范参数、环境和关键步骤的写法。",
        "data_and_evidence": "安排一次证据整理练习，要求学生把声明逐项关联到数据、图表或运行结果。",
        "analysis_and_validation": "用同一组数据示范“描述结果、解释原因、验证结论、讨论误差”的差异。",
        "conclusion_and_reflection": "提供结论检查表，要求每条结论回应目标并引用前文证据。",
        "report_quality": "集中讲解图表编号、单位、引用和学术表达的最低规范。",
    }
    base = action_map.get(criterion_id, "针对该维度设计讲评案例和一次短练习。")
    if average_rate < 0.6:
        return f"优先干预：{base}"
    return f"巩固提升：{base}"


def build_class_diagnosis(
    records: Iterable[dict[str, Any]],
    *,
    weakness_threshold: float = 0.75,
    pass_threshold: float = 0.6,
) -> dict[str, Any]:
    """Aggregate teacher-reviewed grading records into an auditable diagnosis."""
    buckets: dict[str, list[dict[str, Any]]] = defaultdict(list)
    record_count = 0
    record_totals: list[float] = []

    for record in records:
        record_count += 1
        record_score = 0.0
        record_max = 0.0
        for item in record.get("criterion_scores", []):
            max_score = float(item.get("max_score", 0))
            score = float(item.get("score", 0))
            if max_score <= 0 or not 0 <= score <= max_score:
                raise ValueError(f"invalid criterion score: {item}")
            record_score += score
            record_max += max_score
            buckets[str(item["criterion_id"])].append(
                {
                    "name": str(item.get("criterion_name", item["criterion_id"])),
                    "rate": score / max_score,
                }
            )
        if record_max:
            record_totals.append(record_score / record_max * 100)

    summaries = []
    for criterion_id, items in buckets.items():
        rates = [item["rate"] for item in items]
        average_rate = mean(rates)
        below_pass = sum(rate < pass_threshold for rate in rates)
        summaries.append(
            {
                "criterion_id": criterion_id,
                "criterion_name": items[0]["name"],
                "sample_size": len(rates),
                "average_rate": round(average_rate, 4),
                "below_pass_count": below_pass,
                "below_pass_rate": round(below_pass / len(rates), 4),
                "is_weakness": average_rate < weakness_threshold,
                "teacher_action": _teacher_action(criterion_id, average_rate),
            }
        )

    summaries.sort(key=lambda item: (item["average_rate"], -item["sample_size"]))
    weaknesses = [item for item in summaries if item["is_weakness"]]

    return {
        "record_count": record_count,
        "class_average": round(mean(record_totals), 1) if record_totals else 0,
        "criterion_count": len(summaries),
        "weakness_threshold": weakness_threshold,
        "top_weaknesses": weaknesses[:3],
        "all_criteria": summaries,
        "boundary": "该诊断仅聚合已复核成绩，用于辅助备课和讲评，不替代教师学情判断。",
    }
