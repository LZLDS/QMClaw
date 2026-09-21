# QMClaw Server

量子测控服务后端，基于微服务架构。

## QMClaw架构概览

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           用户层 (Browser)                              │
│                        Next.js (:8081/3001)                             │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼ HTTP/REST + WebSocket
┌─────────────────────────────────────────────────────────────────────────┐
│                        Express 网关 (:3002)                             │
│                    TypeScript + Socket.IO                               │
│    ┌──────────────┬──────────────┬──────────────┬────────────────┐     │
│    │   Gateway    │   Queue      │   Services   │   WebSocket    │     │
│    │   路由代理    │   任务队列    │   服务实现    │   实时通信     │     │
│    └──────────────┴──────────────┴──────────────┴────────────────┘     │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                    ┌───────────────┼───────────────┐
                    ▼               ▼               ▼
            ┌───────────────┐ ┌───────────────┐ ┌───────────────┐
            │  Legacy Mode  │ │   Service     │ │  Workflow     │
            │  (Subprocess) │ │   Proxy       │ │  Orchestrator │
            └───────────────┘ └───────────────┘ └───────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                     Python 微服务层 (3003-3009)                         │
│  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌────────┐ │
│  │quantum  │ │analysis │ │   llm   │ │  agent  │ │  image  │ │  task  │ │
│  │service  │ │service  │ │service  │ │service  │ │service  │ │ queue  │ │
│  │ :3003   │ │ :3004   │ │ :3006   │ │ :3005   │ │ :3007   │ │ :3009  │ │
│  └─────────┘ └─────────┘ └─────────┘ └─────────┘ └─────────┘ └────────┘ │
└─────────────────────────────────────────────────────────────────────────┘
                    │               │               │
                    ▼               ▼               ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                          硬件/外部服务层                                 │
│  ┌───────────────┐  ┌───────────────┐  ┌─────────────────────────────┐  │
│  │   LabRAD      │  │   LLM APIs    │  │      ML Models              │  │
│  │ 量子设备控制   │  │ OpenAI/Claude │  │  PyTorch/ONNX               │  │
│  └───────────────┘  │ DeepSeek/Mini │  └─────────────────────────────┘  │
│                     └───────────────┘                                   │
└─────────────────────────────────────────────────────────────────────────┘



## 服务列表

| 服务 | 端口 | 功能 | 状态 |
|------|------|------|------|
| quantum | 3003 | LabRAD 连接、实验执行、Qubit 管理 | ✅ |
| analysis | 3004 | DataLab 绘图、统计分析 | ✅ |
| agent | 3005 | QuantumAgent、ReAct 推理 | ✅ |
| llm | 3006 | 多 Provider 统一接口 | ✅ |
| image | 3007 | PyTorch/ONNX 推理、图像分类 | ✅ |
| workflow | 3008 | 节点调度、依赖解析 | ⏳ |
| task_queue | 3009 | 任务调度、重试机制 | ⏳ |


## 快速开始

### 1. 安装依赖

```bash
npm install
```

### 2. 配置环境变量

复制 `.env.example` 为 `.env` 并配置：

```bash
MINIMAX_API_KEY=your_api_key
OPENAI_API_KEY=your_api_key
# ...
```

### 3. 启动服务

**开发模式（单体）：**
```bash
npm run dev
```

**微服务模式：**
```bash
# 启动所有微服务
python scripts/start_all_services.py

# 然后启动 Express 网关
npm run dev
```

## 配置

配置文件位于 `config/` 目录：

| 文件 | 说明 |
|------|------|
| `services.json` | 服务配置（含微服务模式开关） |
| `session.json` | DataVault session 配置 |
| `experiment_configs.json` | 测控实验配置 |
| `model_configs.json` | LLM 模型配置 |

### 微服务模式切换

```json
// config/services.json
{
  "mode": {
    "use_microservices": true   // true=微服务, false=legacy
  }
}
```

或通过环境变量覆盖：
```bash
QMCLAW_USE_SERVICES=false
```

## 端口说明

| 端口 | 服务 | 说明 |
|------|------|------|
| 3001 | Next.js | 前端 |
| 3002 | Express | API 网关 |
| 3003-3009 | Python | 微服务 |

## API 端点

### 测控相关
- `GET /sessions` - 获取 DataVault session 列表
- `POST /sessions/switch` - 切换 session
- `GET /qubits` - 获取量子比特列表
- `GET /datasets` - 获取数据集列表
- `POST /api/experiments/run` - 执行实验

### 分析相关
- `POST /api/experiments/run-analysis` - 运行分析
- `GET /datasets/plot` - 绘图

### Agent 相关
- `POST /api/agent/chat` - Agent 对话
- `POST /api/hermes/chat` - Hermes 助手

## 技术栈

- **网关**: Express + TypeScript
- **测控**: Python + LabRAD
- **LLM**: MiniMax / OpenAI / DeepSeek
- **图像**: Python + PyTorch

## 目录结构

```
qmclaw-server/
├── src/
│   └── index.ts           # Express 网关
├── services/
│   ├── quantum_service/   # 测控服务
│   ├── analysis_service/ # 分析服务
│   ├── agent_service/     # Agent 服务
│   ├── llm_service/       # LLM 服务
│   └── image_service/     # 图像服务
├── config/                # 配置文件
├── scripts/               # 启动脚本
└── STATUS.md              # 项目状态
```

## 开发指南

### 添加新的微服务

1. 在 `services/` 下创建新服务目录
2. 实现 HTTP API（端口 3003-3009）
3. 在 `config/services.json` 注册服务
4. 在 `src/index.ts` 添加代理路由

### 添加新的 API 端点

1. 在 `src/index.ts` 添加路由
2. 实现代理逻辑到对应微服务
3. 更新前端 API 调用

## 相关文档

- [项目状态](STATUS.md) - 详细的开发进度和问题追踪
