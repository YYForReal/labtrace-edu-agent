#!/usr/bin/env python3
"""
batch_grade_and_export.py — 批量批改 + 成绩汇总到 Excel 整合脚本

功能概述：
  1. 扫描指定目录下的所有学生 docx 文件
  2. 逐一执行批改注入（引用批注、成绩评定、评语、签名+日期）
  3. 收集全部成绩数据
  4. 回填到学校成绩登记表 Excel
  5. 追加统计汇总和分数分布工作表
  6. 导出批改结果 JSON 摘要

用法：
  python batch_grade_and_export.py \
    --input-dir 学生报告目录/ \
    --output-dir 批改后/ \
    --excel 成绩登记表.xlsx \
    --config-dir 批改配置目录/ \
    --signature 签名图片.jpeg

  或在 Python 中导入：
    from batch_grade_and_export import batch_grade
"""

import argparse
import json
import os
import re
import sys
from datetime import datetime

# 添加 scripts 目录到路径
SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

from inject_grading_to_docx import inject_all
from fill_score_to_excel import (
    fill_scores_to_excel,
    append_statistics_sheet,
    extract_scores_from_grading_configs,
)


def _extract_student_info_from_filename(filename):
    """从文件名中提取学号和姓名。

    支持的文件名格式：
      - 2022150022林振法.docx
      - 2022150022_林振法.docx
      - 2022150022-林振法.docx
      - 2022150022 林振法.docx
    """
    base = os.path.splitext(filename)[0]
    m = re.match(r"(\d{10})\s*[_\-]?\s*(.+)", base)
    if m:
        return m.group(1), m.group(2).strip()
    return None, None


def _find_config_for_student(config_dir, student_id, student_name):
    """为指定学生查找批改配置文件。

    搜索策略：
      1. 精确匹配：{学号}{姓名}.json
      2. 学号匹配：文件名包含学号
      3. 姓名匹配：文件名包含姓名
    """
    if not config_dir or not os.path.isdir(config_dir):
        return None

    # 策略1: 精确匹配
    for pattern in [
        f"{student_id}{student_name}.json",
        f"{student_id}_{student_name}.json",
        f"{student_id}-{student_name}.json",
        f"{student_id} {student_name}.json",
    ]:
        path = os.path.join(config_dir, pattern)
        if os.path.exists(path):
            return path

    # 策略2: 学号匹配
    for fname in os.listdir(config_dir):
        if fname.endswith(".json") and student_id in fname:
            return os.path.join(config_dir, fname)

    # 策略3: 姓名匹配
    if student_name:
        for fname in os.listdir(config_dir):
            if fname.endswith(".json") and student_name in fname:
                return os.path.join(config_dir, fname)

    return None


