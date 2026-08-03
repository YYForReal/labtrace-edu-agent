#!/usr/bin/env python3
"""
评分校验脚本
检查评分结果的合法性和一致性
"""

import sys
import json
import argparse


def validate_scores(grading_result, rubric):
    """
    校验评分结果

    Args:
        grading_result: 评分结果字典
        rubric: 评分标准字典

    Returns:
        dict: {"valid": bool, "errors": list, "warnings": list}
    """
    errors = []
    warnings = []

    max_scores = {c["id"]: c["max_score"] for c in rubric.get("criteria", [])}
    total_max = rubric.get("total_score", 100)

    # 1. 检查每项分数范围
    calculated_total = 0
    for cs in grading_result.get("criterion_scores", []):
        cid = cs.get("criterion_id", "")
        score = cs.get("score", 0)
        max_score = cs.get("max_score", max_scores.get(cid, 0))

        if score < 0:
            errors.append(f"评分项 {cid} 分数为负: {score}")

        if max_score > 0 and score > max_score:
            errors.append(f"评分项 {cid} 分数 {score} 超过满分 {max_score}")

        if not cs.get("reason"):
            warnings.append(f"评分项 {cid} 缺少评分理由")

        calculated_total += score

    # 2. 检查总分一致性
    reported_total = grading_result.get("total_score", 0)
    if abs(calculated_total - reported_total) > 0.01:
        errors.append(
            f"总分不一致: 报告总分 {reported_total}, 计算总分 {calculated_total}"
        )

    # 3. 检查总分不超过满分
    if calculated_total > total_max:
        errors.append(f"总分 {calculated_total} 超过满分 {total_max}")

    # 4. 检查置信度
    confidence = grading_result.get("confidence", 0)
    if confidence < 0 or confidence > 1:
        errors.append(f"置信度不在 0-1 范围: {confidence}")

    if confidence < 0.6:
        warnings.append(f"置信度较低 ({confidence})，建议人工复核")

    # 5. 检查评分项完整性
    rubric_criteria_ids = set(c["id"] for c in rubric.get("criteria", []))
    result_criteria_ids = set(
        cs.get("criterion_id", "") for cs in grading_result.get("criterion_scores", [])
    )

    missing = rubric_criteria_ids - result_criteria_ids
    if missing:
        errors.append(f"缺少评分项: {missing}")

    extra = result_criteria_ids - rubric_criteria_ids
    if extra:
        warnings.append(f"包含未知评分项: {extra}")

    # 6. 检查必要字段
    if not grading_result.get("detailed_analysis"):
        warnings.append("缺少详细分析")

    if not grading_result.get("strengths"):
        warnings.append("缺少优点列表")

    return {
        "valid": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
        "calculated_total": calculated_total,
    }


def main():
    parser = argparse.ArgumentParser(description="校验评分结果")
    parser.add_argument("--result", "-r", required=True, help="评分结果 JSON 文件")
    parser.add_argument("--rubric", required=True, help="评分标准 JSON 文件")

    args = parser.parse_args()

    with open(args.result, "r", encoding="utf-8") as f:
        grading_result = json.load(f)

    with open(args.rubric, "r", encoding="utf-8") as f:
        rubric = json.load(f)

    validation = validate_scores(grading_result, rubric)

    print(json.dumps(validation, ensure_ascii=False, indent=2))

    if not validation["valid"]:
        print("\n校验失败！", file=sys.stderr)
        for error in validation["errors"]:
            print(f"  错误: {error}", file=sys.stderr)
        sys.exit(1)
    else:
        print("\n校验通过！")
        for warning in validation["warnings"]:
            print(f"  警告: {warning}")


if __name__ == "__main__":
    main()
