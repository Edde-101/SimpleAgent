import json
import os
import shutil
from pathlib import Path
from uuid import uuid4
from deepagents import create_deep_agent
from langchain.agents import create_agent
from langchain.tools import ToolRuntime, tool
from langchain.messages import HumanMessage, AIMessage
from config import AGENT_SUBAGENTS, SUBAGENT_WORKSPACE_DIRS

base_dir = str(AGENT_SUBAGENTS.parent.parent)  # myAgent/

# 子Agent 配置存储目录
SUBAGENT_DIR = str(AGENT_SUBAGENTS)

# 旧目录（用于迁移）
_OLD_SUBAGENT_DIR = os.path.join(base_dir, "SimpleAgent", ".deepagent", "subagents")

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


def _ensure_dir(subagent_name: str = None):
    """确保子Agent 目录存在。如果指定名称，同时创建其 workspace 子目录。"""
    Path(SUBAGENT_DIR).mkdir(parents=True, exist_ok=True)
    if subagent_name:
        workspace = Path(SUBAGENT_DIR) / subagent_name
        for sub in SUBAGENT_WORKSPACE_DIRS:
            (workspace / sub).mkdir(parents=True, exist_ok=True)


def _migrate_old_subagents():
    """启动时迁移旧目录 .deepagent/subagents/*.json → _AGENT_HOME/subagents/<name>/config.json"""
    old_dir = Path(_OLD_SUBAGENT_DIR)
    if not old_dir.exists():
        return
    new_dir = Path(SUBAGENT_DIR)
    new_dir.mkdir(parents=True, exist_ok=True)
    for entry in old_dir.glob("*.json"):
        try:
            data = json.loads(entry.read_text(encoding="utf-8"))
            name = data.get("name", entry.stem)
            target_dir = new_dir / name
            target_dir.mkdir(parents=True, exist_ok=True)
            target_file = target_dir / "config.json"
            if not target_file.exists():
                shutil.copy2(str(entry), str(target_file))
                print(f"[MIGRATE] 已迁移子Agent: {name} ({entry.name} → {target_file})")
        except (json.JSONDecodeError, KeyError, OSError) as e:
            print(f"[MIGRATE] 跳过损坏的子Agent文件: {entry.name} — {e}")


