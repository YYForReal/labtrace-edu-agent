#!/usr/bin/env python3
"""
学生信息提取脚本
从文件名中提取学号和姓名
"""

import os
import sys
import re
import json
import argparse


def extract_student_info(filename):
    """
    从文件名中提取学生信息

    支持的格式：
    - 2024010001张三.doc
    - 2024010001_张三.doc
    - 2024010001 张三.doc
    - 2024010001-张三.doc
    - 张三_2024010001.doc

    Args:
        filename: 文件名（含或不含路径）

    Returns:
        dict: {"student_id": "xxx", "name": "xxx"} 或 None
    """
    basename = os.path.basename(filename)
    name_without_ext = os.path.splitext(basename)[0]

    # 清理文件名中的常见前后缀
    cleaned = name_without_ext.strip()
    cleaned = re.sub(r"[_\-]?(批改|graded|reviewed|已批)", "", cleaned)

    # 模式1: 10位学号 + 中文姓名（无分隔符）
    match = re.search(r"(\d{10})([\u4e00-\u9fff]{2,4})", cleaned)
    if match:
        return {"student_id": match.group(1), "name": match.group(2)}

    # 模式2: 学号 + 分隔符 + 姓名
    match = re.search(r"(\d{8,12})[_\s\-]([\u4e00-\u9fff]{2,4})", cleaned)
    if match:
        return {"student_id": match.group(1), "name": match.group(2)}

    # 模式3: 姓名 + 分隔符 + 学号
    match = re.search(r"([\u4e00-\u9fff]{2,4})[_\s\-](\d{8,12})", cleaned)
    if match:
        return {"student_id": match.group(2), "name": match.group(1)}

    # 模式4: 仅学号
    match = re.search(r"(\d{10})", cleaned)
    if match:
        return {"student_id": match.group(1), "name": ""}

    # 模式5: 仅中文姓名
    match = re.search(r"([\u4e00-\u9fff]{2,4})", cleaned)
    if match:
        return {"student_id": "", "name": match.group(1)}

    return None


def batch_extract(directory, extensions=None):
    """
    批量提取目录下所有文件的学生信息

    Args:
        directory: 目录路径
        extensions: 文件扩展名列表

    Returns:
        list: 学生信息列表
    """
    if extensions is None:
        extensions = [".doc", ".docx", ".pdf"]

    results = []

    for filename in sorted(os.listdir(directory)):
        ext = os.path.splitext(filename)[1].lower()
        if ext in extensions:
            info = extract_student_info(filename)
            results.append({"filename": filename, "student_info": info})

    return results


def main():
    parser = argparse.ArgumentParser(description="从文件名提取学生信息")
    parser.add_argument("--filename", "-f", help="单个文件名")
    parser.add_argument("--directory", "-d", help="批量提取目录")
    parser.add_argument("--output", "-o", help="输出 JSON 文件")

    args = parser.parse_args()

    if args.filename:
        result = extract_student_info(args.filename)
        print(json.dumps(result, ensure_ascii=False, indent=2))

    elif args.directory:
        results = batch_extract(args.directory)
        output_json = json.dumps(results, ensure_ascii=False, indent=2)

        if args.output:
            with open(args.output, "w", encoding="utf-8") as f:
                f.write(output_json)
            print(f"提取完成，共 {len(results)} 个文件")
        else:
            print(output_json)

    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
