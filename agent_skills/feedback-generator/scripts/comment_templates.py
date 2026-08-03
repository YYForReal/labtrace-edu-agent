#!/usr/bin/env python3
"""
预设评语模板库
从前代批改工具的 24 个快速评语提炼为结构化评语词库
"""

import json
import argparse

# 预设评语词库
COMMENT_TEMPLATES = {
    # ===== 通用肯定类 =====
    "praise_completion": [
        "实验完成度较高，基本达到了实验要求",
        "较好地完成了本次实验的核心内容",
        "实验任务完成情况良好，展现了扎实的基础",
    ],
    "praise_report": [
        "报告结构清晰，图文并茂",
        "实验报告撰写认真，步骤描述详细",
        "报告格式规范，内容组织有条理",
    ],
    "praise_code": [
        "代码实现完整，功能运行正确",
        "代码结构清晰，命名规范",
        "代码逻辑清晰，有良好的编程习惯",
    ],
    "praise_creativity": [
        "有自己的思考和创新点",
        "在实验基础上进行了有意义的扩展",
        "展现了较强的独立思考能力",
    ],
    "praise_detail": [
        "对实验细节把控得当",
        "截图清晰完整，展示了关键步骤",
        "对参数配置的理解较为深入",
    ],
    # ===== 通用不足类 =====
    "weakness_brief": [
        "实验报告内容较为简略，缺少详细的步骤描述",
        "报告内容偏少，建议增加更多实验过程的记录",
        "报告篇幅较短，部分内容一笔带过",
    ],
    "weakness_screenshot": [
        "截图不够清晰或缺少关键步骤的截图",
        "缺少运行效果截图，无法直观看到实验结果",
        "截图标注不足，建议对关键部分进行标注说明",
    ],
    "weakness_code": [
        "代码注释不足，可读性有待提高",
        "代码缺少必要的注释和说明",
        "部分代码逻辑可以进一步优化",
    ],
    "weakness_reflection": [
        "缺少实验总结和心得体会",
        "实验反思部分较为薄弱，建议深入思考",
        "缺少对实验过程中遇到问题的分析和解决方法",
    ],
    "weakness_incomplete": [
        "部分实验要求未完成",
        "核心功能实现不完整，存在缺失",
        "实验内容与要求有一定差距",
    ],
    # ===== 鼓励类结尾 =====
    "encourage_general": [
        "继续保持，期待你在后续实验中的精彩表现",
        "总体来看有不错的基础，继续加油",
        "本次实验表现不错，相信后续会更加出色",
    ],
    "encourage_improvement": [
        "虽然还有提升空间，但已经展现了不错的学习态度",
        "基础已经打好，在细节上再下功夫会更好",
        "建议多参考教程和文档，相信下次会更好",
    ],
    "encourage_struggling": [
        "不要气馁，游戏开发需要循序渐进的学习过程",
        "建议课后多花时间练习，有问题可以及时请教",
        "基础还需加强，建议从教程的基础部分重新巩固",
    ],
    # ===== 严格类 =====
    "strict_attitude": [
        "请认真对待实验报告，这是巩固知识的重要环节",
        "报告质量需要显著提升，请投入更多精力",
        "实验态度有待改进，请认真完成每个环节",
    ],
    "strict_code": [
        "代码质量需要显著提升，建议重新阅读编码规范",
        "代码存在明显问题，需要进行较大改进",
        "请注意代码的规范性和可维护性",
    ],
    "strict_gap": [
        "实验内容与要求差距较大，建议课后补充练习",
        "核心功能未能实现，需要重新审视实验要求",
        "实验完成度不足，建议认真阅读实验指导书",
    ],
    # ===== 游戏开发专项 =====
    "gamedev_scene": [
        "场景搭建展现了良好的空间设计意识",
        "建议优化场景的光照和摄像机配置",
        "场景层级组织需要改进，建议使用空对象进行分组管理",
    ],
    "gamedev_component": [
        "对 Unity 组件系统的理解较为到位",
        "组件使用基本正确，但参数配置可以更精细",
        "建议深入理解各组件的属性和交互方式",
    ],
    "gamedev_script": [
        "脚本编写规范，展现了良好的 C# 编程能力",
        "建议在脚本中添加更多错误处理和边界检查",
        "脚本功能实现正确，但结构可以进一步优化",
    ],
}


def get_templates(style="standard", score=None, categories=None):
    """
    根据风格和分数获取适用的评语模板

    Args:
        style: encouraging / standard / strict
        score: 总分（用于自动选择模板）
        categories: 指定的模板类别列表

    Returns:
        dict: 分类的评语模板
    """
    if categories:
        return {k: v for k, v in COMMENT_TEMPLATES.items() if k in categories}

    selected = {}

    if style == "encouraging" or (score is not None and score < 60):
        selected.update(
            {
                "praise": COMMENT_TEMPLATES.get("praise_completion", [])[:1],
                "weakness": COMMENT_TEMPLATES.get("weakness_brief", [])[:1],
                "closing": COMMENT_TEMPLATES.get("encourage_struggling", []),
            }
        )

    elif style == "strict" or (score is not None and score >= 90):
        selected.update(
            {
                "praise": COMMENT_TEMPLATES.get("praise_code", [])[:1],
                "weakness": COMMENT_TEMPLATES.get("strict_code", [])[:1],
                "closing": COMMENT_TEMPLATES.get("strict_attitude", [])[:1],
            }
        )

    else:  # standard
        selected.update(
            {
                "praise": COMMENT_TEMPLATES.get("praise_completion", [])[:2],
                "weakness": COMMENT_TEMPLATES.get("weakness_code", [])[:1]
                + COMMENT_TEMPLATES.get("weakness_reflection", [])[:1],
                "closing": COMMENT_TEMPLATES.get("encourage_general", [])[:1],
            }
        )

    return selected


def main():
    parser = argparse.ArgumentParser(description="获取预设评语模板")
    parser.add_argument(
        "--style", default="standard", choices=["encouraging", "standard", "strict"]
    )
    parser.add_argument("--score", type=float, help="总分")
    parser.add_argument("--all", action="store_true", help="输出全部模板")

    args = parser.parse_args()

    if args.all:
        result = COMMENT_TEMPLATES
    else:
        result = get_templates(args.style, args.score)

    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
