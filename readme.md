# SimpleAgent

一个基于 [LangChain](https://github.com/langchain-ai/langchain) / [LangGraph](https://github.com/langchain-ai/langgraph) 构建的 **深度 AI Agent**，支持多模型切换、子 Agent 委派、长期记忆、MCP 工具协议和终端交互界面。

---

## 特性

### 交互界面

- **终端交互界面 (TUI)** — 基于 Rich + prompt_toolkit 构建，Claude CLI 风格，支持 Markdown 渲染
- **流式思考+回答分离渲染** — 思考过程与正式回答独立显示，支持折叠/展开
- **命令系统** — `/model` 切换模型、`/save` 导出对话、`/history` 查看历史等

### 模型管理

- **多模型支持** — 支持 DeepSeek、Anthropic Claude、OpenAI、Ollama 本地模型及任意 OpenAI 兼容 API
- **模型注册中心** — YAML 配置驱动，支持环境变量注入 API Key，懒加载模型实例
- **模型运行时切换** — `/model <name>` 一键切换模型，对话历史不丢失

### Agent 能力

- **子 Agent 系统** — 动态创建/删除/委派子 Agent（`dtask`、`add_subagent`、`delete_subagent`），配置持久化到磁盘，即时生效无需重启
- **Skills 技能机制** — 可插拔的技能系统，内置文件搜索 (`/file-search`)、问题优化 (`prompt-optimizer`) 等技能，支持自定义扩展
- **任务规划协议** — 复杂任务先自动生成执行计划，等待用户确认后逐步执行（Plan-and-Execute 架构）
- **工具重试机制** — 可配置的指数退避重试策略，故障不中断执行

### 记忆与上下文

- **长期记忆** — 基于 ChromaDB + Embedding 的向量记忆系统，支持记忆存储 (`remember`)、语义召回 (`recall`)、匹配删除 (`forget`)
- **用户画像自动注入** — 每次对话前自动检索相关记忆，将用户偏好和背景信息注入系统提示词
- **对话状态持久化** — 基于 LangGraph Checkpointer 的对话历史管理，切换模型不丢失上下文

### 安全防护

- **Prompt 注入防护** — 检测并阻断 "ignore previous instructions" 等 10+ 种注入模式
- **PII 双向检测** — 输入/输出端均检测手机号、身份证、银行卡、API Key 等敏感信息并自动拦截
- **HITL 中断确认** — 对写文件、编辑、执行命令、删除文件等危险操作弹出人工确认面板

### 工程化

- **启动健康检查** — 启动时自动检测 LLM 模型、Embedding 服务、MCP 服务器、ChromaDB 的连通性
- **对话持久化** — `/save` 保存对话为 Markdown 文件，思考过程以 `<details>` 折叠，完整保留工具调用记录
- **执行追踪** — JSONL 格式全量回调追踪（LLM/Chain/Tool 起止事件、token 用量、错误记录）
- **MCP 工具协议** — 支持 Model Context Protocol 工具接入，通过 stdio 通信扩展外部工具
- **系统提示词模板** — 外部 Markdown 文件定义系统提示词，修改后无需改代码即可生效

---

## 快速开始

### 环境要求

- Python >= 3.10
- pip

### 安装

```bash
git clone https://github.com/Edde-101/SimpleAgent.git
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
│   ├── calc_server.py       # MCP 数学工具服务器
│   └── tools.py             # 额外工具（网络搜索等）
├── skills/                  # Agent 技能
│   ├── file-search/         # 文件搜索技能
│   ├── prompt-optimizer/    # 问题理解与优化技能
│   └── edit/                # 编辑技能
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

## Skills 技能机制

Skills 是 Agent 的可插拔能力模块。每个 Skill 包含一个 `SKILL.md` 描述文件，Agent 启动时自动加载 `skills/` 目录下所有技能。用户可通过 `/<skill-name>` 在对话中直接调用。

### 内置技能

| 技能 | 调用方式 | 功能 |
| ---- | ---- | ---- |
| `file-search` | `/file-search <keyword>` | 在用户主目录递归搜索文件名包含关键词的文件 |
| `prompt-optimizer` | `/prompt-optimizer` | 深度理解用户意图，执行「问题解构 → 意图对齐 → 回答构建 → 质量自检」四阶段优化 |
| `edit` | `/edit` | 编辑文件内容 |

### 添加自定义技能

在 `skills/` 下创建目录，包含 `SKILL.md`（技能定义）和可选的 Python 实现文件（如 `file_search.py`）。`SKILL.md` 头部 YAML 定义技能名称、描述和参数：

```markdown
---
name: my-skill
description: 我的自定义技能描述
user-invocable: true
argument-hint: "[keyword]"
---

# 技能名称

技能详细说明...
```

创建后无需重启，Agent 自动识别并注册。

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

Agent 通过中间件层实现横切关注点，处理流程为：`输入 → MemoryMiddleware → GuardMiddleware → 模型 → GuardMiddleware → PIIMiddleware → 输出`。

### GuardMiddleware（核心安全守卫）

| 能力 | 说明 |
| ---- | ---- |
| **Prompt 注入防护** | 拦截 "ignore previous instructions"、"system prompt:"、"pretend you are" 等 10+ 种注入模式 |
| **PII 输出检测** | 正则扫描模型输出中的手机号、身份证、银行卡、API Key，命中则替换为拦截提示 |
| **用户画像注入** | 每次对话前从 ChromaDB 语义召回相关记忆 + 用户偏好，拼接为用户画像文本注入系统提示词 |
| **任务规划注入** | 在系统提示词中插入 Plan-and-Execute 协议指令，引导 Agent 对复杂任务先规划再执行 |

### MemoryMiddleware

自动注入全局（`~/.deepagent/AGENTS.md`）和项目级（`.deepagent/AGENTS.md`）的 Agent 配置指令。

### PIIMiddleware

基于可配置正则的 API Key 检测层，对输入和输出双向扫描，命中则阻断。默认检测模式：`sk-[a-zA-Z0-9]{32}`。

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
