import asyncio
import os
import re
import shutil
import tempfile
import zipfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
import httpx
import yaml

# ═══════════════════════════════════════════
# 数据类型
# ═══════════════════════════════════════════


@dataclass
class SkillMeta:
    name: str
    description: str
    author: str
    source: str
    homepage_url: str
    version: str = ""


@dataclass
class SkillDetail(SkillMeta):
    skill_md_content: str = ""
    dependencies: list[str] = field(default_factory=list)
    env_vars: list[str] = field(default_factory=list)


@dataclass
class Marketplace:
    name: str
    type: str  # "rest" | "github"
    search_url: str | None = None
    detail_url: str | None = None
    api_key: str | None = None
    query_param: str = "q"  # REST 搜索时用的参数名: q / query / search


@dataclass
class InstallResult:
    success: bool
    path: str
    message: str = ""


@dataclass
class InstalledSkill:
    name: str
    description: str
    version: str
    path: str
    source_type: str  # "git" | "http"


@dataclass
class RemoveResult:
    success: bool
    path: str
    message: str = ""


# ═══════════════════════════════════════════
# 默认市场
# ═══════════════════════════════════════════

DEFAULT_MARKETPLACES: list[Marketplace] = [
    Marketplace(
        name="github",
        type="github",
        search_url="https://api.github.com/search/repositories",
        detail_url="https://api.github.com/repos",
    ),
]

# 代码安全扫描 —— 危险模式
DANGEROUS_PATTERNS = [
    (r"\bos\.system\b", "os.system() 调用"),
    (r"\bos\.popen\b", "os.popen() 调用"),
    (r"\bsubprocess\b", "subprocess 模块"),
    (r"\beval\s*\(", "eval() 调用"),
    (r"\bexec\s*\(", "exec() 调用"),
    (r"\bcompile\s*\(", "compile() 调用"),
    (r"\b__import__\s*\(", "__import__() 调用"),
    (r"\bsocket\b", "socket 网络模块"),
    (r"\bshutil\.rmtree\b", "shutil.rmtree() 调用"),
    (r"\bos\.remove\b", "os.remove() 调用"),
]

SKILL_REQUIRED_FILE = "SKILL.md"


# ═══════════════════════════════════════════
# 工具函数
# ═══════════════════════════════════════════


def _parse_skill_md(file_path: str) -> dict:
    """解析 SKILL.md 的 YAML front matter，返回 {name, description, version, ...}"""
    content = Path(file_path).read_text(encoding="utf-8")
    match = re.match(r"^---\s*\n(.*?)\n---\s*\n?(.*)", content, re.DOTALL)
    if not match:
        return {}
    front = yaml.safe_load(match.group(1)) or {}
    body = match.group(2).strip()
    return {
        "name": front.get("name", ""),
        "description": front.get("description", body[:200] if body else ""),
        "version": str(front.get("version", "")),
        "dependencies": front.get("dependencies") or [],
        "env_vars": front.get("env") or front.get("env_vars") or [],
        "skill_md_content": content,
    }


# ═══════════════════════════════════════════
# SkillManager
# ═══════════════════════════════════════════


