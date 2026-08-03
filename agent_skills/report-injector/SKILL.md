---
name: report-injector
description: >
  Use this skill to inject grading results, detailed feedback, and TA comments into
  student lab report documents (.docx). Triggers on requests like "inject scores",
  "write grades into document", "annotate report", "create graded document". Appends
  a formatted score table, color-coded detailed evaluation, and final TA comment to
  the end of the original document while preserving all original content. Uses
  python-docx for document manipulation.
---

# Report Injector — 报告注入技能

## 概述

本技能将评分结果（评分表格、详细评价、助教总评）注入到学生原始实验报告文档末尾，保持原文完全不变。使用 `python-docx` 库操作 DOCX 文件。

## 注入内容结构

注入到文档末尾的内容包含三个区块：

```
[原始文档内容保持不变]
    ↓
[分页符]
    ↓
┌──────────────────────────────┐
│   【AI 辅助批改报告】          │  ← 区块1：评分汇总表
│   学生姓名：XX  学号：XX       │
│   总分：XX分                   │
│                               │
│   ┌────┬────┬────┬─────┐     │
│   │评分项│满分│得分│ 评注 │     │
│   ├────┼────┼────┼─────┤     │
│   │... │ .. │ .. │ ... │     │
│   └────┴────┴────┴─────┘     │
└──────────────────────────────┘
    ↓
┌──────────────────────────────┐
│   【详细评价】                 │  ← 区块2：详细评价
│   ✓ 优点：...                 │     （颜色编码）
│   ⚠ 需要改进：...             │
│   → 改进建议：...             │
└──────────────────────────────┘
    ↓
[分页符]
    ↓
┌──────────────────────────────┐
│   【助教总评】                 │  ← 区块3：助教总评
│   评语内容...                  │
│   ────────────────            │
└──────────────────────────────┘
```

## 操作流程

### Step 1: 复制原始文档

```python
import shutil
shutil.copy2(original_doc_path, output_path)
```

**永远不要修改原始文件**，始终在副本上操作。

### Step 2: 注入评分汇总表

运行注入脚本：

```bash
python scripts/inject_score_table.py \
  --input graded_copy.docx \
  --grading-result grading_result.json \
  --output graded_copy.docx
```

评分表格式规范：
- **标题**：`【AI 辅助批改报告】`，16pt，加粗，深蓝色 `#003366`，居中
- **学生信息行**：姓名、学号、总分，加粗
- **表格**：4 列（评分项 | 满分 | 得分 | 评注）
- **表头**：白色文字，深蓝背景 `#003366`
- **得分颜色编码**：
  - 得分率 ≥ 80%：绿色 `#008000`
  - 得分率 60%-79%：默认黑色
  - 得分率 < 60%：红色 `#CC0000`
- **总分行**：加粗，14pt

**核心代码**（从 docx_injector.py 提炼）：

```python
from docx import Document
from docx.shared import Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.oxml import OxmlElement

doc = Document(output_path)

# 添加分页符
doc.add_page_break()

# 添加标题
title = doc.add_paragraph()
title_run = title.add_run("【AI 辅助批改报告】")
title_run.font.size = Pt(16)
title_run.font.bold = True
title_run.font.color.rgb = RGBColor(0, 51, 102)
title.alignment = WD_ALIGN_PARAGRAPH.CENTER

# 创建表格
table = doc.add_table(rows=1, cols=4)
# ... 填充数据和样式
```

### Step 3: 注入详细评价

```bash
python scripts/inject_comments.py \
  --input graded_copy.docx \
  --grading-result grading_result.json \
  --output graded_copy.docx
```

详细评价颜色编码：
- **✓ 优点**：绿色 `#008000`，加粗标题
- **⚠ 需要改进**：橙色 `#CC6600`，加粗标题
- **→ 改进建议**：蓝色 `#003399`，加粗标题
- **⚠ 警告**：红色 `#CC0000`，加粗标题

每个条目使用 `•` 前缀列表展示。

### Step 4: 注入助教总评

```bash
python scripts/inject_final_comment.py \
  --input graded_copy.docx \
  --comment "评语文本..." \
  --output graded_copy.docx
```

总评格式：
- 新页开始（分页符）
- 标题：`【助教总评】`，14pt，加粗，深蓝色，居中
- 评语正文：12pt，左对齐
- 底部分隔线：灰色 `#808080`

### Step 5: 保存并验证

```python
doc.save(output_path)
# 验证文件可以正常打开
doc_verify = Document(output_path)
assert len(doc_verify.paragraphs) > 0
```

## 依赖项

```
python-docx>=0.8.11
```

## Guidelines

1. **绝不修改原文**：所有注入内容追加到文档末尾，原始段落不做任何改动
2. **先复制后操作**：始终在文件副本上工作
3. **输出文件命名**：`{学号}_{姓名}_批改.docx` 或 `{原文件名}_graded.docx`
4. **字体兼容性**：使用系统通用字体（宋体/微软雅黑/SimSun），避免特殊字体
5. **表格样式容错**：如果指定的 table style 不可用，使用默认 Table Grid
6. **大文件处理**：对于超过 50 页的文档，注意内存使用
7. **编码处理**：确保中文内容正确显示，所有文本使用 UTF-8
