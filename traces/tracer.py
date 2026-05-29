from langchain_core.callbacks import BaseCallbackHandler
import json
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from langchain_core.callbacks import AsyncCallbackHandler
from langchain_core.outputs import LLMResult


class JsonlTracer(AsyncCallbackHandler):
    """将所有回调事件记录为 JSONL 文件。

    每个事件写入一行 JSON，便于导入到日志分析系统。
    """

    def __init__(self, file_path: str = "traces.jsonl", verbose: bool = False):
        """
        Args:
            file_path: 输出文件路径（.jsonl）
            verbose: 是否在控制台打印简要提示
        """
        self.file_path = Path(file_path)
        self.verbose = verbose
        # 确保目录存在
        self.file_path.parent.mkdir(parents=True, exist_ok=True)
        # 线程安全锁（可选，若多线程使用需加锁）
        self._lock = None  # 实际可用 threading.Lock()

    def _write_event(self, event: Dict[str, Any]):
        """将事件写入文件（每行一个 JSON）"""
        line = json.dumps(event, ensure_ascii=False) + "\n"
        with open(self.file_path, "a", encoding="utf-8") as f:
            f.write(line)
        if self.verbose:
            print(f"[TRACE] {event.get('event_type')} recorded")

    def _now_iso(self) -> str:
        return datetime.now().isoformat()

    @staticmethod
    def _safe_serialize(obj: Any) -> Any:
        """将对象转为 JSON 可序列化的形式，失败则返回 str()"""
        try:
            json.dumps(obj, ensure_ascii=False)
            return obj
        except (TypeError, ValueError):
            return str(obj)

    def on_llm_start(self, serialized, prompts, *, run_id, **kwargs):
        # 记录: 模型调用开始 + 输入 prompts
        event = {
            "event_type": "llm_start",
            "run_id": str(run_id),
            "timestamp": self._now_iso(),
            "prompts": prompts,
        }
        self._write_event(event)

    def on_llm_end(
        self,
        response: LLMResult,
        *,
        run_id: uuid.UUID,
        parent_run_id: Optional[uuid.UUID] = None,
        tags: Optional[List[str]] = None,
        **kwargs: Any,
    ) -> None:
        # 提取 token 用量
        token_usage = {}
        if response.llm_output and "token_usage" in response.llm_output:
            token_usage = response.llm_output["token_usage"]
        # 提取生成的内容（可选）
        event = {
            "event_type": "llm_end",
            "run_id": str(run_id),
            "timestamp": self._now_iso(),
            "token_usage": token_usage,
            # 也可以计算耗时，需要通过 run_id 映射开始时间，这里简单起见不计算
        }
        self._write_event(event)

    def on_tool_start(
        self,
        serialized: Dict[str, Any],
        input_str: str,
        *,
        run_id: uuid.UUID,
        parent_run_id: Optional[uuid.UUID] = None,
        tags: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> None:
        event = {
            "event_type": "tool_start",
            "run_id": str(run_id),
            "timestamp": self._now_iso(),
            "tool_name": serialized.get("name", "unknown") if serialized else "unknown",
            "input": input_str,
            "tags": tags,
        }
        self._write_event(event)

    def on_tool_end(
        self,
        output: str,
        *,
        run_id: uuid.UUID,
        parent_run_id: Optional[uuid.UUID] = None,
        tags: Optional[List[str]] = None,
        **kwargs: Any,
    ) -> None:
        event = {
            "event_type": "tool_end",
            "run_id": str(run_id),
            "timestamp": self._now_iso(),
            "output": self._safe_serialize(output),
        }
        self._write_event(event)

    # -------------------- 链/节点相关 (LangGraph 节点属于 Chain) --------------------
    def on_chain_start(
        self,
        serialized: Dict[str, Any],
        inputs: Dict[str, Any],
        *,
        run_id: uuid.UUID,
        parent_run_id: Optional[uuid.UUID] = None,
        tags: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> None:
        event = {
            "event_type": "chain_start",
            "run_id": str(run_id),
            "timestamp": self._now_iso(),
            "chain_name": (
                serialized.get("name", "unknown") if serialized else "unknown"
            ),
            "inputs": self._safe_serialize(inputs),
            "tags": tags,
        }
        self._write_event(event)

    def on_chain_end(
        self,
        outputs: Dict[str, Any],
        *,
        run_id: uuid.UUID,
        parent_run_id: Optional[uuid.UUID] = None,
        tags: Optional[List[str]] = None,
        **kwargs: Any,
    ) -> None:
        event = {
            "event_type": "chain_end",
            "run_id": str(run_id),
            "timestamp": self._now_iso(),
            "outputs": self._safe_serialize(outputs),
        }
        self._write_event(event)

    # -------------------- 可选：错误处理 --------------------
    def on_llm_error(self, error: BaseException, *, run_id, **kwargs) -> None:
        event = {
            "run_id": str(run_id),
            "event_type": "llm_error",
            "timestamp": self._now_iso(),
            "error": str(error),
        }
        self._write_event(event)

    def on_tool_error(self, error: BaseException, **kwargs) -> None:
        event = {
            "event_type": "tool_error",
            "timestamp": self._now_iso(),
            "error": str(error),
        }
        self._write_event(event)

    def on_chain_error(self, error: BaseException, **kwargs) -> None:
        event = {
            "event_type": "chain_error",
            "timestamp": self._now_iso(),
            "error": str(error),
        }
        self._write_event(event)
