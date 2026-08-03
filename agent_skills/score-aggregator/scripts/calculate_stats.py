#!/usr/bin/env python3
"""
统计计算脚本
计算成绩统计指标（均分、最高、最低、中位数、标准差、五档分布）
"""

import sys
import json
import math
import argparse


def calculate_stats(
    records,
    pass_threshold=60,
    excellent_threshold=90,
    good_threshold=80,
    fair_threshold=70,
):
    """
    计算成绩统计数据

    Args:
        records: 成绩记录列表
        pass_threshold: 及格线
        excellent_threshold: 优秀线
        good_threshold: 良好线
        fair_threshold: 中等线

    Returns:
        dict: 统计结果
    """
    all_records = (
        records if isinstance(records, list) else records.get("all_records", [])
    )

    total_students = len(all_records)

    # 已提交且有成绩的学生
    graded = [
        r for r in all_records if r.get("状态") == "已批改" and r.get("总分", 0) > 0
    ]
    scores = [r.get("总分", 0) for r in graded]

    submitted = len(graded)

    if not scores:
        return {
            "total_students": total_students,
            "submitted_students": 0,
            "graded_students": 0,
            "average_score": 0,
            "max_score": 0,
            "min_score": 0,
            "median_score": 0,
            "std_deviation": 0,
            "pass_rate": 0,
            "excellent_rate": 0,
            "good_rate": 0,
            "fair_rate": 0,
            "poor_rate": 0,
            "score_distribution": {
                "90-100": 0,
                "80-89": 0,
                "70-79": 0,
                "60-69": 0,
                "0-59": 0,
            },
        }

    # 基本统计
    n = len(scores)
    avg = sum(scores) / n
    max_s = max(scores)
    min_s = min(scores)

    sorted_scores = sorted(scores)
    if n % 2 == 0:
        median = (sorted_scores[n // 2 - 1] + sorted_scores[n // 2]) / 2
    else:
        median = sorted_scores[n // 2]

    # 标准差
    if n > 1:
        variance = sum((s - avg) ** 2 for s in scores) / (n - 1)
        std_dev = math.sqrt(variance)
    else:
        std_dev = 0

    # 各等级统计
    excellent = sum(1 for s in scores if s >= excellent_threshold)
    good = sum(1 for s in scores if good_threshold <= s < excellent_threshold)
    fair = sum(1 for s in scores if fair_threshold <= s < good_threshold)
    passed = sum(1 for s in scores if s >= pass_threshold)
    poor = sum(1 for s in scores if s < fair_threshold)

    # 五档分布
    distribution = {
        "90-100": sum(1 for s in scores if 90 <= s <= 100),
        "80-89": sum(1 for s in scores if 80 <= s < 90),
        "70-79": sum(1 for s in scores if 70 <= s < 80),
        "60-69": sum(1 for s in scores if 60 <= s < 70),
        "0-59": sum(1 for s in scores if s < 60),
    }

    return {
        "total_students": total_students,
        "submitted_students": submitted,
        "graded_students": submitted,
        "average_score": round(avg, 2),
        "max_score": max_s,
        "min_score": min_s,
        "median_score": round(median, 2),
        "std_deviation": round(std_dev, 2),
        "pass_rate": round(passed / n * 100, 2),
        "excellent_rate": round(excellent / n * 100, 2),
        "good_rate": round(good / n * 100, 2),
        "fair_rate": round(fair / n * 100, 2),
        "poor_rate": round(poor / n * 100, 2),
        "score_distribution": distribution,
    }


def main():
    parser = argparse.ArgumentParser(description="计算成绩统计")
    parser.add_argument("--input", "-i", required=True, help="匹配后的成绩 JSON")
    parser.add_argument("--output", "-o", help="输出统计 JSON")

    args = parser.parse_args()

    with open(args.input, "r", encoding="utf-8") as f:
        data = json.load(f)

    stats = calculate_stats(data)
    output_json = json.dumps(stats, ensure_ascii=False, indent=2)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(output_json)
        print(
            f"统计完成: 平均分 {stats['average_score']}, 及格率 {stats['pass_rate']}%"
        )
    else:
        print(output_json)


if __name__ == "__main__":
    main()
