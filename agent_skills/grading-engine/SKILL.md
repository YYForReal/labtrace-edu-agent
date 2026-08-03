---
name: grading-engine
description: >
  Use this skill when grading student lab reports for the Game Development course.
  Triggers when the user wants to evaluate, score, or assess a student's experiment
  report against a rubric. Accepts a parsed document (text + images) and a JSON
  rubric file, outputs structured GradingResult JSON with per-criterion scores,
  detailed analysis, strengths, weaknesses, suggestions, and confidence level.
  Uses Chain-of-Thought reasoning for transparent scoring decisions.
---

# Grading Engine — AI 评分引擎技能

## 概述

本技能负责根据 JSON 评分标准（rubric）对学生实验报告进行多维度逐项评分。使用 Chain-of-Thought 推理确保评分过程透明可追溯，输出结构化 `GradingResult` JSON。

## 评分 SOP（标准操作流程）

### Step 1: 加载评分标准

从 `config/rubrics/` 目录加载对应实验的 JSON 评分标准文件：

```bash
python scripts/load_rubric.py --rubric config/rubrics/exp01_unity_basics.json
```

评分标准 JSON 结构：

```json
{
  "experiment_name": "实验名称",
  "total_score": 100,
  "criteria": [
    {
      "id": "criterion_id",
      "name": "评分项名称",
      "max_score": 25,
      "weight": 0.25,
      "description": "评分项描述",
      "rules": [
        {"condition": "条件描述", "score": 25, "reason": "得分理由"}
      ]
    }
  ],
  "few_shot_examples": [...],
  "grading_tips": [...]
}
```

### Step 2: 构建评分 Prompt

使用以下多段结构构建评分 Prompt：

```bash
python scripts/build_prompt.py \
  --rubric config/rubrics/exp01_unity_basics.json \
  --document parsed_document.json \
  --output prompt.txt
```

**Prompt 模板结构**（六段式）：

```
[角色定义]
你是一位资深的游戏开发工程师和高校《计算机游戏开发》课程助教。
你有丰富的 Unity/Unreal 引擎开发经验，熟悉游戏开发的各个环节。

[任务说明]
请严格按照评分标准对学生的实验报告进行客观、公正的评分。

[评分原则]
1. 严格按照评分标准中的规则进行评分
2. 根据学生实际完成情况进行判断，不偏袒也不严苛
3. 评分理由要具体、客观，引用报告中的具体内容作为证据
4. 发现抄袭或雷同时，在 warnings 中标注

[评分标准]
{从 rubric JSON 动态填充每个 criterion 的名称、分值、规则}

[学生报告内容]
{从 ParsedDocument 填充 full_text + images 描述}

[Few-shot 示例]（如有）
{从 rubric 的 few_shot_examples 填充，最多 2 个}

[输出格式]
严格按照 GradingResult JSON Schema 输出
```

### Step 3: 执行评分

**关键参数**：
- `temperature = 0.2`（确保评分稳定性，减少随机波动）
- `max_tokens = 4096`
- 单次输入不超过 8000 tokens

**Chain-of-Thought 推理要求**：

对每个评分项，按以下顺序思考：
1. **证据识别**：从报告中找到与该评分项相关的内容
2. **规则匹配**：将找到的证据与 rules 中的条件逐一比对
3. **分数判定**：选择最匹配的规则对应的分数
4. **理由撰写**：用 50 字以内说明得分理由，引用具体证据

### Step 4: 解析评分结果

```bash
python scripts/parse_grading_response.py --response llm_response.json --rubric config/rubrics/exp01_unity_basics.json
```

脚本执行以下操作：
1. 从 LLM 响应中提取 JSON（容错处理：正则提取 `{...}` 块）
2. 将每个 criterion_score 与 rubric 中的 max_score 关联
3. 校验分数范围（0 ≤ score ≤ max_score）
4. 计算总分

### Step 5: 校验评分

```bash
python scripts/validate_scores.py --result grading_result.json --rubric config/rubrics/exp01_unity_basics.json
```

校验规则：
- 每项得分不超过该项 max_score
- 每项得分不为负数
- 总分等于各项得分之和
- 置信度在 0-1 范围内
- 低置信度（< 0.6）时在 warnings 中标注"建议人工复核"

## 输出格式

```json
{
  "student_id": "2024010001",
  "student_name": "张三",
  "total_score": 82,
  "criterion_scores": [
    {
      "criterion_id": "scene_setup",
      "criterion_name": "场景搭建",
      "max_score": 25,
      "score": 22,
      "reason": "场景包含地面、光源和摄像机，但摄像机角度略有偏差"
    }
  ],
  "detailed_analysis": "该学生较好地完成了Unity基础操作实验...",
  "strengths": ["场景搭建完整", "代码结构清晰"],
  "weaknesses": ["组件参数配置不够精确"],
  "suggestions": ["建议调整摄像机视角", "建议增加代码注释"],
  "confidence": 0.85,
  "warnings": []
}
```

## Guidelines

1. **评分标准是唯一的评分依据**，不要引入 rubric 之外的评分维度
2. **证据驱动**，每个分数必须有报告中的具体内容支撑
3. **分数只能从 rules 中选择**，不允许给出 rules 之外的分数（如 rules 中没有 17 分的选项，就不能给 17 分）
4. **置信度反映报告信息充分程度**：内容丰富 → 0.8+；内容简略 → 0.5-0.7；几乎无内容 → < 0.5
5. **对截图/图片的评估**：如果报告中有截图描述，应纳入评分考量
6. **抄袭检测**：如果多份报告内容高度相似（> 80%），在 warnings 中标注
7. **Mock 模式**：如果没有 LLM 可用，使用 `scripts/mock_grading.py` 生成模拟评分（用于测试流程）
