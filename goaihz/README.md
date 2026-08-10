# 格物智评 LabTrace

面向高校教师的实验报告证据化批改 Agent，也是本仓库参加 GOAI 2026「无界应用 / AI+教育」赛道的独立工作区。

本项目由既有 `GameAssistant` 能力裁剪并迁移到独立开源仓库。参赛版的核心交付不是聊天框里的一段评分，而是教师可以继续编辑、归档和发回学生的 Word：

1. 教师导入实验要求并确认评分标准。
2. Agent 解析图文 Word / PDF 中的正文、表格、图片、代码与结果证据。
3. Agent 按 rubric 逐项评分，每个判断关联可定位证据和置信度。
4. 低置信度、证据缺失或高风险结果进入教师复核队列。
5. 教师确认或调整后，系统把证据批注、成绩和教师评语写回原 Word。
6. 系统聚合班级维度表现，为讲评课和下一轮教学提供学情诊断。

教师始终拥有最终裁量权。

> 别的 Agent 给教师一段回答，格物智评交还一份已经完成证据批注、成绩填写和教师评语回填的可编辑 Word。

## 当前状态

本仓库已经形成一条“真实模型在线 + 确定性离线降级”的参赛闭环：

- 一套跨理工科实验报告的通用 rubric；
- 真实 DOCX 结构解析和 `evidence_id` 证据账本，图片可定位回原 Word 段落；
- 使用运行时 MiniMax-M3 配置的真实结构化评分适配器；
- 教师可上传 2–12 维、总分 1–200 的真实课程 rubric JSON；
- 外部模型调用前自动脱敏；图片默认不外发，教师可为单次任务授权至多 4 张、合计至多 6 MiB；
- 六维评分建议、分数校验、低置信度复核门槛；
- 教师调整、审计事件、原位证据批注、成绩与教师评语回写；
- Web 教师管理台同屏展示真实 Word、逐项评分、原生批注和可点击的 `[n]` 证据定位；
- `p- / t- / i-` 内部证据号映射为教师可读的 Word 段落、表格和图片位置，并将科研式引用索引写入 Word 末页附录；
- 固定课程模板可填写既有成绩/评语区；任意 Word 则保留原文、表格和图片，并追加可编辑的标准批改页；
- 仅聚合已复核成绩的班级学情诊断；
- `/education/` 生产入口和 `/labtrace-api` 独立 API；
- 一份 Unity 实验任务书，以及过敏原 ELISA、Unity 游戏开发两份公开合成图文报告；
- 24 小时自动过期、立即删除、上传结构校验、限流与并发保护；
- 人工合成报告、真实课程报告受控烟测、图文 Word 结构验证、隐私扫描、18 项回归测试和初赛提交材料。

生产环境使用 MiniMax-M3 生成逐项建议，输出必须通过 `GradeTrace` 的维度、分值、证据引用和总分校验；JSON 不合法时最多追加两次带具体错误的修复请求，超时、额度耗尽或契约失败会显式标记并降级。`LABTRACE_LLM_ENABLED=false` 可切换到无密钥确定性模式，离线闭环不会冒充真实模型推理。详见 [架构与迁移说明](docs/architecture.md)。

## 快速验证

在仓库根目录创建独立环境后执行：

```bash
.venv/bin/python goaihz/scripts/validate_package.py
.venv/bin/python -m unittest discover -s goaihz/tests -v
.venv/bin/python goaihz/scripts/run_diagnosis.py
```

先构建前端，再启动完整本地 Demo：

```bash
cd frontend
npm install
npm run build
cd ..
RUBRICS_DIR="$PWD/goaihz/config/rubrics" \
LABTRACE_RUNTIME_DIR="$PWD/goaihz/runtime/demo_tasks" \
LABTRACE_LLM_ENABLED=false \
PORT=11315 \
.venv/bin/python -m goaihz.app
```

浏览器打开：

`http://127.0.0.1:11315/`

公网演示地址：

<https://yywebsite.cn/education/>

开发态也可以分别启动 `.venv/bin/python -m goaihz.app` 和
`cd frontend && npm run dev`，再访问 `http://127.0.0.1:3000/labtrace`。

Docker 方式：

```bash
cp goaihz/.env.example goaihz/.env
docker compose -f goaihz/docker-compose.yml up --build
```

若要启用真实模型，在未提交的 `.env` 中填写同名
`LLM_PROVIDER / LLM_BASE_URL / LLM_API_KEY / LLM_MODEL`。密钥不得进入镜像、仓库、演示材料或浏览器响应。

生产构建、容量结论、Nginx 接入、验收和回滚见
[生产部署手册](docs/deployment_runbook.md)。

## 目录

```text
goaihz/
├── config/rubrics/              # 参赛版通用评分标准
├── data/synthetic/              # 任务书、两份公开合成报告与评测数据
├── docs/                        # 产品、架构、合规、评测和提交材料
├── scripts/                     # 包验证与诊断演示
├── src/labtrace/                # 证据链、隐私与学情诊断模块
├── model_engine.py              # MiniMax 适配、脱敏、结构化校验与降级
├── submission/                  # 初赛 PPT/PDF、作品简介与提交清单
├── tests/                       # 独立可运行测试
├── docker-compose.yml           # 参赛版运行配置
└── project.json                 # 机器可读的项目与开源边界清单
```

## 赛道适配结论

官方手册允许自选模型、Agent 框架和工具，也允许基于既有项目继续开发。参赛材料必须说明原项目来源、新增贡献、数据授权、隐私保护、人工确认、模型或商业 API 依赖、可替代方案与复现方式。

因此当前技术路线保留已经验证过的 FastAPI + Vue 3 + 显式工具调用架构，并通过兼容协议接入模型服务。参赛重点放在真实任务闭环、证据可追溯、评测、教师终审和开放复用。

## 文档入口

- [产品与赛道定位](docs/product.md)
- [闭环演示方案](docs/closed_loop_demo_plan.md)
- [初版工程计划](docs/engineering_plan_v1.md)
- [技术架构与迁移说明](docs/architecture.md)
- [数据、安全与教育边界](docs/compliance.md)
- [评测方案](docs/evaluation.md)
- [初赛提交草案](docs/preliminary_submission.md)
- [三分钟 Demo 脚本](docs/demo_script.md)
- [赛事规则核对与时间风险](docs/competition_notes.md)
- [单人参赛队名建议](docs/team_names.md)
- [开源与第三方边界](docs/open_source_boundary.md)
