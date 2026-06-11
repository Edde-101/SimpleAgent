import os
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from skill_manager import SkillManager

mcp = FastMCP("Skill Manager Server")

_base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_AGENT_HOME = Path.home() / ".simpleagent"

manager = SkillManager(
    install_dirs=[
        os.path.join(_base_dir, "skills"),
        str(_AGENT_HOME / "skills"),
    ],
    trash_dir=str(_AGENT_HOME / ".trash"),
    marketplaces_yaml=os.path.join(os.path.dirname(__file__), "skill_marketplaces.yaml"),
)


@mcp.tool()
async def search_skills(keyword: str) -> list[dict]:
    """并行搜索多个技能市场，返回匹配的 skill 列表"""
    results = await manager.search(keyword)
    return [
        {
            "name": r.name,
            "description": r.description,
            "author": r.author,
            "source": r.source,
            "url": r.homepage_url,
        }
        for r in results
    ]


@mcp.tool()
async def get_skill_details(skill_name: str) -> dict | None:
    """获取指定 skill 的详细信息（SKILL.md 完整内容、依赖、环境变量等）"""
    detail = await manager.get_details(skill_name)
    if detail is None:
        return {"error": f"未找到 skill: {skill_name}"}
    return {
        "name": detail.name,
        "description": detail.description,
        "author": detail.author,
        "source": detail.source,
        "version": detail.version,
        "homepage_url": detail.homepage_url,
        "skill_md_content": detail.skill_md_content,
        "dependencies": detail.dependencies,
        "env_vars": detail.env_vars,
    }


@mcp.tool()
async def install_skill(skill_name: str, target_path: str = "") -> dict:
    """下载并安装一个 skill 到本地"""
    target = target_path or None
    result = await manager.install(skill_name, target)
    return {"success": result.success, "path": result.path, "message": result.message}


@mcp.tool()
def list_installed_skills() -> list[dict]:
    """列出所有已安装的 skill"""
    skills = manager.list_installed()
    return [
        {
            "name": s.name,
            "description": s.description,
            "version": s.version,
            "path": s.path,
            "source_type": s.source_type,
        }
        for s in skills
    ]


@mcp.tool()
async def update_skill(skill_name: str) -> dict:
    """更新指定的 skill（git pull 或重新下载）"""
    result = await manager.update(skill_name)
    return {"success": result.success, "path": result.path, "message": result.message}


@mcp.tool()
def remove_skill(skill_name: str, permanent: bool = False) -> dict:
    """删除指定 skill（默认移入回收站）"""
    result = manager.remove(skill_name, permanent)
    return {"success": result.success, "path": result.path, "message": result.message}


if __name__ == "__main__":
    mcp.run(transport="stdio")
