#!/usr/bin/env python3
"""
LLM 响应解析脚本
从 LLM 响应中提取评分结果 JSON，进行容错处理
"""

import os
import sys
import json
import re
import argparse


def parse_grading_response(response_text, rubric):
    """
    解析 LLM 评分响应

    Args:
        response_text: LLM 响应文本
        rubric: 评分标准字典

    Returns:
        dict: GradingResult 结构
    """
    # 提取 JSON 块
    data = _extract_json(response_text)

    # 构建 max_score 映射
    max_scores = {c["id"]: c["max_score"] for c in rubric.get("criteria", [])}

    # 处理 criterion_scores
    criterion_scores = []
    for cs in data.get("criterion_scores", []):
        criterion_id = cs.get("criterion_id", "")
        max_score = max_scores.get(criterion_id, 0)
        score = cs.get("score", 0)

        # 容错：分数不超过满分
        if score > max_score and max_score > 0:
            score = max_score

        # 容错：分数不为负
        if score < 0:
            score = 0

        criterion_scores.append(
            {
                "criterion_id": criterion_id,
                "criterion_name": cs.get("criterion_name", criterion_id),
                "max_score": max_score,
                "score": score,
                "reason": cs.get("reason", ""),
            }
        )

    # 计算总分
    total_score = sum(cs["score"] for cs in criterion_scores)

    # 构建结果
    result = {
        "total_score": total_score,
        "criterion_scores": criterion_scores,
        "detailed_analysis": data.get("detailed_analysis", ""),
        "strengths": data.get("strengths", []),
        "weaknesses": data.get("weaknesses", []),
        "suggestions": data.get("suggestions", []),
        "confidence": data.get("confidence", 0.0),
        "warnings": data.get("warnings", []),
    }

    return result


def _extract_json(text):
    """从文本中提取 JSON 对象"""
    # 尝试直接解析
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # 尝试提取 ```json ... ``` 块
    match = re.search(r"```json\s*([\s\S]*?)```", text)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass

    # 尝试提取 { ... } 块
    match = re.search(r"\{[\s\S]*\}", text)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass

    raise ValueError(f"无法从响应中提取有效 JSON: {text[:200]}...")


def main():
    parser = argparse.ArgumentParser(description="解析 LLM 评分响应")
    parser.add_argument("--response", "-r", required=True, help="LLM 响应文本文件")
    parser.add_argument("--rubric", required=True, help="评分标准 JSON 文件")
    parser.add_argument("--output", "-o", help="输出 JSON 文件路径")

    args = parser.parse_args()

    with open(args.response, "r", encoding="utf-8") as f:
        response_text = f.read()

    with open(args.rubric, "r", encoding="utf-8") as f:
        rubric = json.load(f)

    try:
        result = parse_grading_response(response_text, rubric)
        output_json = json.dumps(result, ensure_ascii=False, indent=2)

        if args.output:
            with open(args.output, "w", encoding="utf-8") as f:
                f.write(output_json)
            print(f"解析完成，总分: {result['total_score']}")
        else:
            print(output_json)

    except Exception as e:
        print(f"错误: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