class SkillManager:
    def __init__(
        self,
        install_dirs: list[str] | None = None,
        trash_dir: str | None = None,
        marketplaces: list[Marketplace] | None = None,
        marketplaces_yaml: str | None = None,
    ):
        if marketplaces:
            self.marketplaces = marketplaces
        elif marketplaces_yaml:
            self.marketplaces = self._load_marketplaces_from_yaml(marketplaces_yaml)
        else:
            self.marketplaces = DEFAULT_MARKETPLACES

        _AGENT_HOME = Path.home() / ".simpleagent"
        self.install_dirs = install_dirs or [
            os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "skills"
            ),
            str(_AGENT_HOME / "skills"),
        ]
        self.trash_dir = trash_dir or str(_AGENT_HOME / ".trash")
        os.makedirs(self.trash_dir, exist_ok=True)
        for d in self.install_dirs:
            os.makedirs(d, exist_ok=True)

    @staticmethod
    def _load_marketplaces_from_yaml(yaml_path: str) -> list[Marketplace]:
        raw = yaml.safe_load(Path(yaml_path).read_text(encoding="utf-8"))
        marketplaces: list[Marketplace] = []
        for item in raw.get("marketplaces", []):
            api_key = item.get("api_key", "")
            # 支持 ${ENV_VAR} 格式的环境变量
            if api_key and api_key.startswith("${") and api_key.endswith("}"):
                api_key = os.environ.get(api_key[2:-1], "")
            marketplaces.append(
                Marketplace(
                    name=item["name"],
                    type=item["type"],
                    search_url=item.get("search_url"),
                    detail_url=item.get("detail_url"),
                    api_key=api_key or None,
                    query_param=item.get("query_param", "q"),
                )
            )
        return marketplaces

    # ── 搜索 ──

    async def search(self, keyword: str) -> list[SkillMeta]:
        """并行搜索所有市场，合并去重"""
        tasks = [self._search_one(mp, keyword) for mp in self.marketplaces]
        gathered = await asyncio.gather(*tasks, return_exceptions=True)
        results: list[SkillMeta] = []
        for item in gathered:
            if isinstance(item, Exception):
                continue
            results.extend(item)
        return self._dedup(results)

    async def _search_one(self, mp: Marketplace, keyword: str) -> list[SkillMeta]:
        if mp.type == "github":
            return await self._search_github(mp, keyword)
        elif mp.type == "rest":
            return await self._search_rest(mp, keyword)
        return []

    async def _search_github(self, mp: Marketplace, keyword: str) -> list[SkillMeta]:
        """搜索 GitHub 仓库，按 topic:mcp-skill + keyword"""
        headers = {"Accept": "application/vnd.github+json"}
        if mp.api_key:
            headers["Authorization"] = f"Bearer {mp.api_key}"
        params = {
            "q": f"topic:mcp-skill {keyword}",
            "per_page": 20,
            "sort": "stars",
        }
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(
                    mp.search_url or "https://api.github.com/search/repositories",
                    params=params,
                    headers=headers,
                )
                resp.raise_for_status()
                data = resp.json()
        except Exception:
            return []

        results = []
        for repo in data.get("items", []):
            results.append(
                SkillMeta(
                    name=repo["name"],
                    description=(repo.get("description") or "")[:300],
                    author=repo["owner"]["login"],
                    source=mp.name,
                    homepage_url=repo["html_url"],
                )
            )
        return results

    async def _search_rest(self, mp: Marketplace, keyword: str) -> list[SkillMeta]:
        if not mp.search_url:
            return []
        headers = {}
        if mp.api_key:
            headers["Authorization"] = f"Bearer {mp.api_key}"
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(
                    mp.search_url,
                    params={mp.query_param: keyword},
                    headers=headers,
                )
                resp.raise_for_status()
                data = resp.json()
        except Exception:
            return []
        # 解包常见响应 envelope: {data:[...]}, {results:[...]}, {skills:[...]}, 纯数组 [...]
        items = self._unwrap_response(data)
        return self._normalize_rest_results(items, mp.name)

    @staticmethod
    def _unwrap_response(data) -> list[dict]:
        """从各 API 的不同响应格式中提取技能列表"""
        if isinstance(data, list):
            return data
        for key in ("data", "results", "skills", "items", "records"):
            if isinstance(data.get(key), list):
                return data[key]
        # 兜底：如果以上都不匹配，可能是单条结果，包成列表
        if isinstance(data, dict) and data:
            return [data]
        return []

    def _normalize_rest_results(self, data: list[dict], source: str) -> list[SkillMeta]:
        results = []
        for item in data:
            results.append(
                SkillMeta(
                    name=item.get("name") or item.get("slug") or item.get("id") or "",
                    description=(item.get("description") or item.get("summary") or "")[:300],
                    author=item.get("author") or item.get("owner") or item.get("publisher") or "",
                    source=source,
                    homepage_url=item.get("url")
                    or item.get("homepage")
                    or item.get("homepage_url")
                    or item.get("html_url")
                    or "",
                    version=str(item.get("version", "")),
                )
            )
        return results

    def _dedup(self, results: list[SkillMeta]) -> list[SkillMeta]:
        seen: set[str] = set()
        unique: list[SkillMeta] = []
        for r in results:
            key = r.name.lower()
            if key not in seen:
                seen.add(key)
                unique.append(r)
        return unique

    # ── 详情 ──

    async def get_details(self, skill_name: str) -> SkillDetail | None:
        """先从本地已安装查找，再从市场远程获取"""
        local = self._find_installed(skill_name)
        if local:
            parsed = _parse_skill_md(os.path.join(local, SKILL_REQUIRED_FILE))
            return SkillDetail(
                name=parsed.get("name", skill_name),
                description=parsed.get("description", ""),
                author="",
                source="local",
                homepage_url="",
                version=parsed.get("version", ""),
                skill_md_content=parsed.get("skill_md_content", ""),
                dependencies=parsed.get("dependencies", []),
                env_vars=parsed.get("env_vars", []),
            )
        return await self._fetch_remote_detail(skill_name)

    async def _fetch_remote_detail(self, skill_name: str) -> SkillDetail | None:
        """从各市场获取 skill 详情"""
        for mp in self.marketplaces:
            if mp.type == "github":
                detail = await self._github_detail(mp, skill_name)
                if detail:
                    return detail
            elif mp.type == "rest" and mp.detail_url:
                detail = await self._rest_detail(mp, skill_name)
                if detail:
                    return detail
        return None

    async def _github_detail(
        self, mp: Marketplace, skill_name: str
    ) -> SkillDetail | None:
        """从 GitHub 仓库获取 SKILL.md"""
        headers = {"Accept": "application/vnd.github.raw"}
        if mp.api_key:
            headers["Authorization"] = f"Bearer {mp.api_key}"
        # 尝试直接获取 SKILL.md
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                # 先搜索到仓库
                search_resp = await client.get(
                    mp.search_url or "https://api.github.com/search/repositories",
                    params={"q": f"topic:mcp-skill {skill_name}", "per_page": 3},
                    headers={
                        "Accept": "application/vnd.github+json",
                        **(
                            {"Authorization": f"Bearer {mp.api_key}"}
                            if mp.api_key
                            else {}
                        ),
                    },
                )
                search_resp.raise_for_status()
                items = search_resp.json().get("items", [])
                if not items:
                    return None

                owner = items[0]["owner"]["login"]
                repo_name = items[0]["name"]
                default_branch = items[0].get("default_branch", "main")

                # 获取 SKILL.md 内容
                raw_url = f"https://raw.githubusercontent.com/{owner}/{repo_name}/{default_branch}/SKILL.md"
                raw_resp = await client.get(raw_url, headers=headers)
                raw_resp.raise_for_status()
                skill_md = raw_resp.text

                parsed = _parse_skill_md_text(skill_md)
                return SkillDetail(
                    name=parsed.get("name", repo_name),
                    description=parsed.get(
                        "description", items[0].get("description", "")
                    ),
                    author=owner,
                    source=mp.name,
                    homepage_url=items[0]["html_url"],
                    version=parsed.get("version", ""),
                    skill_md_content=skill_md,
                    dependencies=parsed.get("dependencies", []),
                    env_vars=parsed.get("env_vars", []),
                )
        except Exception:
            return None

    async def _rest_detail(
        self, mp: Marketplace, skill_name: str
    ) -> SkillDetail | None:
        """从 REST 市场获取 skill 详情"""
        if not mp.detail_url or not mp.search_url:
            return None
        headers = {}
        if mp.api_key:
            headers["Authorization"] = f"Bearer {mp.api_key}"
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                # 先搜索找到该 skill 的准确条目
                search_resp = await client.get(
                    mp.search_url,
                    params={mp.query_param: skill_name},
                    headers=headers,
                )
                search_resp.raise_for_status()
                items = self._unwrap_response(search_resp.json())

                if not items:
                    return None

                # 按名称精确匹配
                matched = next(
                    (
                        it
                        for it in items
                        if (it.get("name") or it.get("slug") or "").lower()
                        == skill_name.lower()
                    ),
                    items[0],  # 无精确匹配时用第一条
                )

                # 尝试获取详情端点
                slug = matched.get("slug") or matched.get("name") or matched.get("id")
                detail_url = f"{mp.detail_url.rstrip('/')}/{slug}"
                detail = matched  # 默认用搜索结果
                try:
                    detail_resp = await client.get(detail_url, headers=headers)
                    if detail_resp.status_code < 400:
                        detail = detail_resp.json()
                except Exception:
                    pass

                return SkillDetail(
                    name=detail.get("name") or detail.get("slug") or skill_name,
                    description=(detail.get("description") or "")[:300],
                    author=detail.get("author")
                    or detail.get("owner")
                    or detail.get("publisher")
                    or "",
                    source=mp.name,
                    homepage_url=detail.get("url")
                    or detail.get("homepage")
                    or detail.get("homepage_url")
                    or detail.get("html_url")
                    or "",
                    version=str(detail.get("version", "")),
                    skill_md_content=detail.get("skill_md_content")
                    or detail.get("content")
                    or "",
                    dependencies=detail.get("dependencies") or [],
                    env_vars=detail.get("env_vars") or detail.get("env") or [],
                )
        except Exception:
            return None

    # ── 安装 ──

    async def install(
        self, skill_name: str, target: str | None = None
    ) -> InstallResult:
        """下载 → 校验 → 安装"""
        source = await self._resolve_source(skill_name)
        if source is None:
            return InstallResult(
                success=False, path="", message=f"未找到 skill: {skill_name}"
            )

        staging = tempfile.mkdtemp(prefix="skill_install_")
        dest = target or self.install_dirs[0]  # 默认安装到第一个目录

        try:
            if source["type"] == "git":
                await self._git_clone(source["url"], staging)
            elif source["type"] == "http":
                await self._http_download(source["url"], staging)
            else:
                return InstallResult(
                    success=False,
                    path="",
                    message=f"不支持的下载类型: {source['type']}",
                )

            self._validate_skill(staging)

            skill_path = os.path.join(dest, skill_name)
            if os.path.exists(skill_path):
                ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                backup = os.path.join(self.trash_dir, f"{skill_name}_backup_{ts}")
                shutil.move(skill_path, backup)

            shutil.move(staging, skill_path)
            return InstallResult(
                success=True, path=skill_path, message=f"安装成功: {skill_path}"
            )
        except SkillValidationError as e:
            return InstallResult(success=False, path="", message=f"校验失败: {e}")
        except Exception as e:
            return InstallResult(success=False, path="", message=f"安装失败: {e}")
        finally:
            if os.path.exists(staging):
                shutil.rmtree(staging, ignore_errors=True)

    async def _resolve_source(self, skill_name: str) -> dict | None:
        """确定 skill 的下载来源。返回 {type, url}，找不到返回 None"""
        # 先看是否看起来像完整 URL
        if skill_name.startswith("http://") or skill_name.startswith("https://"):
            url = skill_name
            if url.endswith(".git"):
                return {"type": "git", "url": url}
            return {"type": "http", "url": url}

        # 查市场（优先远程，本地的 detail 没有 homepage_url 无法用于下载）
        detail = await self.get_details(skill_name)
        if detail and not detail.homepage_url and detail.source == "local":
            # 本地已安装但缺少下载源，跳过本地结果，尝试远程查找
            detail = await self._fetch_remote_detail(skill_name)

        if detail and detail.homepage_url:
            # GitHub repo → 用 git clone
            if "github.com" in detail.homepage_url:
                return {
                    "type": "git",
                    "url": (
                        detail.homepage_url + ".git"
                        if not detail.homepage_url.endswith(".git")
                        else detail.homepage_url
                    ),
                }
            return {"type": "http", "url": detail.homepage_url}

        return None

    async def _git_clone(self, url: str, dest: str):
        proc = await asyncio.create_subprocess_exec(
            "git",
            "clone",
            "--depth",
            "1",
            url,
            dest,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode != 0:
            raise RuntimeError(f"git clone 失败: {stderr.decode()}")

    async def _http_download(self, url: str, dest: str):
        async with httpx.AsyncClient(timeout=60, follow_redirects=True) as client:
            resp = await client.get(url)
            resp.raise_for_status()

        content_type = resp.headers.get("content-type", "")
        content = resp.content

        if len(content) > 50 * 1024 * 1024:  # 50MB 上限
            raise RuntimeError("下载内容过大 (>50MB)，拒绝下载")

        if "zip" in content_type or url.endswith(".zip"):
            self._extract_zip(content, dest)
        elif "tar" in content_type or url.endswith((".tar.gz", ".tgz")):
            self._extract_tar(content, dest)
        else:
            os.makedirs(dest, exist_ok=True)
            Path(dest, SKILL_REQUIRED_FILE).write_bytes(content)

    def _extract_zip(self, content: bytes, dest: str):
        import io

        with zipfile.ZipFile(io.BytesIO(content)) as zf:
            # 安全检查：拒绝路径穿越
            for member in zf.infolist():
                member_path = os.path.normpath(member.filename)
                if member_path.startswith("..") or os.path.isabs(member_path):
                    raise SkillValidationError(f"压缩包包含危险路径: {member.filename}")
            zf.extractall(dest)

    def _extract_tar(self, content: bytes, dest: str):
        import io, tarfile

        with tarfile.open(fileobj=io.BytesIO(content), mode="r:*") as tf:
            for member in tf.getmembers():
                member_path = os.path.normpath(member.name)
                if member_path.startswith("..") or os.path.isabs(member_path):
                    raise SkillValidationError(f"压缩包包含危险路径: {member.name}")
            tf.extractall(dest)

    # ── 校验 ──

    def _validate_skill(self, path: str):
        """校验 skill 目录合法性"""
        # 1. SKILL.md 必须存在
        skill_md = os.path.join(path, SKILL_REQUIRED_FILE)
        if not os.path.isfile(skill_md):
            raise SkillValidationError(f"缺少 {SKILL_REQUIRED_FILE} 文件")

        parsed = _parse_skill_md(skill_md)
        if not parsed.get("name"):
            raise SkillValidationError("SKILL.md front matter 中缺少 name 字段")

        # 2. 扫描 Python 文件
        for root, _dirs, files in os.walk(path):
            for f in files:
                if f.endswith(".py"):
                    self._scan_file(os.path.join(root, f))

    def _scan_file(self, file_path: str):
        """扫描单个文件中的危险代码"""
        try:
            lines = Path(file_path).read_text(encoding="utf-8")
        except Exception:
            return
        for lineno, line in enumerate(lines.split("\n"), 1):
            for pattern, desc in DANGEROUS_PATTERNS:
                if re.search(pattern, line):
                    raise SkillValidationError(
                        f"安全风险: {desc} at {file_path}:{lineno}\n  → {line.strip()[:120]}"
                    )

    # ── 列表 ──

    def list_installed(self) -> list[InstalledSkill]:
        """扫描所有安装目录，读取每个 SKILL.md"""
        skills: list[InstalledSkill] = []
        seen: set[str] = set()
        for base_dir in self.install_dirs:
            if not os.path.isdir(base_dir):
                continue
            for entry in os.listdir(base_dir):
                full_path = os.path.join(base_dir, entry)
                if not os.path.isdir(full_path):
                    continue
                skill_md = os.path.join(full_path, SKILL_REQUIRED_FILE)
                if not os.path.isfile(skill_md):
                    continue
                key = entry.lower()
                if key in seen:
                    continue
                seen.add(key)
                parsed = _parse_skill_md(skill_md)
                source_type = (
                    "git" if os.path.isdir(os.path.join(full_path, ".git")) else "http"
                )
                skills.append(
                    InstalledSkill(
                        name=parsed.get("name", entry),
                        description=parsed.get("description", ""),
                        version=parsed.get("version", ""),
                        path=full_path,
                        source_type=source_type,
                    )
                )
        return sorted(skills, key=lambda s: s.name)

    # ── 查找已安装 ──

    def _find_installed(self, skill_name: str) -> str | None:
        """在安装目录中查找 skill，返回完整路径"""
        for base_dir in self.install_dirs:
            candidate = os.path.join(base_dir, skill_name)
            if os.path.isdir(candidate) and os.path.isfile(
                os.path.join(candidate, SKILL_REQUIRED_FILE)
            ):
                return candidate
        # 模糊匹配：遍历目录名
        for base_dir in self.install_dirs:
            if not os.path.isdir(base_dir):
                continue
            for entry in os.listdir(base_dir):
                if entry.lower() == skill_name.lower():
                    full = os.path.join(base_dir, entry)
                    if os.path.isdir(full) and os.path.isfile(
                        os.path.join(full, SKILL_REQUIRED_FILE)
                    ):
                        return full
        return None

    # ── 更新 ──

    async def update(self, skill_name: str) -> InstallResult:
        """更新已安装的 skill"""
        local = self._find_installed(skill_name)
        if not local:
            return InstallResult(
                success=False, path="", message=f"未找到已安装的 skill: {skill_name}"
            )

        dotgit = os.path.join(local, ".git")
        if os.path.isdir(dotgit):
            try:
                proc = await asyncio.create_subprocess_exec(
                    "git",
                    "-C",
                    local,
                    "pull",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                stdout, stderr = await proc.communicate()
                if proc.returncode != 0:
                    return InstallResult(
                        success=False,
                        path=local,
                        message=f"git pull 失败: {stderr.decode()}",
                    )
                return InstallResult(
                    success=True, path=local, message="已通过 git pull 更新"
                )
            except FileNotFoundError:
                return InstallResult(
                    success=False, path=local, message="未找到 git 命令"
                )
        else:
            return await self.install(skill_name, target=os.path.dirname(local))

    # ── 删除 ──

    def remove(self, skill_name: str, permanent: bool = False) -> RemoveResult:
        """删除 skill（默认移入回收站）"""
        local = self._find_installed(skill_name)
        if not local:
            return RemoveResult(
                success=False, path="", message=f"未找到已安装的 skill: {skill_name}"
            )

        if permanent:
            shutil.rmtree(local, ignore_errors=True)
            return RemoveResult(
                success=True, path=local, message=f"已永久删除: {local}"
            )
        else:
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            trash_path = os.path.join(self.trash_dir, f"{skill_name}_{ts}")
            shutil.move(local, trash_path)
            return RemoveResult(
                success=True,
                path=trash_path,
                message=f"已移入回收站: {trash_path}（可手动恢复）",
            )


# ═══════════════════════════════════════════
# 辅助
# ═══════════════════════════════════════════


def _parse_skill_md_text(content: str) -> dict:
    """从 SKILL.md 文本内容解析 YAML front matter"""
    match = re.match(r"^---\s*\n(.*?)\n---\s*\n?(.*)", content, re.DOTALL)
    if not match:
        return {}
    front = yaml.safe_load(match.group(1)) or {}
    body = match.group(2).strip()
    return {
        "name": front.get("name", ""),
        "description": front.get("description", body[:200] if body else ""),
        "version": str(front.get("version", "")),
        "dependencies": front.get("dependencies") or [],
        "env_vars": front.get("env") or front.get("env_vars") or [],
    }


def _parse_skill_md(file_path: str) -> dict:
    """从 SKILL.md 文件路径解析 YAML front matter"""
    content = Path(file_path).read_text(encoding="utf-8")
    return _parse_skill_md_text(content)


class SkillValidationError(Exception):
    """Skill 校验失败异常"""

    pass
