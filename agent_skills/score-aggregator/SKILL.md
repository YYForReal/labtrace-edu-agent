---
name: score-aggregator
description: >
  Use this skill to aggregate grading results across all students, match scores with
  the class roster, calculate statistics, generate comprehensive Excel reports, and
  fill scores back into the school's official grade registration spreadsheet.
  Triggers on requests like "aggregate scores", "generate grade report", "create
  statistics", "summarize class performance", "fill scores into Excel", "update
  grade sheet". Supports both standalone reports and in-place modification of the
  school's standard grade registration form. Uses openpyxl.
---

# Score Aggregator — 成绩统计技能

## 概述

本技能提供两大能力：

1. **成绩汇总报表**：汇总全班评分结果，计算统计指标，生成独立的四工作表 Excel 报表
2. **成绩回填到学校登记表**：将批改成绩按学号匹配回填到学校统一格式的《学生成绩登记表》Excel 中，保留原始格式和合并单元格。默认自动在成绩单元格上添加**批注说明**（含分项成绩明细和评语），并**自动追加统计汇总和分数分布工作表**

## 成绩回填流程（推荐）

### Step 0: 准备成绩数据

成绩数据以 JSON 格式提供，每个学生一条记录：

```json
[
  {
    "student_id": "2022150022",
    "student_name": "林振法",
    "total_score": 83,
    "scores": [37, 3, 3, 5, 7, 5, 23],
    "comment": "评语文本（写入 Excel 单元格批注）"
  }
]
```

### Step 1: 回填成绩到登记表

```bash
python scripts/fill_score_to_excel.py \
  --excel 成绩登记表.xlsx \
  --scores results.json \
  --output 成绩登记表_已填.xlsx
```

默认行为（无需额外参数）：
- 成绩回填到"平时总评成绩"列
- 在成绩单元格上添加**批注说明**（分项明细 + 等级 + 评语）
- 自动追加**统计汇总**和**分数分布直方图**工作表

可选开关：
- `--no-comments` — 不添加批注说明
- `--no-stats` — 不追加统计工作表
- `--comment-author "教师名"` — 自定义批注作者名（默认 "AI批改助手"）

自动检测学校成绩登记表结构：
- 表头行：搜索包含"学号"和"姓名"的行
- 学号列、姓名列、平时总评成绩列：自动定位
- 周次考核列 (H-R)：识别 1-11 编号子表头
- 学生数据行：从表头后第3行开始扫描

支持三种填充模式：
- `total_score` — 仅填写平时总评成绩列（默认）
- `week_score` — 仅填写指定周次的考核列
- `both` — 同时填写两列

```bash
# 同时填写第5周考核列和总评列
python scripts/fill_score_to_excel.py \
  --excel 成绩登记表.xlsx \
  --scores results.json \
  --output 成绩登记表_已填.xlsx \
  --week-number 5 \
  --fill-mode both \
  --append-stats
```

### Step 2: 批量批改 + 回填（一站式）

```bash
python scripts/batch_grade_and_export.py \
  --input-dir 学生报告目录/ \
  --output-dir 批改后/ \
  --excel 成绩登记表.xlsx \
  --config-dir 批改配置目录/ \
  --signature 签名图片.jpeg
```

扫描学生 docx → 逐一批改注入 → 收集成绩 → 回填 Excel → 追加统计工作表。

## 独立统计报表流程

### Step 1: 读取学生名单

```bash
python scripts/read_roster.py --input 考勤表.xlsx --output roster.json
```

支持 `.xlsx`、`.xls`、`.csv` 格式。自动识别包含"学号"和"姓名"列的工作表。

学号标准化处理：
- 去除前后空格
- 统一转为字符串类型
- 10 位数字正则验证：`^\d{10}$`

### Step 2: 匹配成绩数据

```bash
python scripts/match_scores.py \
  --roster roster.json \
  --results grading_results/ \
  --output matched.json
```

匹配策略：
1. 以学生名单为基准（左连接）
2. 按学号精确匹配
3. 未匹配到成绩的标记为"未提交"
4. 有成绩但不在名单中的标记为"名单外提交"

### Step 3: 计算统计指标

```bash
python scripts/calculate_stats.py --input matched.json --output stats.json
```

| 指标 | 公式 |
|------|------|
| 平均分 | `mean(scores)` |
| 最高分 | `max(scores)` |
| 最低分 | `min(scores)` |
| 中位数 | `median(scores)` |
| 标准差 | `std(scores)` |
| 及格率 | `count(score >= 60) / total * 100%` |

五档分布：

| 档次 | 分数段 | 对应等级 |
|------|--------|---------|
| 优秀 | 90-100 | A |
| 良好 | 80-89 | B |
| 中等 | 70-79 | C |
| 及格 | 60-69 | D |
| 不及格 | 0-59 | F |

### Step 4: 生成独立 Excel 报表

```bash
python scripts/generate_excel.py \
  --matched matched.json \
  --stats stats.json \
  --output "实验一_成绩统计.xlsx"
```

生成四个工作表：

**工作表 1：成绩总表**
- 列：学号、姓名、各评分项得分、总分、等级、状态
- 表头：白色加粗字体，深蓝背景 `#366092`
- 冻结首行
- 按总分降序排列

**工作表 2：统计汇总**
- 班级总人数、提交人数、已批改人数
- 平均分、最高分、最低分、中位数、标准差
- 及格率、优秀率、良好率、中等率、不及格率

**工作表 3：分数分布**
- 五档分布表（分数段、人数、占比）
- 柱状图（分数分布直方图）
- 图表配置：标题"分数分布直方图"，X轴"分数段"，Y轴"人数"

**工作表 4：未提交学生**
- 列：学号、姓名、状态
- 表头：白色加粗字体，红色背景 `#CC0000`

## 脚本清单

| 脚本 | 功能 | 输入 | 输出 |
|------|------|------|------|
| `fill_score_to_excel.py` | 成绩回填到学校登记表 | Excel + 成绩 JSON | 已填 Excel |
| `batch_grade_and_export.py` | 批量批改 + 回填 | docx 目录 + Excel | 批改 docx + 已填 Excel |
| `generate_excel.py` | 独立统计报表 | matched JSON + stats JSON | 四工作表 Excel |
| `calculate_stats.py` | 统计计算 | matched JSON | stats JSON |

## 依赖项

```
openpyxl>=3.1.0
```

## Guidelines

1. **成绩回填优先**：教师通常需要把成绩填入学校统一的登记表，优先使用 `fill_score_to_excel.py`
2. **批注说明默认开启**：每个成绩单元格自动附加 Excel 批注，内容包括分项成绩明细（如 `37+3+3+5+7+5+23=83`）、等级和评语。教师悬停单元格即可查看完整批改说明
3. **统计汇总自动追加**：回填成绩后默认追加"统计汇总"和"分数分布直方图"两个工作表，无需单独传 `--append-stats` 参数
4. **格式保留**：回填时保留原始合并单元格、标题行、课程信息等，仅修改成绩数据列和批注
5. **学号匹配容错**：去除前后空格，统一转字符串，支持 6 位以上数字学号
6. **姓名校验**：匹配后检查姓名一致性，不一致时输出警告（不阻止写入）
7. **空值处理**：成绩为空的学生在统计时排除，不影响平均分计算
8. **排序规则**：成绩总表默认按总分降序，未提交排在最后
9. **文件命名**：回填输出建议命名为 `{原文件名}_已填.xlsx`
10. **安全保存**：使用临时文件 + 原子替换避免 macOS 文件锁冲突
