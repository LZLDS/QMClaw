# AGENTS.md — QmClaw 开发约定


## 配置文件

所有配置统一保存在 `qmclaw-server/config/` 目录：

| 文件 | 说明 |
|------|------|
| `session.json` | DataVault session 配置 |
| `experiment_configs.json` | 测控实验配置（函数、绘图命令） |
| `model_configs.json` | LLM 模型配置 |
| `fallback_config.json` | 离线模式配置（offline_mode 配置） |

**API Key 说明**：从环境变量读取，不保存在配置文件中
- `OPENAI_API_KEY`、`MINIMAX_API_KEY`、`ANTHROPIC_API_KEY`、`DEEPSEEK_API_KEY`

## 离线模式

quantum_service 和 analysis_service 支持离线模式，可在 LabRAD 不可用时使用历史数据：

- **配置**：`fallback_config.json` 中的 `offline_mode` 字段
- **模式切换**：POST `/mode` 接口，参数 `{"mode": "online"|"offline"|"auto"}`
  - `online`: 强制使用 LabRAD
  - `offline`: 强制使用离线数据
  - `auto`: 自动切换（LabRAD 断开时自动离线）
- **离线数据**：存放在 `qmclaw-server/data/offline_data/` 目录
- **索引生成**：运行 `python -m services.common.offline_data_provider --generate-index`

## 约定

1. **开发任务用 sub-session 隔离**：不污染主 session 的日常对话
2. **模块化和结构化设计**：分层架构（前端/后端/测控），单一职责，API 优先
3. **前后端服务启停由人控制**：不自行启动或杀死前后端服务，这些操作要由人完成（Express :3002、Next.js :3001）
4. **复杂功能开发前先确认需求**：向用户提问明确需求、优先级、边界条件
5. **AGENTS.md 保持精简**：开发进展写入 `.Codex/progress.md`，AGENTS.md 只保留经用户确认的约定
6. 当一个同样的问题反复出现两次以上，就不要采用直接的思路去解决了，而是增加一些debug信息来辅助解决。
7. 当需求涉及较多修改时，先制定计划，由用户确认后才能执行。
8. 计划模式下，或者用户明确让制定计划的时候，需要多向用户提问，详细了解需求。
9. 当前系统有后端打印日志的过滤器，只有满足特定声明逻辑的日志才能被打印到后端的终端窗口里。所以当你要增加后端日志的时候，需要检查一下后端日志过滤器(Agentic Workflow\qmclaw-server\src\index.ts)。
10. python 用这个：`D:\访问github\deploy\qmclaw\python.exe`（Python 3.11，已装
    qubitclient / matplotlib / numpy / torch / openai）。注意它在**仓库外**
    （`QMClaw-main` 的同级 `deploy\` 目录）；系统自带的 `D:\anacanda\python.exe`
    是 3.7，跑不了要求 3.10+ 的 vendor 包。
11. **推送由人发起**：改动可以本地提交，但 `git push` 必须等用户明确说"推"才执行，不要主动推送。
12. **提交身份固定**：本仓库用 `user.name = LZLDS`、
    `user.email = 331927507+LZLDS@users.noreply.github.com`（noreply，避免把真实邮箱
    写进公开仓库的提交元数据）。已设在 `.git/config`（仓库级，非全局）。
13. **不外传本地环境信息**：内网/服务地址、真实 qubit 名、离线数据条数与规模、
    设备会话路径等，一律不进仓库。文档里用 `<lqcs-host>`、`<nnscope-host>`、`qXXX`
    这类占位符；`.gitignore` 已挡住 `qubitclient.json` 与 `data/`。

# Compaction 压缩规则（自动压缩时生效）
## 摘要必须保留内容
1. 项目架构：QMC Pro / QMC Claw微服务分层定义、各个微服务调用关系（Agent、Workflow、Quantum、Analysis、Image、QubitClient）
2. 关键技术决策：自动驾驶类比的规则引擎+大模型混合方案
3. 未完成任务清单、当前开发阶段
4. 核心代码接口定义、重要实验测控逻辑


## 需要简化/丢弃
1. 反复调试的中间失败日志、重复报错
2. 临时探索性的非核心讨论
3. 无关闲聊内容
4. 确认已修复的bug