@tool
async def dtask(description: str, subagent_type: str, runtime: ToolRuntime):
    """动态委派任务给磁盘上的任意子 Agent（即时生效，无需重启）。"""

    if _subagent_model is None:
        return "错误：子Agent 运行时未初始化，请联系管理员。"
    # 1. 从磁盘读取配置（支持新旧两种结构）
    config = {}
    # 新结构: <name>/config.json
    new_path = os.path.join(SUBAGENT_DIR, subagent_type, "config.json")
    # 旧结构: <name>.json
    old_path = os.path.join(SUBAGENT_DIR, f"{subagent_type}.json")
    try:
        if os.path.exists(new_path):
            with open(new_path, "r", encoding="utf-8") as f:
                config = json.loads(f.read())
        elif os.path.exists(old_path):
            with open(old_path, "r", encoding="utf-8") as f:
                config = json.loads(f.read())
        else:
            return f"子Agent '{subagent_type}' 配置不存在或已损坏。"
    except (json.JSONDecodeError, OSError):
        return f"子Agent '{subagent_type}' 配置不存在或已损坏。"

    if not config.get("system_prompt"):
        return f"子Agent '{subagent_type}' 缺少 system_prompt。"

    # 子Agent 的专属 skills 目录
    subagent_skills_dir = os.path.join(SUBAGENT_DIR, subagent_type, "skills")
    sub_skills = (_subagent_skills or []) + (
        [subagent_skills_dir] if os.path.isdir(subagent_skills_dir) else []
    )

    # 2. 当场创建 agent
    sub_agent = create_deep_agent(
        model=_subagent_model,
        tools=_subagent_tools,
        checkpointer=_subagent_checkpointer,
        system_prompt=config["system_prompt"],
        skills=sub_skills,
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
    """启动时调用：扫描 subagent 目录，返回 deepagents SubAgent 规格列表。

    支持两种结构：
    - 新结构: <name>/config.json (带 workspace 子目录)
    - 旧结构: <name>.json (平铺在根目录，向后兼容)
    """
    # 先迁移旧数据
    _migrate_old_subagents()

    _ensure_dir()
    subagents = []
    root = Path(SUBAGENT_DIR)

    for entry in sorted(root.iterdir()):
        # 新结构: 子目录下的 config.json
        if entry.is_dir():
            config_file = entry / "config.json"
            if config_file.exists():
                try:
                    data = json.loads(config_file.read_text(encoding="utf-8"))
                    spec = _parse_subagent_spec(data)
                    if spec:
                        subagents.append(spec)
                except (json.JSONDecodeError, KeyError) as e:
                    print(f"[WARN] 跳过损坏的子Agent配置: {config_file} — {e}")
        # 旧结构: 平铺 .json 文件（向后兼容）
        elif entry.suffix == ".json":
            try:
                data = json.loads(entry.read_text(encoding="utf-8"))
                spec = _parse_subagent_spec(data)
                if spec:
                    subagents.append(spec)
            except (json.JSONDecodeError, KeyError) as e:
                print(f"[WARN] 跳过损坏的子Agent文件: {entry.name} — {e}")
    return subagents


def _parse_subagent_spec(data: dict) -> dict | None:
    """从配置数据提取 deepagents SubAgent 规格"""
    spec = {
        "name": data["name"],
        "description": data["description"],
        "system_prompt": data["system_prompt"],
    }
    for key in ("tools", "model", "skills", "interrupt_on"):
        if key in data and data[key]:
            spec[key] = data[key]
    return spec


@tool
def add_subagent(name: str, description: str, system_prompt: str) -> str:
    """创建一个新的子 Agent 并持久化到磁盘，即时生效。

    Args:
        name: 子Agent 唯一标识符，如 "code-reviewer"
        description: 该子Agent 的职责描述，主Agent 据此判断何时委派
        system_prompt: 子Agent 的系统提示词，包含工具使用指引和输出格式要求
    """
    # 创建 workspace 目录结构
    _ensure_dir(name)
    config_file = os.path.join(SUBAGENT_DIR, name, "config.json")
    # 兼容旧格式：检查平铺 .json 文件
    old_file = os.path.join(SUBAGENT_DIR, f"{name}.json")
    if os.path.exists(config_file) or os.path.exists(old_file):
        return f"子Agent '{name}' 已存在。如需覆盖请先调用 delete_subagent 删除。"

    config = {
        "name": name,
        "description": description,
        "system_prompt": system_prompt,
    }
    with open(config_file, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)
    return f"子Agent '{name}' 已创建并保存（workspace: {SUBAGENT_DIR}/{name}/），立即生效。"


@tool
def delete_subagent(name: str) -> str:
    """删除一个已持久化的子 Agent。

    Args:
        name: 要删除的子Agent 名称
    """
    # 新结构: 删除整个 workspace 目录
    dirpath = os.path.join(SUBAGENT_DIR, name)
    # 旧结构: 删除平铺 .json 文件
    filepath = os.path.join(SUBAGENT_DIR, f"{name}.json")
    if os.path.isdir(dirpath):
        shutil.rmtree(dirpath, ignore_errors=True)
        return f"子Agent '{name}' 及其 workspace 已删除。"
    elif os.path.exists(filepath):
        os.remove(filepath)
        return f"子Agent '{name}' 已删除。"
    else:
        return f"子Agent '{name}' 不存在。"


@tool
def list_subagents() -> str:
    """列出所有已持久化的子 Agent 及其描述。"""
    _ensure_dir()
    root = Path(SUBAGENT_DIR)
    lines = []
    seen: set[str] = set()

    # 新结构: 子目录下的 config.json
    for d in sorted(root.iterdir()):
        if d.is_dir():
            config_file = d / "config.json"
            if config_file.exists():
                try:
                    data = json.loads(config_file.read_text(encoding="utf-8"))
                    name = data.get("name", d.name)
                    desc = data.get("description", "-")
                    if name not in seen:
                        seen.add(name)
                        lines.append(f"{len(lines) + 1}. **{name}** (workspace): {desc}")
                except json.JSONDecodeError:
                    lines.append(f"{len(lines) + 1}. **{d.name}**: (文件损坏)")

    # 旧结构: 平铺 .json 文件
    for f in sorted(root.glob("*.json")):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            name = data.get("name", f.stem)
            desc = data.get("description", "-")
            if name not in seen:
                seen.add(name)
                lines.append(f"{len(lines) + 1}. **{name}**: {desc}")
        except json.JSONDecodeError:
            pass  # 已在新结构循环中处理

    if not lines:
        return "当前没有已保存的子Agent。"
    return "\n".join(lines)
