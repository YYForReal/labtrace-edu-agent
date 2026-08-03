---
name: ta-grading-workflow
description: >
  Top-level orchestration skill for the Game Development course TA grading workflow.
  Use this skill when the user wants to grade student lab reports end-to-end, either
  a single report or a batch of reports. Triggers on requests like "grade reports",
  "批改实验报告", "start grading workflow", "批量批改", "帮我批改这份报告".
  Coordinates doc-parser, grading-engine, feedback-generator, report-injector, and
  score-aggregator skills in sequence with human-in-the-loop checkpoints.
---

# TA Grading Workflow — 助教批改流程编排技能

## 概述

本技能是顶层编排技能，串联五大子技能完成《计算机游戏开发》课程实验报告的完整批改流程。支持**单份批改**和**批量批改**两种模式，内置 Human-in-the-loop 检查点。

## 两种批改模式

### 模式 A：单份批改

适用于逐份批改或需要仔细审阅的场景。

```
用户指令示例：
- "帮我批改这份实验报告：2024010001张三.doc"
- "批改一下 /path/to/report.docx，用实验一的评分标准"
```

### 模式 B：批量批改

适用于批量处理一个文件夹中的所有报告。

```
用户指令示例：
- "批量批改 实验一/A/ 文件夹下的所有报告"
- "批改实验二目录下的全部学生报告，生成成绩统计"
```

## 完整批改 SOP

### Phase 1: 准备（Preparation）

**1.1 确认输入**

| 参数 | 必需 | 说明 |
|------|------|------|
| 报告文件/目录 | 是 | 单个文件路径或包含多个报告的目录 |
| 评分标准 | 是 | `config/rubrics/` 下的 JSON 文件 |
| 学生名单 | 批量必需 | 考勤表 Excel（用于成绩统计） |
| 评语风格 | 否 | encouraging/standard/strict，默认 standard |
| 输出目录 | 否 | 默认在输入目录旁创建 `_graded/` |

**1.2 环境检查**

```bash
# 检查 LibreOffice（.doc 转换需要）
which soffice || echo "Warning: LibreOffice not found, .doc files cannot be processed"

# 检查 Python 依赖
python -c "import docx; import pandas; import openpyxl; print('All dependencies OK')"
```

**1.3 扫描报告文件**

```bash
# 列出目标目录下的所有报告文件
find /path/to/reports -name "*.doc" -o -name "*.docx" -o -name "*.pdf" | sort
```

### Phase 2: 文档解析（Parse）

对每个报告文件调用 **doc-parser** 技能：

```
[doc-parser] 解析文档
  ├── .doc → soffice 转换 → .docx
  ├── .docx → python-docx 提取
  └── .pdf → pdfplumber 提取

输出：ParsedDocument JSON
```

### Phase 3: AI 评分（Grade）

对每个 ParsedDocument 调用 **grading-engine** 技能：

```
[grading-engine] AI 评分
  ├── 加载 rubric JSON
  ├── 构建评分 Prompt
  ├── 调用 LLM（temperature=0.2）
  ├── 解析评分结果
  └── 校验分数范围

输出：GradingResult JSON
```

### 🛑 检查点 1：Human-in-the-Loop

**AI 评分完成后，暂停等待助教确认。**

向助教展示评分结果摘要：

```
═══════════════════════════════════
学生：2024010001 张三
总分：82/100（置信度：0.85）

场景搭建：22/25 - 场景包含基本元素，摄像机角度略有偏差
游戏对象：25/30 - 创建了多个对象，层级基本合理
组件使用：18/25 - 组件使用基本正确，参数配置有瑕疵
代码实现：17/20 - 代码基本完整，注释较少

优点：场景搭建完整、代码结构清晰
不足：组件参数不够精确
═══════════════════════════════════

请确认或调整：
[1] 确认评分，继续
[2] 调整某项分数
[3] 跳过此份，稍后处理
[4] 终止批改流程
```

助教可以：
- **确认**：直接进入评语生成
- **调整**：修改具体分数后继续
- **跳过**：标记为"待复核"跳过
- **终止**：停止整个流程

> **批量模式下**：可以设置"自动确认"模式（对置信度 > 0.8 的自动通过），仅对低置信度的暂停确认。

### Phase 4: 评语生成（Feedback）

对确认后的 GradingResult 调用 **feedback-generator** 技能：

```
[feedback-generator] 生成评语
  ├── 选择评语风格
  ├── 加载预设评语词库
  ├── 构建评语 Prompt
  └── 生成 150-200 字评语

输出：评语文本
```

### Phase 5: 文档注入（Inject）

调用 **report-injector** 技能将结果写入文档：

```
[report-injector] 注入评分结果
  ├── 复制原始文档
  ├── 追加评分汇总表
  ├── 追加详细评价（颜色编码）
  └── 追加助教总评

输出：{学号}_{姓名}_批改.docx
```

### 🛑 检查点 2：批改结果确认

展示批改后文档的预览，确认注入内容无误。

### Phase 6: 成绩统计（Aggregate）

**仅在批量模式下执行。**

所有报告批改完成后，调用 **score-aggregator** 技能：

```
[score-aggregator] 成绩统计
  ├── 读取学生名单
  ├── 匹配全部成绩
  ├── 计算统计指标
  └── 生成四工作表 Excel

输出：实验X_成绩统计.xlsx
```

### Phase 7: 输出总结

批改完成后输出总结报告：

```
═══════════════════════════════════
批改完成总结
═══════════════════════════════════
实验名称：Unity基础操作与游戏对象创建
批改数量：42/45
平均分：78.5
最高分：98（张三）
最低分：35（李四）
未提交：3人

输出目录：/path/to/_graded/
成绩表：实验一_成绩统计_20250312.xlsx
═══════════════════════════════════
```

## 错误处理策略

| 错误类型 | 处理方式 |
|---------|---------|
| 文件无法打开 | 跳过该文件，记录到 errors.log |
| .doc 转换失败 | 尝试 antiword fallback，仍失败则跳过 |
| LLM 调用失败 | 使用 mock 评分并在 warnings 中标注 |
| 分数校验失败 | 暂停等待人工审核 |
| 内存不足 | 分批处理，每批不超过 10 份 |

## 数据传递

各技能间通过 JSON 文件传递数据：

```
doc-parser → parsed_document.json → grading-engine
grading-engine → grading_result.json → feedback-generator
grading-engine → grading_result.json → report-injector
feedback-generator → comment.txt → report-injector
grading-engine → grading_results/*.json → score-aggregator
```

## Guidelines

1. **始终从准备阶段开始**，确认输入参数完整
2. **Human-in-the-loop 是核心**，不要跳过检查点（除非助教明确要求自动模式）
3. **每份报告独立处理**，一份失败不影响其他
4. **中间结果持久化**，每个阶段的 JSON 输出保存到 `_graded/` 目录
5. **进度反馈**，批量模式下显示 `[3/42] 正在处理...` 进度
6. **超时保护**，单份报告处理不超过 2 分钟，超时则跳过
