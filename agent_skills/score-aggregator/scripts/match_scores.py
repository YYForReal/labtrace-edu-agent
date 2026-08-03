#!/usr/bin/env python3
"""
成绩匹配脚本
将评分结果与学生名单进行左连接匹配
"""

import sys
import json
import os
import re
import argparse

try:
    import pandas as pd

    PANDAS_AVAILABLE = True
except ImportError:
    PANDAS_AVAILABLE = False


def match_scores(roster_path, results_dir):
    """
    匹配学生名单和评分结果

    Args:
        roster_path: 学生名单文件路径（Excel/CSV）
        results_dir: 评分结果 JSON 文件目录

    Returns:
        dict: 匹配后的数据
    """
    if not PANDAS_AVAILABLE:
        raise ImportError("请安装 pandas: pip install pandas openpyxl")

    # 读取学生名单
    if roster_path.endswith(".xlsx") or roster_path.endswith(".xls"):
        student_df = pd.read_excel(roster_path)
    elif roster_path.endswith(".csv"):
        student_df = pd.read_csv(roster_path, encoding="utf-8-sig")
    else:
        raise ValueError(f"不支持的名单格式: {roster_path}")

    # 标准化列名
    student_df.columns = student_df.columns.str.strip()

    # 确保学号为字符串
    if "学号" in student_df.columns:
        student_df["学号"] = student_df["学号"].astype(str).str.strip()

    # 读取评分结果
    results = []
    if os.path.isdir(results_dir):
        for filename in os.listdir(results_dir):
            if filename.endswith(".json"):
                filepath = os.path.join(results_dir, filename)
                with open(filepath, "r", encoding="utf-8") as f:
                    result = json.load(f)
                    results.append(result)
    elif os.path.isfile(results_dir):
        with open(results_dir, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, list):
                results = data
            else:
                results = [data]

    # 构建成绩 DataFrame
    result_data = []
    for r in results:
        result_data.append(
            {
                "学号": str(r.get("student_id", "")).strip(),
                "姓名_graded": r.get("student_name", ""),
                "总分": r.get("total_score", 0),
                "状态": "已批改",
                "置信度": r.get("confidence", 0),
            }
        )

    result_df = (
        pd.DataFrame(result_data)
        if result_data
        else pd.DataFrame(columns=["学号", "姓名_graded", "总分", "状态", "置信度"])
    )

    if "学号" in student_df.columns:
        result_df["学号"] = result_df["学号"].astype(str).str.strip()

        merged = student_df.merge(
            result_df, on="学号", how="left", suffixes=("", "_result")
        )

        if "状态" not in merged.columns and "状态_result" in merged.columns:
            merged.rename(columns={"状态_result": "状态"}, inplace=True)

        merged["状态"] = merged["状态"].fillna("未提交")
        merged["总分"] = merged["总分"].fillna(0)
    else:
        merged = result_df

    # 转换为输出格式
    records = merged.to_dict("records")

    matched = [r for r in records if r.get("状态") == "已批改"]
    unmatched = [r for r in records if r.get("状态") == "未提交"]

    return {
        "all_records": records,
        "matched_count": len(matched),
        "unmatched_count": len(unmatched),
        "total_count": len(records),
    }


def main():
    parser = argparse.ArgumentParser(description="匹配学生成绩")
    parser.add_argument("--roster", "-r", required=True, help="学生名单文件")
    parser.add_argument("--results", required=True, help="评分结果 JSON 文件或目录")
    parser.add_argument("--output", "-o", help="输出 JSON 文件")

    args = parser.parse_args()

    try:
        result = match_scores(args.roster, args.results)
        output_json = json.dumps(result, ensure_ascii=False, indent=2, default=str)

        if args.output:
            with open(args.output, "w", encoding="utf-8") as f:
                f.write(output_json)
            print(f"匹配完成: {result['matched_count']}/{result['total_count']} 已匹配")
        else:
            print(output_json)

    except Exception as e:
        print(f"错误: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
