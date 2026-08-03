# LabTrace 生产部署手册

目标地址：`https://yywebsite.cn/education/`
部署分支：`main`
部署形态：独立只读容器 + 现有共享 Nginx 路由
应用监听：`172.17.0.1:8792 → container:11315`

## 1. 容量结论

生产机为 2 vCPU、3.8 GiB 内存，检查时约 2.8 GiB 可用、磁盘约 25 GiB 可用。当前版本的实测与限制如下：

| 环节 | 观测/限制 | 结论 |
|---|---:|---|
| Vue 生产构建 | 峰值约 0.80 GiB RSS | 在本地/CI 构建，避免与服务器业务争抢 |
| FastAPI + MiniMax SDK 空闲 | 约 120–180 MiB RSS | 可用 |
| 完成一次 DOCX + 真实模型闭环后 | 约 180–350 MiB RSS | 远端推理，不在本机加载模型权重 |
| 容器内存上限 | 1 GiB | 为异常 PDF/OCR 留出余量 |
| 并发评分 | 2 | 与 2 核服务器匹配 |
| 上传上限 | 25 MiB；DOCX 解压后 100 MiB | 防止异常压缩包挤占内存 |

因此当前机器可运行竞赛公开 Demo。MiniMax-M3 通过 HTTPS 远端推理，不需要服务器加载模型权重；本机内存主要用于文档解压、图片 Base64、请求 JSON 和 Word 输出。保守估算常态占用 180–350 MiB，双任务解析峰值建议按 600–900 MiB 预留。服务器没有 swap，故不在服务器执行 Node 前端构建，并强制容器 `mem_limit: 1g`。若未来改为本地部署 7B/8B 量化模型，这台 3.8 GiB 机器不适合，至少应准备 12–16 GiB 内存或独立 GPU 推理节点。

## 2. 发布前门槛

1. 当前分支必须是 `main`（可用 `LABTRACE_DEPLOY_BRANCH` 显式覆盖）；
2. `origin/main` 必须与本地待部署提交完全一致；
3. 通过单元测试、前端构建、隐私扫描与提交包校验；
4. 前端必须使用 `VITE_PUBLIC_BASE=/education/` 构建；
5. 公开样例只能使用仓库内合成材料；
6. 禁止把 SSH 密码、API 密钥或真实学生数据写入仓库和镜像。

生产模型变量保存在服务器 `/etc/labtrace/labtrace.env`，目录权限 `0700`、文件权限 `0600`，只包含 `LLM_PROVIDER`、`LLM_BASE_URL`、`LLM_API_KEY` 和 `LLM_MODEL`。默认部署脚本会从仓库根目录未提交的 `.env` 提取并通过 SSH 覆盖该文件；也可用 `LABTRACE_MODEL_ENV_FILE=/secure/path/model.env` 指定来源。若服务器已有受管配置，可设置 `LABTRACE_SYNC_MODEL_ENV=false`，脚本只检查远端文件存在。

## 3. 应用发布

脚本采用“提交归档 + 本地生成前端 + 远端构建镜像 + 不可变 release 目录”的方式：

```bash
bash goaihz/scripts/deploy_production.sh
```

脚本本身不保存认证信息，也不会打印模型变量。优先使用 SSH 密钥或人工交互认证，不得把密码作为命令行参数提交。

发布后先在服务器验证：

```bash
curl -fsS http://172.17.0.1:8792/health
docker inspect --format '{{.State.Health.Status}}' labtrace-goaihz
docker stats --no-stream labtrace-goaihz
```

## 4. 首次接入 Nginx

只在 `yywebsite.cn` 对应的现有 `server` 块中加入
`goaihz/deploy/nginx.education.conf` 的两个 location。修改前备份：

```bash
cp /home/hyy/nginx.conf /home/hyy/nginx.conf.before-labtrace
docker exec nginx_server nginx -t
docker exec nginx_server nginx -s reload
```

必须先通过 `nginx -t`，再 reload。不得覆盖其他项目的 location。

## 5. 公网验收

至少验证：

```text
GET  /education/
GET  /education/health
GET  /education/labtrace-api/bootstrap
GET  /education/labtrace-api/sample/assignment-template
GET  /education/labtrace-api/sample/allergen
GET  /education/labtrace-api/sample/game-dev
POST /education/labtrace-api/grade
POST /education/labtrace-api/review
GET  /education/labtrace-api/tasks/{id}/download?kind=trace
DELETE /education/labtrace-api/tasks/{id}
```

浏览器验收还需检查所有 JS/CSS 请求均在 `/education/assets/` 下返回 200，顶部显示 `MiniMax 真实 Agent`，任务书与两份合成报告均可下载/载入，真实模型返回动态分数与证据链，教师复核、下载和立即删除能够闭环。过敏原 68 与游戏开发 75 仅作为关闭模型后的确定性回归基线，不作为生产模型固定结果。

## 6. 回滚

应用版本由镜像标签和 `/opt/labtrace.release-<commit>` 固定。回滚时：

1. 找到上一版 release 与镜像标签；
2. 将 `/opt/labtrace-current` 指回上一版；
3. 使用上一镜像执行 compose up；
4. 验证内网健康和公网闭环；
5. 仅在确认新版本无恢复价值后再清理镜像或 release。

不要删除当前可用 release；不要用 `docker system prune`，服务器上还运行其他项目。

## 7. 数据与安全

- 容器以 UID 10001 非 root 运行，根文件系统只读，移除全部 Linux capabilities；
- 仅 `/var/lib/labtrace/demo_tasks` 可写；
- 任务默认 24 小时过期，页面提供立即删除；
- 浏览器响应不返回服务器绝对路径；
- 上传文件做扩展名、魔数、DOCX 结构、条目数和解压大小校验；
- 公共接口按来源 IP 限流，并限制最多两个评分任务并行；
- Cloudflare 负责公网 HTTPS，应用容器不保存证书。
- 模型密钥只存在于宿主机受限环境文件并由 Compose 运行时注入，不进入 Git、release 目录、镜像层或浏览器响应；
- 默认只发送自动脱敏后的有界文本证据，图片二进制需教师逐任务勾选授权；
- 模型超时、额度耗尽、传输错误或输出契约失败都会在任务中显示降级状态。
