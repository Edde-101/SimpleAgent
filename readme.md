# SimpleAgent

一个基于 [LangChain](https://github.com/langchain-ai/langchain) / [LangGraph](https://github.com/langchain-ai/langgraph) 构建的 **深度 AI Agent**，支持多模型切换、子 Agent 委派、长期记忆、MCP 工具协议和终端交互界面。

---

## 特性

- **终端交互界面 (TUI)** — 基于 Rich + prompt_toolkit 构建，Claude CLI 风格，支持 Markdown 渲染、流式输出、思考过程回显
- **多模型支持** — 通过 YAML 配置文件管理模型，支持 DeepSeek、Anthropic Claude、OpenAI、Ollama 本地模型及任意 OpenAI 兼容 API
- **子 Agent 系统** — 动态创建/删除/委派子 Agent，配置即时生效并持久化到磁盘
- **长期记忆** — 基于 ChromaDB + Embedding 的向量记忆系统，支持记忆存储 (remember)、语义召回 (recall)、匹配删除 (forget)
- **MCP 工具协议** — 支持 Model Context Protocol 工具接入，可扩展外部工具
- **HITL 中断确认** — 对危险操作（写文件、编辑、执行命令、删除）弹出人工确认面板
- **安全中间件** — PII 检测/阻断 + 操作守卫 + 记忆中间件
- **启动健康检查** — 启动时自动检测 LLM 模型、Embedding 服务、MCP 服务器、ChromaDB 的连通性
- **模型运行时切换** — `/model <name>` 一键切换模型，对话历史不丢失
- **对话持久化** — 支持保存对话为 Markdown 文件，包含思考过程和工具调用记录
- **工具重试机制** — 可配置的指数退避重试策略，故障不中断执行
- **执行追踪** — JSONL 格式的调用链 tracer，便于调试和分析

---

## 快速开始

### 环境要求

- Python >= 3.10
- pip

### 安装

```bash
https://github.com/Edde-101/SimpleAgent.git
cd SimpleAgent

# 创建虚拟环境
python -m venv venv
source venv/bin/activate  # Linux/macOS
venv\Scripts\activate     # Windows

# 安装依赖
pip install -r requirements.txt
```

### 配置

复制环境变量模板并填入你的 API Key：

```bash
cp .env.example .env
```

按需编辑 `.env`：

```env
# DeepSeek
DEEPSEEK_KEY=sk-xxx
DEEPSEEK_URL=https://api.deepseek.com/v1

# Anthropic Claude
ANTHROPIC_KEY=sk-ant-xxx

# OpenAI
OPENAI_KEY=sk-xxx

# 阿里云 / 任意 OpenAI 兼容 API
ALI_KEY=sk-xxx
ALI_URL=https://dashscope.aliyuncs.com/compatible-mode/v1

# Embedding
EMBEDDING_KEY=sk-xxx
EMBEDDING_URL=https://api.example.com/v1

#TAVILY 搜索工具
TAVILY_API_KEY=xxx
```

模型配置文件 [models.yaml](models.yaml) 中可添加或修改模型条目。

### 启动

```bash
# TUI 界面（推荐）
python main.py

# 命令行模式
python deep_agent.py
```

启动后会自动运行健康检查，确保所有组件就绪后进入对话。

---

## 使用指南

### TUI 命令

| 命令 | 说明 |
| ---- | ---- |
| `/help` | 显示帮助 |
| `/clear` | 清空屏幕 |
| `/model [name]` | 查看或切换模型 |
| `/save` | 保存对话记录为 Markdown |
| `/history` | 查看本轮对话历史摘要 |
| `/exit` | 退出程序 |

### 快捷键

| 按键 | 说明 |
| ---- | ---- |
| `Enter` | 发送消息 |
| `Alt + Enter` | 消息中换行 |
| `Ctrl + C` | 中断 AI 生成 |
| `Ctrl + D` | 退出程序 |
| `↑ / ↓` | 浏览输入历史 |

### 模型切换

````text
# models.yaml 中配置的模型均可在运行时切换
/models.yaml            # 列出可用模型
/model <model-name>     # 切换到指定模型
````

---

## 项目结构

```
SimpleAgent/
├── main.py                  # TUI 入口
├── deep_agent.py            # Agent 核心逻辑
├── models.yaml              # 模型配置
├── models/                  # 模型注册中心
│   └── model_registry.py
├── tui/                     # 终端 UI
│   └── chat_tui.py          # Rich + prompt_toolkit 界面
├── memory/                  # 长期记忆
│   ├── memory_store.py      # remember / recall / forget 工具
│   ├── memory.py            # Checkpointer
│   └── chroma_db/           # ChromaDB 持久化目录
├── middleware/               # 中间件
│   ├── memory_middleware.py  # MemoryMiddleware + PIIMiddleware
│   └── guard_middleware.py   # 操作守卫
├── tools/                   # 工具模块
│   ├── subagent_tool.py     # 子 Agent 管理工具
│   └── tool_wrapper.py      # 工具重试包装器
├── mcp/                     # MCP 工具协议
├── skills/                  # Agent 技能
├── prompt/                  # 系统提示词
├── traces/                  # 执行追踪日志
├── tests/                   # 测试
└── .deepagent/              # Agent 运行时目录
    ├── AGENTS.md            # 项目级 Agent 配置
    └── subagents/           # 持久化子 Agent 配置
```

---

## 子 Agent 系统

主 Agent 可以将任务委派给专门的子 Agent。子 Agent 通过 JSON 文件定义并以持久化方式管理。

### 创建子 Agent

在对话中直接通过 `add_subagent` 工具创建，或手动在 `.deepagent/subagents/` 下放置 JSON 文件：

```json
{
  "name": "code-reviewer",
  "description": "审查代码变更，检查安全漏洞和代码质量",
  "system_prompt": "你是一位资深代码审查员。请仔细审查以下代码...",
  "tools": ["read_file", "search_code"],
  "interrupt_on": { "edit_file": true }
}
```

创建后立即生效，无需重启。

### 委派任务

Agent 会自动识别适合委派的任务并调用 `dtask` 工具，你也可以在对话中显式要求将某个任务委派给指定子 Agent。

---

## 记忆系统

基于 ChromaDB 向量数据库 + Embedding 模型的三重记忆操作：

| 工具 | 功能 |
| ---- | ---- |
| `remember` | 将用户偏好、决策、背景信息存入长期记忆 |
| `recall` | 语义搜索相关记忆（支持相关度排序） |
| `forget` | 精确或语义匹配删除记忆 |

记忆在后续对话会话中自动生效，Agent 会在处理请求前检索相关历史记忆。

---

## 中间件

| 中间件 | 功能 |
| ------ | ---- |
| `MemoryMiddleware` | 注入全局 + 项目级 AGENTS.md 配置 |
| `PIIMiddleware` | 检测并阻断 API Key 等敏感信息的输入/输出 |
| `GuardMiddleware` | 操作守卫，对危险操作启用 HITL 确认 |

---

## 扩展

### 添加新模型

编辑 [models.yaml](models.yaml)，添加新的模型条目：

```yaml
models:
  my-model:
    provider: openai_compatible
    model: your-model-name
    api_key: ${MY_API_KEY}
    base_url: ${MY_BASE_URL}
```

### 添加新工具

在 `tools/` 目录下创建新的工具模块，使用 `@tool` 装饰器定义工具函数，然后在 `deep_agent.py` 的 `start_agent()` 中注册。

### 添加新技能

在 `skills/` 目录下添加技能文件，Agent 启动时会自动加载。

### MCP 工具

在 MCP 服务器文件中定义新工具，Agent 启动时会通过 MCP 协议自动发现并接入。

---

## 技术栈

- [LangChain](https://github.com/langchain-ai/langchain) / [LangGraph](https://github.com/langchain-ai/langgraph) — Agent 框架
- [DeepAgents](https://github.com/langchain-ai/deepagents) — 深度 Agent 构建库
- [ChromaDB](https://github.com/chroma-core/chroma) — 向量数据库
- [Rich](https://github.com/Textualize/rich) + [prompt_toolkit](https://github.com/prompt-toolkit/python-prompt-toolkit) — 终端 UI
- [MCP](https://modelcontextprotocol.io/) — Model Context Protocol

---

## License

MIT
