"""Agent 统一配置 — 所有路径常量集中定义，其他模块从此导入。"""
import os
from pathlib import Path

# ═══════════════════════════════════════════
# 项目路径（基于本文件位置）
# ═══════════════════════════════════════════

_base_dir = Path(__file__).resolve().parent          # SimpleAgent/
_project_dir = _base_dir.parent                      # myAgent/

# 项目所在盘符根（D:/），作为默认后端的 root_dir
_drive_root = os.path.splitdrive(str(_base_dir))[0] + "/"

# 项目虚拟路径（CompositeBackend 路由用）
PROJECT_VPATH = "/" + os.path.relpath(str(_base_dir), _drive_root).replace("\\", "/") + "/"

# ═══════════════════════════════════════════
# Agent 工作目录（~/.simpleagent/）
# ═══════════════════════════════════════════

AGENT_HOME = Path.home() / ".simpleagent"

# —— 标准化子目录（本地绝对路径） ——
AGENT_TEMP = AGENT_HOME / "temp"
AGENT_SKILLS = AGENT_HOME / "skills"
AGENT_MCPS = AGENT_HOME / "mcps"
AGENT_SUBAGENTS = AGENT_HOME / "subagents"
AGENT_TRASH = AGENT_HOME / ".trash"

# —— 虚拟路径（CompositeBackend 路由：/.simpleagent/ → AGENT_HOME） ——
VIRTUAL_TEMP = "/.simpleagent/temp"
VIRTUAL_SKILLS_HOME = "/.simpleagent/skills"
VIRTUAL_MCPS_HOME = "/.simpleagent/mcps"
VIRTUAL_SUBAGENTS = "/.simpleagent/subagents"

# ═══════════════════════════════════════════
# 项目内置目录
# ═══════════════════════════════════════════

LOCAL_SKILLS = _base_dir / "skills"          # 项目 skills
LOCAL_MCP = _base_dir / "mcp"                # 项目 MCP
LOCAL_MEMORY = _base_dir / "memory"          # 项目 memory
LOCAL_TRACES = _base_dir / "traces"          # 项目 traces
LOCAL_PROMPTS = _base_dir / "prompt"         # 项目 prompts

# ═══════════════════════════════════════════
# 标准化目录列表（供批量创建用）
# ═══════════════════════════════════════════

AGENT_HOME_DIRS = (AGENT_TEMP, AGENT_SKILLS, AGENT_MCPS, AGENT_SUBAGENTS, AGENT_TRASH)

SUBAGENT_WORKSPACE_DIRS = ("temp", "skills", "mcps")
