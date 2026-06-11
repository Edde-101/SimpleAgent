import os
from pathlib import Path
from config import (
    AGENT_HOME,
    AGENT_TEMP,
    AGENT_SKILLS,
    AGENT_MCPS,
    AGENT_SUBAGENTS,
    AGENT_TRASH,
    VIRTUAL_TEMP,
    VIRTUAL_SKILLS_HOME,
    VIRTUAL_MCPS_HOME,
    VIRTUAL_SUBAGENTS,
    LOCAL_SKILLS,
    LOCAL_MCP,
)

general_prompt = """
 # 角色
 你是人工智能助手。

 # 行为准则
 1. 简洁精准，不啰嗦
 2. 不确定时明确说明，不编造
 """

_PROMPT_DIR = Path(__file__).parent

# ── 从 config 导入的路径（以 _ 前缀别名保持模块内部兼容）──
_AGENT_HOME = AGENT_HOME
_AGENT_TEMP = AGENT_TEMP
_AGENT_SKILLS = AGENT_SKILLS
_AGENT_MCPS = AGENT_MCPS
_AGENT_SUBAGENTS = AGENT_SUBAGENTS
_AGENT_TRASH = AGENT_TRASH

_LOCAL_TEMP = _AGENT_TEMP.as_posix()  # 如 C:/Users/husc/.simpleagent/temp

_VIRTUAL_TEMP = VIRTUAL_TEMP
_VIRTUAL_SKILLS_HOME = VIRTUAL_SKILLS_HOME
_VIRTUAL_MCPS_HOME = VIRTUAL_MCPS_HOME
_VIRTUAL_SUBAGENTS = VIRTUAL_SUBAGENTS

# ── 项目目录 ──
_PROJECT_DIR = LOCAL_SKILLS.parent
_LOCAL_SKILLS = LOCAL_SKILLS.as_posix()  # 如 D:/.../SimpleAgent/skills
_LOCAL_MCP = LOCAL_MCP.as_posix()

# 盘符根 → 虚拟路径：D:/x/y/z → /x/y/z
_drive_root = os.path.splitdrive(str(_PROJECT_DIR))[0] + "/"
_VIRTUAL_SKILLS = "/" + os.path.relpath(_LOCAL_SKILLS, _drive_root).replace("\\", "/")
_VIRTUAL_MCP = "/" + os.path.relpath(_LOCAL_MCP, _drive_root).replace("\\", "/")


def load_prompt(name: str, **kwargs) -> str:
    try:
        template = (_PROMPT_DIR / f"{name}").read_text(encoding="utf-8")
        for k, v in kwargs.items():
            template = template.replace(f"{{{{{k}}}}}", str(v))
    except FileNotFoundError:
        template = general_prompt
    return template


def get_assistant_prompt(
    local_temp: str | None = None,
    virtual_temp: str | None = None,
    local_skills: str | None = None,
    virtual_skills: str | None = None,
    local_mcp: str | None = None,
    virtual_mcp: str | None = None,
    local_skills_home: str | None = None,
    virtual_skills_home: str | None = None,
    local_mcps_home: str | None = None,
    virtual_mcps_home: str | None = None,
    virtual_subagents: str | None = None,
) -> str:
    """加载系统提示词并注入运行时路径信息"""
    return load_prompt(
        "system_prompt.md",
        local_temp=local_temp or _LOCAL_TEMP,
        virtual_temp=virtual_temp or _VIRTUAL_TEMP,
        local_skills=local_skills or _LOCAL_SKILLS,
        virtual_skills=virtual_skills or _VIRTUAL_SKILLS,
        local_mcp=local_mcp or _LOCAL_MCP,
        virtual_mcp=virtual_mcp or _VIRTUAL_MCP,
        local_skills_home=local_skills_home or _AGENT_SKILLS.as_posix(),
        virtual_skills_home=virtual_skills_home or _VIRTUAL_SKILLS_HOME,
        local_mcps_home=local_mcps_home or _AGENT_MCPS.as_posix(),
        virtual_mcps_home=virtual_mcps_home or _VIRTUAL_MCPS_HOME,
        virtual_subagents=virtual_subagents or _VIRTUAL_SUBAGENTS,
    )


Assistant_PROMPT = get_assistant_prompt()
