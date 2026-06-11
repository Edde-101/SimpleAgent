import aiosqlite
from pathlib import Path
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

_conn = None
checkpointer: AsyncSqliteSaver | None = None


async def init_checkpointer(db_path: str = None):
    global _conn, checkpointer
    if db_path is None:
        db_path = str(Path.home() / ".simpleagent" / "checkpoints.db")
    _conn = await aiosqlite.connect(db_path)
    checkpointer = AsyncSqliteSaver(_conn)


async def close_checkpointer():
    global _conn, checkpointer
    if _conn:
        await _conn.close()
        _conn = None
    checkpointer = None
