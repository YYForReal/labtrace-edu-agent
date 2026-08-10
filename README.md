# 格物智评 LabTrace

面向高校实验课程教师的图文 Word 原生批改 Agent。教师上传带正文、表格和图片的实验报告，系统生成可定位的评分建议；教师终审后，证据批注、最终成绩和教师评语会写回一份可继续编辑的 Word。

[在线 Demo](https://yywebsite.cn/education/) · [初赛方案 PDF](goaihz/submission/格物智评_LabTrace_GOAI初赛方案.pdf) · [演示视频](goaihz/submission/格物智评_LabTrace_初赛Demo.mp4)

## 核心闭环

1. 读取 DOCX 原生段落、表格和内嵌图片，并保留 Word 段落定位。
2. 按课程 rubric 逐项形成证据化建议和置信度。
3. 低置信度、证据缺失和图片判断必须进入教师终审。
4. 将原生批注、成绩和教师评语写回可编辑 DOCX。
5. 聚合已复核结果，生成班级薄弱维度和讲评建议。

网页顶部提供“教师管理台”入口：原始/批改版 Word、逐项评分、Word 原生批注编号和 `[n]` 证据引用可同屏复核。正文、表格和图片仍保留 `p- / t- / i-` 工程编号，并在网页与批改版 Word 末页生成“证据引用索引”附录；教师点击引用即可回到对应原文位置。

公开 Demo 自带一份合成实验任务书和两份完全合成的学生报告，不含真实姓名、学号、成绩或学生原文。

## 快速开始

环境要求：Python 3.11+、Node.js 20+；DOCX/PDF 基础闭环不需要 LibreOffice，只有旧 `.doc` 转换需要系统安装 LibreOffice。

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cd frontend
npm ci
npm run build
cd ..

LABTRACE_LLM_ENABLED=false \
RUBRICS_DIR="$PWD/goaihz/config/rubrics" \
LABTRACE_RUNTIME_DIR="$PWD/goaihz/runtime/demo_tasks" \
PORT=11315 \
python -m goaihz.app
```

打开 <http://127.0.0.1:11315/>。无密钥模式会明确显示为确定性基线，不冒充模型推理。

## 测试

```bash
python -m unittest discover -s goaihz/tests -p 'test_*.py' -v
python goaihz/scripts/validate_package.py
cd frontend && npm run build
docker build -f goaihz/Dockerfile.production -t labtrace-edu-agent:local .
```

## 启用真实模型

```bash
cp .env.example .env
# 填写 LLM_PROVIDER / LLM_BASE_URL / LLM_API_KEY / LLM_MODEL
set -a && source .env && set +a
python -m goaihz.app
```

报告正文在外部调用前会进行身份信息脱敏；图片默认不发送，只有教师对单次任务显式授权后才发送至多 4 张。AI 只提供建议，正式成绩必须由教师确认。

## 仓库结构

```text
app/                         # 模型适配与工具注册的最小复用层
agent_skills/                # 文档解析、评分校验和 Word 回写工具
frontend/                    # 独立 Vue 3 公共 Demo
goaihz/
  config/rubrics/            # 通用评分标准
  data/synthetic/            # 任务书与合成学生报告
  src/labtrace/              # GradeTrace、隐私和诊断契约
  tests/                     # 端到端闭环测试
  docs/                      # 架构、合规、评测和部署说明
```

## 开源与数据边界

- 项目代码采用 [Apache License 2.0](LICENSE)。
- 不包含原 `GameAssistant` 仓库中的 `_data/`、学期成绩表、真实课程压缩包、学生报告、签名图片和任何 `.env`。
- 本仓库不再内嵌 Anthropic 文档技能的 source-available 脚本；DOCX XML 诊断由标准库实现。
- 商业模型/API 不是开源代码的一部分；可在无密钥确定性模式下复现完整教师闭环。
- 详细说明见 [开源边界](goaihz/docs/open_source_boundary.md) 与 [数据合规说明](goaihz/docs/compliance.md)。

## 许可证

Copyright 2026 Youyi Huang. Licensed under Apache-2.0.
