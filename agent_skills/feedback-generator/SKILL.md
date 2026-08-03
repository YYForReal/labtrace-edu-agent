---
name: feedback-generator
description: >
  Use this skill to generate personalized feedback comments for graded student lab
  reports. Triggers on requests like "generate comment", "write feedback", "create
  review". Supports three styles: encouraging (鼓励型), standard (标准型), strict
  (严格型). Uses the "sandwich method" (praise → criticism → encouragement).
  Incorporates a curated library of 24+ preset comment phrases from the legacy
  grading tool. Outputs 150-200 character Chinese feedback text.
---

# Feedback Generator — 评语生成技能

## 概述

本技能根据评分结果（GradingResult）生成个性化中文评语，支持三种风格，遵循"三明治法则"（肯定→指出不足→改进建议与鼓励），输出 150-200 字的评语文本。

## 三种评语风格

| 风格 | 代码 | 适用场景 | 语气特点 |
|------|------|---------|---------|
| 鼓励型 | `encouraging` | 总分 < 60 或首次提交 | 积极肯定，建设性建议，结尾鼓励 |
| 标准型 | `standard` | 总分 60-85 | 客观平衡，肯定成绩也指出不足 |
| 严格型 | `strict` | 总分 > 85 或高年级 | 严格直接，重点指出改进方向 |

## 评语生成流程

### Step 1: 确定评语风格

根据总分自动选择风格（可由助教手动覆盖）：

```python
def select_style(total_score, manual_style=None):
    if manual_style:
        return manual_style
    if total_score < 60:
        return "encouraging"
    elif total_score <= 85:
        return "standard"
    else:
        return "strict"
```

### Step 2: 加载预设评语词库

```bash
python scripts/comment_templates.py --style standard --score 82
```

预设评语词库来源于前代批改工具积累的 24 个快速评语，已按类别和适用分数段组织：

**通用肯定类**：
- "实验完成度较高，基本达到了实验要求"
- "报告结构清晰，图文并茂"
- "代码实现完整，功能运行正确"
- "有自己的思考和创新点"

**通用不足类**：
- "实验报告内容较为简略，缺少详细的步骤描述"
- "截图不够清晰或缺少关键步骤的截图"
- "代码注释不足，可读性有待提高"
- "缺少实验总结和心得体会"

**鼓励类**：
- "继续保持，期待你在后续实验中的精彩表现"
- "虽然还有提升空间，但已经展现了不错的学习态度"
- "建议多参考教程和文档，相信下次会更好"

**严格类**：
- "请认真对待实验报告，这是巩固知识的重要环节"
- "代码质量需要显著提升，建议重新阅读编码规范"
- "实验内容与要求差距较大，建议课后补充练习"

### Step 3: 构建评语 Prompt

使用以下模板：

```
你是一位经验丰富的《计算机游戏开发》课程助教。
请根据以下评分信息生成实验报告评语。

# 评语风格要求
{style_description}

# 三明治法则
评语必须按以下结构组织：
1. 开头：肯定学生的优点和付出（1-2句）
2. 中间：客观指出不足和问题（1-2句）
3. 结尾：提供改进建议和鼓励（1-2句）

# 学生信息
- 姓名：{student_name}
- 总分：{total_score}/100

# 分项得分
{per_criterion_scores}

# 优点
{strengths}

# 不足
{weaknesses}

# 改进建议
{suggestions}

# 参考评语短语（可选择性融入）
{selected_templates}

# 输出要求
- 字数：150-200字
- 语言：中文
- 语气：{style}
- 不要使用"你"，使用"同学"或直接称呼姓名
- 不要透露具体分数数字，用"得分较高/一般/偏低"等表述
```

### Step 4: 生成并校验

生成后校验：
1. 字数在 100-250 范围内（允许适度浮动）
2. 包含肯定内容（检查正面词汇）
3. 包含建设性内容（检查建议词汇）
4. 不包含具体分数数字
5. 不包含敏感或不当用语

## 输出格式

纯文本字符串，150-200 字中文评语。

**示例输出（标准型）**：

> 张三同学本次实验完成度较好，场景搭建完整规范，展现了对 Unity 基础操作的扎实掌握。游戏对象的创建和层级组织也体现了良好的工程思维。不过在组件参数配置方面还有提升空间，部分 Collider 的尺寸设置不够精确，代码注释也略显不足。建议在后续实验中注重组件属性的细节调整，养成良好的注释习惯。期待在下一次实验中看到更出色的表现。

## Guidelines

1. **三明治法则不可违反**：必须有肯定、有指出、有建议
2. **避免千篇一律**：每份评语应该针对该学生的具体情况，不要套用完全相同的模板
3. **不透露具体分数**：使用"表现优秀/良好/一般/有待提高"等模糊表述
4. **称谓统一**：使用"XX同学"，不使用"你"
5. **字数控制**：严格控制在 150-200 字，过长则截断优化
6. **正面导向**：即使是严格型，也要有建设性，不要纯粹批评
7. **专业术语**：适当使用游戏开发领域的专业术语，体现专业性