def batch_grade(
    input_dir,
    output_dir,
    excel_path=None,
    config_dir=None,
    default_config=None,
    signature_path=None,
    signature_date=None,
    score_column=None,
    week_number=None,
    fill_mode="total_score",
):
    """
    批量批改学生实验报告并汇总成绩到 Excel。

    Args:
        input_dir: str — 学生 docx 文件目录
        output_dir: str — 批改后 docx 输出目录
        excel_path: str|None — 成绩登记表 Excel（为 None 则不回填）
        config_dir: str|None — 批改配置 JSON 目录（每学生一个 JSON）
        default_config: dict|None — 默认批改配置（当找不到特定学生的配置时使用）
        signature_path: str|None — 签名图片路径
        signature_date: str|None — 日期字符串
        score_column: str|int|None — 成绩列
        week_number: int|None — 周次编号
        fill_mode: str — 填充模式

    Returns:
        dict: 批量批改结果
    """
    os.makedirs(output_dir, exist_ok=True)

    # 扫描学生文件
    student_files = []
    for fname in sorted(os.listdir(input_dir)):
        if fname.lower().endswith(".docx") and not fname.startswith("~"):
            sid, name = _extract_student_info_from_filename(fname)
            if sid:
                student_files.append(
                    {
                        "filename": fname,
                        "student_id": sid,
                        "student_name": name,
                        "input_path": os.path.join(input_dir, fname),
                        "output_path": os.path.join(output_dir, fname),
                    }
                )

    print(f"扫描到 {len(student_files)} 份学生报告")

    # 逐一批改
    all_scores = []
    results = {
        "total": len(student_files),
        "success": 0,
        "failed": 0,
        "skipped": 0,
        "details": [],
        "scores": [],
    }

    for i, sf in enumerate(student_files):
        sid = sf["student_id"]
        name = sf["student_name"]
        print(f"\n[{i+1}/{len(student_files)}] 批改: {sid} {name}")

        # 查找配置
        config = None
        config_path = _find_config_for_student(config_dir, sid, name)
        if config_path:
            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    config = json.load(f)
                print(f"  配置: {os.path.basename(config_path)}")
            except Exception as e:
                print(f"  配置读取失败: {e}", file=sys.stderr)

        if config is None and default_config:
            config = dict(default_config)  # 浅拷贝
            print(f"  使用默认配置")

        if config is None:
            print(f"  跳过: 无批改配置")
            results["skipped"] += 1
            results["details"].append(
                {
                    "student_id": sid,
                    "student_name": name,
                    "status": "skipped",
                    "reason": "无批改配置",
                }
            )
            continue

        # 注入签名配置（如果命令行指定了全局签名）
        if signature_path and "signature" not in config:
            config["signature"] = {
                "image_path": signature_path,
                "date": signature_date or datetime.now().strftime("%Y年 %m 月 %d 日"),
            }

        # 确保配置中有学生信息
        config["student_id"] = sid
        config["student_name"] = name

        # 执行批改注入
        try:
            inject_result = inject_all(
                sf["input_path"],
                sf["output_path"],
                config,
            )

            # 收集成绩
            scores = config.get("scores", [])
            total_score = sum(scores) if scores else 0
            comment = config.get("comment", "")

            score_entry = {
                "student_id": sid,
                "student_name": name,
                "total_score": total_score,
                "scores": scores,
                "comment": comment,
            }
            all_scores.append(score_entry)
            results["success"] += 1
            results["details"].append(
                {
                    "student_id": sid,
                    "student_name": name,
                    "status": "success",
                    "total_score": total_score,
                    "inject_result": inject_result,
                }
            )

        except Exception as e:
            print(f"  ✗ 批改失败: {e}", file=sys.stderr)
            results["failed"] += 1
            results["details"].append(
                {
                    "student_id": sid,
                    "student_name": name,
                    "status": "failed",
                    "error": str(e),
                }
            )

    results["scores"] = all_scores

    # 保存批改结果 JSON
    results_json_path = os.path.join(output_dir, "_grading_results.json")
    with open(results_json_path, "w", encoding="utf-8") as f:
        json.dump(all_scores, f, ensure_ascii=False, indent=2)
    print(f"\n成绩数据已导出: {results_json_path}")

    # 回填到 Excel
    if excel_path and all_scores:
        excel_output = os.path.splitext(excel_path)
        excel_output_path = f"{excel_output[0]}_已填{excel_output[1]}"

        print(f"\n正在回填成绩到 Excel...")
        fill_result = fill_scores_to_excel(
            excel_path=excel_path,
            scores_data=all_scores,
            output_path=excel_output_path,
            score_column=score_column,
            week_number=week_number,
            fill_mode=fill_mode,
            add_comments=True,  # 默认添加批注说明
            auto_stats=True,  # 默认追加统计工作表
        )
        results["excel_fill"] = fill_result
        results["excel_output"] = excel_output_path

    # 打印汇总
    print(f"\n{'='*50}")
    print(f"批量批改完成")
    print(f"  总计: {results['total']} 份")
    print(f"  成功: {results['success']} 份")
    print(f"  失败: {results['failed']} 份")
    print(f"  跳过: {results['skipped']} 份")
    if all_scores:
        avg = sum(s["total_score"] for s in all_scores) / len(all_scores)
        print(f"  平均分: {avg:.1f}")

    return results


# ══════════════════════════════════════════════════════════
# CLI 入口
# ══════════════════════════════════════════════════════════

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="批量批改学生实验报告并汇总成绩到 Excel"
    )
    parser.add_argument("--input-dir", "-i", required=True, help="学生 docx 文件目录")
    parser.add_argument(
        "--output-dir", "-o", required=True, help="批改后 docx 输出目录"
    )
    parser.add_argument("--excel", "-e", help="成绩登记表 Excel 路径")
    parser.add_argument("--config-dir", "-d", help="批改配置 JSON 目录")
    parser.add_argument("--signature", "-sig", help="签名图片路径")
    parser.add_argument("--date", help='日期字符串（如 "2025年 04 月 19 日"）')
    parser.add_argument("--score-column", "-c", help="成绩列（如 S 或 19）")
    parser.add_argument("--week-number", "-w", type=int, help="周次编号")
    parser.add_argument(
        "--fill-mode",
        default="total_score",
        choices=["total_score", "week_score", "both"],
        help="填充模式",
    )

    args = parser.parse_args()

    results = batch_grade(
        input_dir=args.input_dir,
        output_dir=args.output_dir,
        excel_path=args.excel,
        config_dir=args.config_dir,
        signature_path=args.signature,
        signature_date=args.date,
        score_column=args.score_column,
        week_number=args.week_number,
        fill_mode=args.fill_mode,
    )
