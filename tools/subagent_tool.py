import json
import os
from pathlib import Path
from uuid import uuid4
from deepagents import create_deep_agent
from langchain.agents import create_agent
from langchain.tools import ToolRuntime, tool
from langchain.messages import HumanMessage, AIMessage

base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SUBAGENT_DIR = os.path.join(base_dir, ".deepagent", "subagents")

_subagent_model = None
_subagent_tools = None
_subagent_checkpointer = None
_subagent_skills = None
_subagent_backend = None
_subagent_middleware = None
_subagent_interrupt_on = None


def init_subagent_runtime(
    model,
    tools,
    checkpointer,
    skills=None,
    backend=None,
    middleware=None,
    interrupt_on=None,
):
    global _subagent_model, _subagent_tools, _subagent_checkpointer
    global _subagent_skills, _subagent_backend, _subagent_middleware, _subagent_interrupt_on
    _subagent_model = model
    _subagent_tools = tools
    _subagent_checkpointer = checkpointer
    _subagent_skills = skills
    _subagent_backend = backend
    _subagent_middleware = middleware
    _subagent_interrupt_on = interrupt_on


def _ensure_dir():
    Path(SUBAGENT_DIR).mkdir(parents=True, exist_ok=True)


@tool
async def dtask(description: str, subagent_type: str, runtime: ToolRuntime):
    """动态委派任务给磁盘上的任意子 Agent（即时生效，无需重启）。"""

    if _subagent_model is None:
        return "错误：子Agent 运行时未初始化，请联系管理员。"
    # 1. 从磁盘读取配置
    config = {}
    try:
        config_path = os.path.join(SUBAGENT_DIR, f"{subagent_type}.json")
        with open(config_path, "r", encoding="utf-8") as f:
            config = json.loads(f.read())
    except (FileNotFoundError, json.JSONDecodeError):
        return f"子Agent '{subagent_type}' 配置不存在或已损坏。"

    if not config.get("system_prompt"):
        return f"子Agent '{subagent_type}' 缺少 system_prompt。"
    # 2. 当场创建 agent
    sub_agent = create_deep_agent(
        model=_subagent_model,
        tools=_subagent_tools,
        checkpointer=_subagent_checkpointer,
        system_prompt=config["system_prompt"],
        skills=_subagent_skills,
        backend=_subagent_backend,
        middleware=_subagent_middleware,
        interrupt_on=_subagent_interrupt_on or {},
    )

    # 3. 执行
    result = await sub_agent.ainvoke(
        {"messages": [HumanMessage(content=description)]},
        config={"configurable": {"thread_id": f"subagent-{subagent_type}-{uuid4()}"}},
    )

    # 4. 提取最后一条 AIMessage 返回
    for msg in reversed(result["messages"]):
        if isinstance(msg, AIMessage) and msg.content:
            return msg.content
    return "子Agent 未返回有效结果。"


def load_subagents_from_disk() -> list[dict]:
    """启动时调用：扫描 subagent 目录，返回 deepagents SubAgent 规格列表。"""
    _ensure_dir()
    subagents = []
    for entry in sorted(Path(SUBAGENT_DIR).iterdir()):
        if entry.suffix != ".json":
            continue
        try:
            data = json.loads(entry.read_text(encoding="utf-8"))
            # 只取 deepagents SubAgent 需要的字段
            spec = {
                "name": data["name"],
                "description": data["description"],
                "system_prompt": data["system_prompt"],
            }
            # 可选字段
            for key in ("tools", "model", "skills", "interrupt_on"):
                if key in data and data[key]:
                    spec[key] = data[key]
            subagents.append(spec)
        except (json.JSONDecodeError, KeyError) as e:
            print(f"[WARN] 跳过损坏的子Agent文件: {entry.name} — {e}")
    return subagents


@tool
def add_subagent(name: str, description: str, system_prompt: str) -> str:
    """创建一个新的子 Agent 并持久化到磁盘。。
    即时生效"。

    Args:
        name: 子Agent 唯一标识符，如 "code-reviewer"
        description: 该子Agent 的职责描述，主Agent 据此判断何时委派
        system_prompt: 子Agent 的系统提示词，包含工具使用指引和输出格式要求
    """
    _ensure_dir()
    filepath = os.path.join(SUBAGENT_DIR, f"{name}.json")
    if os.path.exists(filepath):
        return f"子Agent '{name}' 已存在。如需覆盖请先调用 delete_subagent 删除。"

    config = {
        "name": name,
        "description": description,
        "system_prompt": system_prompt,
    }
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)
    return f"子Agent '{name}' 已创建并保存，立即生效。"


@tool
def delete_subagent(name: str) -> str:
    """删除一个已持久化的子 Agent。

    Args:
        name: 要删除的子Agent 名称
    """
    filepath = os.path.join(SUBAGENT_DIR, f"{name}.json")
    if not os.path.exists(filepath):
        return f"子Agent '{name}' 不存在。"
    os.remove(filepath)
    return f"子Agent '{name}' 已删除，重启后生效。"


@tool
def list_subagents() -> str:
    """列出所有已持久化的子 Agent 及其描述。"""
    _ensure_dir()
    entries = sorted(Path(SUBAGENT_DIR).glob("*.json"))
    if not entries:
        return "当前没有已保存的子Agent。"

    lines = []
    for i, entry in enumerate(entries, 1):
        try:
            data = json.loads(entry.read_text(encoding="utf-8"))
            name = data.get("name", entry.stem)
            desc = data.get("description", "-")
            lines.append(f"{i}. **{name}**: {desc}")
        except json.JSONDecodeError:
            lines.append(f"{i}. **{entry.stem}**: (文件损坏)")
    return "\n".join(lines)
