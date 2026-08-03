#!/usr/bin/env python3
"""
文档转换脚本 - 将 .doc 文件转换为 .docx 格式

使用系统 LibreOffice 的 headless 模式进行转换。
"""

import logging
import os
import sys
import subprocess
import argparse
import platform

logger = logging.getLogger(__name__)


def find_soffice():
    """查找 LibreOffice 可执行文件路径"""
    system = platform.system()

    if system == "Darwin":  # macOS
        paths = [
            "/Applications/LibreOffice.app/Contents/MacOS/soffice",
            "/usr/local/bin/soffice",
            "/opt/homebrew/bin/soffice",
        ]
    elif system == "Linux":
        paths = [
            "/usr/bin/soffice",
            "/usr/bin/libreoffice",
            "/usr/local/bin/soffice",
        ]
    elif system == "Windows":
        paths = [
            r"C:\Program Files\LibreOffice\program\soffice.exe",
            r"C:\Program Files (x86)\LibreOffice\program\soffice.exe",
        ]
    else:
        paths = []

    # 先尝试 which/where
    try:
        result = subprocess.run(
            ["which", "soffice"] if system != "Windows" else ["where", "soffice"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip().split("\n")[0]
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass

    # 尝试预设路径
    for path in paths:
        if os.path.isfile(path):
            return path

    return None


def convert_doc_to_docx(input_path, output_dir=None):
    """
    将 .doc 文件转换为 .docx

    Args:
        input_path: 输入 .doc 文件路径
        output_dir: 输出目录（默认与输入文件同目录）

    Returns:
        str: 转换后的 .docx 文件路径
    """
    if not os.path.isfile(input_path):
        raise FileNotFoundError(f"文件不存在: {input_path}")

    if output_dir is None:
        output_dir = os.path.dirname(os.path.abspath(input_path))

    os.makedirs(output_dir, exist_ok=True)

    soffice_path = find_soffice()
    if soffice_path is None:
        raise EnvironmentError(
            "未找到 LibreOffice。请安装 LibreOffice：\n"
            "  macOS: brew install --cask libreoffice\n"
            "  Linux: sudo apt install libreoffice\n"
            "  Windows: https://www.libreoffice.org/download/"
        )

    cmd = [
        soffice_path,
        "--headless",
        "--convert-to",
        "docx",
        "--outdir",
        output_dir,
        os.path.abspath(input_path),
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        if result.returncode != 0:
            raise RuntimeError(f"转换失败: {result.stderr}")
    except subprocess.TimeoutExpired:
        raise RuntimeError("转换超时（60秒），文件可能过大")

    basename = os.path.splitext(os.path.basename(input_path))[0]
    output_path = os.path.join(output_dir, f"{basename}.docx")

    if not os.path.isfile(output_path):
        raise RuntimeError(f"转换完成但输出文件不存在: {output_path}")

    return output_path


def main():
    parser = argparse.ArgumentParser(description="将 .doc 文件转换为 .docx")
    parser.add_argument("--input", "-i", required=True, help="输入 .doc 文件路径")
    parser.add_argument("--output-dir", "-o", help="输出目录（默认与输入文件同目录）")

    args = parser.parse_args()

    try:
        output_path = convert_doc_to_docx(args.input, args.output_dir)
        print(f"转换成功: {output_path}")
    except Exception as e:
        print(f"错误: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
