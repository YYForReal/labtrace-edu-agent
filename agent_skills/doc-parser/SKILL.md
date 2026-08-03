---
name: doc-parser
description: >
  Use this skill when you need to parse student lab report documents (.doc, .docx, or .pdf)
  for the Game Development course. Triggers on requests like "parse report", "read student
  document", "extract report content", "analyze submission file". Outputs a structured
  ParsedDocument JSON containing full text, paragraphs, images, document structure, and
  student info (student_id + name extracted from filename). Handles .doc→.docx conversion
  via LibreOffice headless mode.
---

# Doc Parser — 实验报告文档解析技能

## 概述

本技能负责将学生提交的实验报告文档（`.doc`、`.docx`、`.pdf`）解析为结构化的 `ParsedDocument` JSON，供下游评分引擎和报告注入技能使用。

## 快速参考

| 操作 | 方法 |
|------|------|
| `.doc` → `.docx` 转换 | `soffice --headless --convert-to docx` 或 `scripts/convert_doc.py` |
| `.docx` 文本提取 | `scripts/parse_docx.py` (python-docx) |
| `.pdf` 文本提取 | `scripts/parse_pdf.py` (pdfplumber + OCR fallback) |
| 学生信息提取 | `scripts/extract_student_info.py` (正则匹配文件名) |

## 操作流程

### Step 1: 检测文件类型

```python
import os
ext = os.path.splitext(file_path)[1].lower()
# .doc → 需要先转换为 .docx
# .docx → 直接解析
# .pdf → 使用 PDF 解析器
```

### Step 2: .doc 预处理（仅 .doc 文件）

学生实际提交的多为 `.doc` 格式（OLE 二进制），python-docx 不支持直接读取，必须先转换。

**方法 A：LibreOffice 命令行转换（推荐）**

```bash
soffice --headless --convert-to docx --outdir /tmp/converted "学生报告.doc"
```

**方法 B：使用辅助脚本**

```bash
python scripts/convert_doc.py --input "学生报告.doc" --output-dir /tmp/converted
```

转换前检查 LibreOffice 是否可用：

```bash
which soffice || which libreoffice
# macOS: /Applications/LibreOffice.app/Contents/MacOS/soffice
```

如果 LibreOffice 不可用，尝试使用 `textract` 或 `antiword` 作为 fallback：

```bash
antiword "学生报告.doc" > output.txt
```

### Step 3: 解析 DOCX 文档

运行解析脚本：

```bash
python scripts/parse_docx.py --input "学生报告.docx" --output parsed_result.json
```

脚本执行以下操作：
1. 使用 `python-docx` 打开文件
2. 遍历所有段落，提取文本和样式（标题级别、正文、列表项）
3. 提取嵌入图片，保存描述和上下文
4. 构建文档结构树（标题层级）
5. 提取文档元数据（作者、创建时间、修改时间）

### Step 4: 解析 PDF 文档

```bash
python scripts/parse_pdf.py --input "学生报告.pdf" --output parsed_result.json
```

脚本逻辑：
1. 使用 `pdfplumber` 提取文本
2. 如果提取文本为空或过少，使用 `pytesseract` OCR
3. 提取页面中的图片
4. 构建段落结构

### Step 5: 提取学生信息

从文件名提取学号和姓名。文件名格式约定：`{学号}{姓名}.doc` 或 `{学号}_{姓名}.doc`。

```bash
python scripts/extract_student_info.py --filename "2024010001张三.doc"
# 输出: {"student_id": "2024010001", "name": "张三"}
```

正则匹配规则：
- 10 位数字学号：`(\d{10})`
- 学号后紧跟或用下划线/空格分隔的中文姓名：`[\u4e00-\u9fff]{2,4}`

## 输出格式

```json
{
  "file_path": "/path/to/report.docx",
  "file_type": "docx",
  "student_info": {
    "student_id": "2024010001",
    "name": "张三"
  },
  "full_text": "完整文本内容...",
  "paragraphs": [
    {"text": "实验一：Unity基础操作", "style": "Heading 1", "level": 1},
    {"text": "一、实验目的", "style": "Heading 2", "level": 2},
    {"text": "本实验旨在...", "style": "Normal", "level": null}
  ],
  "images": [
    {"index": 0, "description": "Unity场景截图", "context": "图1展示了场景搭建的效果"}
  ],
  "structure": {
    "sections": [
      {"title": "实验目的", "level": 1, "content_length": 200},
      {"title": "实验步骤", "level": 1, "content_length": 1500}
    ]
  },
  "metadata": {
    "author": "张三",
    "created": "2025-03-10T10:00:00",
    "modified": "2025-03-11T15:30:00",
    "word_count": 2000,
    "page_count": 8,
    "image_count": 5
  }
}
```

## 依赖项

```
python-docx>=0.8.11
pdfplumber>=0.9.0
pytesseract>=0.3.10  # OCR fallback
Pillow>=9.0.0
```

系统级依赖：
- LibreOffice（.doc 转 .docx）
- Tesseract OCR（扫描型 PDF）

## Guidelines

1. **始终先检查文件类型**，不要假设输入一定是 .docx
2. **优先使用 LibreOffice 转换 .doc**，因为它保持格式最完整
3. **文本提取后检查内容长度**，如果过短（< 100 字符）可能是扫描文档，需要 OCR
4. **学生信息提取失败时不要报错**，设为 null 并在 warnings 中记录
5. **图片描述依赖上下文推断**，提取图片前后的文本段落作为 context
6. **编码统一使用 UTF-8**，处理中文内容时注意编码
7. **文档内容超过 8000 tokens 时需要截断**，保留前后各 3000 tokens，中间用 `[...已截断...]` 标记
