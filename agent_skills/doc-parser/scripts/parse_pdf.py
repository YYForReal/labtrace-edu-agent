#!/usr/bin/env python3
"""
PDF 文档解析脚本
使用 pdfplumber 提取文本，pytesseract OCR 作为 fallback，
PyMuPDF (fitz) 提取图片 base64 数据供 Vision 分析。
"""

import os
import sys
import json
import argparse
import re
import hashlib
import logging
import tempfile

logger = logging.getLogger(__name__)

try:
    import pdfplumber

    PDF_AVAILABLE = True
except ImportError:
    PDF_AVAILABLE = False

try:
    import pytesseract
    from PIL import Image

    OCR_AVAILABLE = True
except ImportError:
    OCR_AVAILABLE = False

try:
    import fitz  # PyMuPDF

    FITZ_AVAILABLE = True
except ImportError:
    FITZ_AVAILABLE = False

try:
    import base64 as _b64

    B64_AVAILABLE = True
except ImportError:
    B64_AVAILABLE = False

# 图片扩展名 → MIME 类型
_EXT_MIME = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".bmp": "image/bmp",
    ".tiff": "image/tiff",
    ".tif": "image/tiff",
    ".webp": "image/webp",
}


def parse_pdf(file_path):
    """
    解析 PDF 文件，返回结构化数据

    Args:
        file_path: PDF 文件路径

    Returns:
        dict: ParsedDocument 结构
    """
    if not PDF_AVAILABLE:
        raise ImportError("请安装 pdfplumber: pip install pdfplumber")

    if not os.path.isfile(file_path):
        raise FileNotFoundError(f"文件不存在: {file_path}")

    paragraphs = []
    full_text_parts = []
    text_images = []  # pdfplumber 提取的图片位置（用于 fallback）
    page_count = 0

    with pdfplumber.open(file_path) as pdf:
        page_count = len(pdf.pages)

        for page_num, page in enumerate(pdf.pages):
            # 提取文本
            text = page.extract_text()

            if text:
                # 按行分割为段落
                lines = [line.strip() for line in text.split("\n") if line.strip()]
                for line in lines:
                    # 简单的标题检测（全大写或以数字开头的短行）
                    is_heading = len(line) < 50 and (
                        line.isupper()
                        or re.match(r"^[一二三四五六七八九十\d]+[、.．]\s*", line)
                        or re.match(r"^第[一二三四五六七八九十\d]+[章节部分]", line)
                    )

                    paragraphs.append(
                        {
                            "text": line,
                            "style": "Heading" if is_heading else "Normal",
                            "level": 1 if is_heading else None,
                        }
                    )
                    full_text_parts.append(line)

            # 记录 pdfplumber 发现的图片位置（供 fallback 使用）
            if page.images:
                for _img in page.images:
                    text_images.append(
                        {
                            "page": page_num + 1,
                        }
                    )

    full_text = "\n".join(full_text_parts)

    # 如果提取文本过少，尝试 OCR
    ocr_used = False
    if len(full_text) < 100 and OCR_AVAILABLE:
        full_text, paragraphs = _ocr_fallback(file_path)
        ocr_used = True

    # ── 图片提取：优先使用 PyMuPDF (fitz)，支持 base64 数据 ──
    images = _extract_images_with_fitz(file_path, paragraphs, text_images)

    # 提取学生信息
    student_info = _extract_student_info(file_path)

    # 构建结构
    structure = _build_structure(paragraphs)

    return {
        "file_path": os.path.abspath(file_path),
        "file_type": "pdf",
        "student_info": student_info,
        "full_text": full_text,
        "paragraphs": paragraphs,
        "images": images,
        "structure": structure,
        "metadata": {
            "page_count": page_count,
            "word_count": len(full_text),
            "image_count": len(images),
            "ocr_used": ocr_used,
            "image_backend": "fitz" if FITZ_AVAILABLE else "pdfplumber_metadata",
        },
    }


