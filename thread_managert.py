import json
import uuid
from datetime import datetime
from pathlib import Path
from dataclasses import dataclass, field


@dataclass
class Thread:
    id: str
    title: str
    created_at: str
    updated_at: str
    message_count: int = 0


class ThreadManager:
    """多会话管理器 — 元数据存 JSON，对话状态由 SqliteSaver 按 thread_id 隔离"""

    def __init__(self, storage_dir: Path = None):
        self.storage_dir = storage_dir or (Path.home() / ".simpleagent" / "threads")
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self._current_id: str | None = None

        # 自动恢复上次活跃的会话
        existing = self.list()
        if existing:
            self._current_id = existing[0].id

    # ---- CRUD ----

    def create(self, title: str = "") -> Thread:
        t = Thread(
            id=uuid.uuid4().hex[:12],
            title=title or "新对话",
            created_at=datetime.now().isoformat(),
            updated_at=datetime.now().isoformat(),
        )
        self._save(t)
        self._current_id = t.id
        return t

    def list(self) -> list[Thread]:
        threads = []
        for f in sorted(
            self.storage_dir.glob("*.json"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        ):
            data = json.loads(f.read_text("utf-8"))
            threads.append(Thread(**data))
        return threads

    def switch(self, thread_id: str) -> Thread | None:
        t = self._load(thread_id)
        if t:
            self._current_id = t.id
        return t

    def delete(self, thread_id: str) -> bool:
        f = self.storage_dir / f"{thread_id}.json"
        if f.exists():
            f.unlink()
            if self._current_id == thread_id:
                self._current_id = None
            return True
        return False

    def rename(self, thread_id: str, title: str) -> Thread | None:
        t = self._load(thread_id)
        if t:
            t.title = title
            self._save(t)
        return t

    def touch(self, thread_id: str):
        """更新最近活动时间"""
        t = self._load(thread_id)
        if t:
            t.updated_at = datetime.now().isoformat()
            self._save(t)

    @property
    def current_id(self) -> str | None:
        return self._current_id

    # ---- internal ----

    def _file(self, thread_id: str) -> Path:
        return self.storage_dir / f"{thread_id}.json"

    def _save(self, t: Thread):
        self._file(t.id).write_text(
            json.dumps(t.__dict__, ensure_ascii=False, indent=2), "utf-8"
        )

    def _load(self, thread_id: str) -> Thread | None:
        f = self._file(thread_id)
        if not f.exists():
            return None
        return Thread(**json.loads(f.read_text("utf-8")))
