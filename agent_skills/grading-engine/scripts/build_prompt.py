#!/usr/bin/env python3
"""
评分 Prompt 构建脚本
从 rubric JSON 和文档内容组装评分 Prompt
"""

import os
import sys
import json
import argparse


def build_grading_prompt(rubric, document, options=None):
    """
    构建评分 Prompt

    Args:
        rubric: 评分标准字典
        document: 解析后的文档字典（ParsedDocument）
        options: 可选参数

    Returns:
        str: 完整的评分 Prompt
    """
    options = options or {}

    # 角色定义
    system_prompt = """你是一位资深的游戏开发工程师和高校《计算机游戏开发》课程助教。
你有丰富的 Unity/Unreal 引擎开发经验，熟悉游戏开发的各个环节。
你的任务是严格按照评分标准对学生的实验报告进行客观、公正的评分。

评分原则：
1. 严格按照评分标准中的规则进行评分
2. 根据学生实际完成情况进行判断，不偏袒也不严苛
3. 评分理由要具体、客观，引用报告中的具体内容作为证据
4. 发现问题要明确指出，提供改进建议
5. 对每个评分项使用 Chain-of-Thought 推理：先找证据，再匹配规则，再给分数"""

    # 任务说明
    task_prompt = f"""
# 评分任务

## 实验名称
{rubric.get('experiment_name', '')}

## 实验描述
{rubric.get('description', '')}

## 评分标准
"""

    # 添加评分项
    for criterion in rubric.get("criteria", []):
        task_prompt += f"""
### {criterion['name']}（满分 {criterion['max_score']} 分，ID: {criterion['id']}）
描述：{criterion.get('description', '')}

评分规则：
"""
        for rule in criterion.get("rules", []):
            task_prompt += (
                f"- {rule['condition']} → {rule['score']}分（{rule['reason']}）\n"
            )

    # 添加文档内容（限制长度）
    full_text = document.get("full_text", "")
    if len(full_text) > 6000:
        # 截断：保留前后各 2500 字符
        full_text = (
            full_text[:2500]
            + "\n\n[...文档内容已截断，仅展示前后部分...]\n\n"
            + full_text[-2500:]
        )

    task_prompt += f"""
## 学生报告内容

### 文本内容
{full_text}
"""

    # 添加图片描述
    images = document.get("images", [])
    if images:
        task_prompt += "\n### 截图描述\n"
        for img in images:
            desc = img.get("description", "无描述")
            context = img.get("context", "")
            task_prompt += f"- 图{img.get('index', 0) + 1}：{desc}（{context}）\n"

    # 添加 Few-shot 示例
    few_shot_examples = rubric.get("few_shot_examples", [])
    if few_shot_examples and options.get("use_examples", True):
        task_prompt += "\n## 评分参考示例\n"
        for i, example in enumerate(few_shot_examples[:2]):
            task_prompt += f"""
示例{i+1}（{example.get('description', '')}）：
- 内容摘要：{example.get('content_summary', '')}
- 预期分数：{example.get('expected_score', '')}
- 优点：{', '.join(example.get('strengths', []))}
- 不足：{', '.join(example.get('weaknesses', []))}
"""

    # 添加评分提示
    grading_tips = rubric.get("grading_tips", [])
    if grading_tips:
        task_prompt += "\n## 评分提示\n"
        for tip in grading_tips:
            task_prompt += f"- {tip}\n"

    # 输出格式
    task_prompt += """
## 输出要求

请严格按照以下 JSON 格式输出评分结果，不要输出其他内容：

```json
{
    "criterion_scores": [
        {
            "criterion_id": "评分项ID（与标准中的id对应）",
            "criterion_name": "评分项名称",
            "score": 得分数字,
            "reason": "得分理由（50字以内，引用报告中的具体内容）"
        }
    ],
    "detailed_analysis": "详细分析（200字以内）",
    "strengths": ["优点1", "优点2", "优点3"],
    "weaknesses": ["不足1", "不足2"],
    "suggestions": ["建议1", "建议2"],
    "confidence": 0.85,
    "warnings": ["警告信息（如有抄袭嫌疑、内容缺失等）"]
}
```

请开始评分：
"""

    return system_prompt + task_prompt


def main():
    parser = argparse.ArgumentParser(description="构建评分 Prompt")
    parser.add_argument("--rubric", "-r", required=True, help="评分标准 JSON 文件路径")
    parser.add_argument(
        "--document", "-d", required=True, help="解析后的文档 JSON 文件路径"
    )
    parser.add_argument("--output", "-o", help="输出 Prompt 文件路径")
    parser.add_argument(
        "--no-examples", action="store_true", help="不使用 Few-shot 示例"
    )

    args = parser.parse_args()

    with open(args.rubric, "r", encoding="utf-8") as f:
        rubric = json.load(f)

    with open(args.document, "r", encoding="utf-8") as f:
        document = json.load(f)

    options = {"use_examples": not args.no_examples}
    prompt = build_grading_prompt(rubric, document, options)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(prompt)
        print(f"Prompt 已保存到: {args.output}")
        print(f"Prompt 长度: {len(prompt)} 字符")
    else:
        print(prompt)


if __name__ == "__main__":
    main()