def _extract_images_with_fitz(file_path, paragraphs, text_images):
    """
    使用 PyMuPDF (fitz) 提取 PDF 图片，包含 base64 数据供 Vision 分析。

    如果 PyMuPDF 不可用，回退到 pdfplumber 的图片位置信息（无 base64）。
    """
    images = []
    _seen_hashes = {}  # 去重：content_hash → 首次出现 index

    if FITZ_AVAILABLE and B64_AVAILABLE:
        try:
            doc = fitz.open(file_path)
            image_index = 0

            for page_num in range(len(doc)):
                page = doc[page_num]
                # 获取页面中的所有图片列表
                img_list = page.get_images(full=True)

                for img_info in img_list:
                    xref = img_info[0]  # 图片的 xref 编号

                    try:
                        # 提取图片二进制数据
                        base_image = doc.extract_image(xref)
                        if not base_image:
                            continue

                        image_blob = base_image["image"]
                        if not image_blob or len(image_blob) < 100:
                            continue  # 跳过极小的图片（可能是装饰元素）

                        ext = base_image.get("ext", "png")
                        media_type = _EXT_MIME.get(
                            f".{ext}", base_image.get("mime", "image/png")
                        )

                        # 计算内容 hash 用于去重
                        content_hash = hashlib.sha256(image_blob).hexdigest()

                        # 获取图片上下文（周围文本）
                        context = _get_pdf_image_context(
                            paragraphs, image_index, page_num
                        )

                        image_data = {
                            "index": image_index,
                            "description": f"PDF 第 {page_num + 1} 页图片",
                            "context": context,
                            "base64": _b64.b64encode(image_blob).decode("ascii"),
                            "media_type": media_type,
                            "size_bytes": len(image_blob),
                            "width": base_image.get("width", 0),
                            "height": base_image.get("height", 0),
                        }

                        # 去重检测
                        if content_hash in _seen_hashes:
                            first_idx = _seen_hashes[content_hash]
                            image_data["duplicate_of"] = first_idx
                            logger.debug(
                                "PDF 图片 %d 与图片 %d 内容相同 (hash=%s...)",
                                image_index + 1,
                                first_idx + 1,
                                content_hash[:12],
                            )
                        else:
                            _seen_hashes[content_hash] = image_index

                        images.append(image_data)
                        image_index += 1

                    except Exception as exc:
                        logger.debug(
                            "PDF 图片提取失败 (xref=%s, page=%d): %s",
                            xref,
                            page_num + 1,
                            exc,
                        )
                        continue

            doc.close()

            if images:
                dup_count = sum(1 for img in images if "duplicate_of" in img)
                if dup_count > 0:
                    logger.info(
                        "PDF 图片去重: %d/%d 张为重复图片", dup_count, len(images)
                    )

                logger.info(
                    "PDF 图片提取完成: 共 %d 张 (fitz backend), 文件: %s",
                    len(images),
                    os.path.basename(file_path),
                )
                return images

        except Exception as exc:
            logger.warning("PyMuPDF 图片提取失败，回退到元数据模式: %s", exc)

    # ── Fallback: 仅图片位置信息，无 base64 ──
    for i, info in enumerate(text_images):
        context = _get_pdf_image_context(paragraphs, i, info["page"] - 1)
        images.append(
            {
                "index": i,
                "description": f"PDF 第 {info['page']} 页图片",
                "context": context,
            }
        )

    return images


def _get_pdf_image_context(paragraphs, image_index, page_num):
    """
    获取 PDF 图片周围的文本上下文。

    使用页面号定位到对应的段落区间，取前后各 2 段作为上下文。
    """
    if not paragraphs:
        return ""

    # 粗略按段落序号定位（假设段落分布均匀）
    if len(paragraphs) > 1:
        # 估算该页对应的段落索引范围
        estimated_idx = int(image_index * len(paragraphs) / max(len(paragraphs), 1))
        estimated_idx = max(0, min(estimated_idx, len(paragraphs) - 1))
    else:
        estimated_idx = 0

    start = max(0, estimated_idx - 2)
    end = min(len(paragraphs), estimated_idx + 3)

    context_parts = []
    for i in range(start, end):
        text = paragraphs[i]["text"][:200]
        if not text:
            continue
        if i == estimated_idx:
            context_parts.append(f"[当前段落] {text}")
        else:
            context_parts.append(text)

    return " | ".join(context_parts)


def _ocr_fallback(file_path):
    """OCR fallback for scanned PDFs"""
    try:
        from pdf2image import convert_from_path

        images = convert_from_path(file_path, dpi=300)
        full_text_parts = []
        paragraphs = []

        for i, img in enumerate(images):
            text = pytesseract.image_to_string(img, lang="chi_sim+eng")
            if text.strip():
                lines = [line.strip() for line in text.split("\n") if line.strip()]
                for line in lines:
                    paragraphs.append({"text": line, "style": "Normal", "level": None})
                    full_text_parts.append(line)

        return "\n".join(full_text_parts), paragraphs

    except Exception:
        return "", []


def _extract_student_info(file_path):
    """从文件名提取学生信息"""
    basename = os.path.basename(file_path)
    name_without_ext = os.path.splitext(basename)[0]

    match = re.search(r"(\d{10})([\u4e00-\u9fff]{2,4})", name_without_ext)
    if match:
        return {"student_id": match.group(1), "name": match.group(2)}

    match = re.search(r"(\d{8,12})[_\s\-]([\u4e00-\u9fff]{2,4})", name_without_ext)
    if match:
        return {"student_id": match.group(1), "name": match.group(2)}

    return None


def _build_structure(paragraphs):
    """构建文档结构"""
    sections = []
    current_section = None
    content_length = 0

    for para in paragraphs:
        if para.get("level") is not None:
            if current_section:
                current_section["content_length"] = content_length
                sections.append(current_section)
            current_section = {
                "title": para["text"],
                "level": para["level"],
                "content_length": 0,
            }
            content_length = 0
        else:
            content_length += len(para["text"])

    if current_section:
        current_section["content_length"] = content_length
        sections.append(current_section)

    return {"sections": sections}


def main():
    parser = argparse.ArgumentParser(description="解析 PDF 文档")
    parser.add_argument("--input", "-i", required=True, help="输入 PDF 文件路径")
    parser.add_argument("--output", "-o", help="输出 JSON 文件路径")

    args = parser.parse_args()

    try:
        result = parse_pdf(args.input)
        output_json = json.dumps(result, ensure_ascii=False, indent=2)

        if args.output:
            with open(args.output, "w", encoding="utf-8") as f:
                f.write(output_json)
            print(f"解析完成，结果保存到: {args.output}")
        else:
            print(output_json)

    except Exception as e:
        print(f"错误: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
