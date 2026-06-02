import asyncio
import os
from dataclasses import dataclass, field
from enum import Enum


class Status(Enum):
    PASS = "✅"
    WARN = "⚠️"
    FAIL = "❌"


@dataclass
class CheckResult:
    name: str
    status: Status
    detail: str = ""


class StartupChecker:
    def __init__(self):
        self.results: list[CheckResult] = []

    async def check_env(self) -> CheckResult:
        """检查必需环境变量"""
        required = ["EMBEDDING_KEY", "EMBEDDING_URL"]
        missing = [k for k in required if k not in os.environ]
        if missing:
            return CheckResult("环境变量", Status.FAIL, f"缺少: {', '.join(missing)}")
        return CheckResult("环境变量", Status.PASS)

    async def check_model(self, model) -> CheckResult:
        """检查 LLM 模型连通性"""
        try:
            response = await model.ainvoke([{"role": "user", "content": "ping"}])
            if response.content:
                return CheckResult("LLM 模型", Status.PASS, "连接正常")
        except Exception as e:
            return CheckResult("LLM 模型", Status.FAIL, str(e)[:100])

    async def check_embedding(self, embeddings) -> CheckResult:
        """检查 Embedding 服务连通性"""
        try:
            vec = await embeddings.aembed_query("test")
            if vec and len(vec) > 0:
                return CheckResult("Embedding", Status.PASS, f"维度={len(vec)}")
        except Exception as e:
            return CheckResult("Embedding", Status.WARN, f"不可用（不影响对话）- {str(e)[:80]}")

    async def check_mcp(self, python_exe: str, server_script: str) -> CheckResult:
        """检查 MCP 服务器文件"""
        if not os.path.exists(python_exe):
            return CheckResult("MCP Python", Status.WARN, f"路径不存在: {python_exe}")
        if not os.path.exists(server_script):
            return CheckResult("MCP 脚本", Status.WARN, f"文件不存在: {server_script}")
        return CheckResult("MCP 服务器", Status.PASS)

    async def check_chromadb(self, persist_dir: str) -> CheckResult:
        """检查 ChromaDB 目录可写"""
        try:
            os.makedirs(persist_dir, exist_ok=True)
            test_file = os.path.join(persist_dir, ".write_test")
            with open(test_file, "w") as f:
                f.write("")
            os.remove(test_file)
            return CheckResult("ChromaDB", Status.PASS, f"目录: {persist_dir}")
        except Exception as e:
            return CheckResult("ChromaDB", Status.WARN, str(e)[:100])

    async def run_all(self, **kwargs) -> list[CheckResult]:
        """运行全部检查"""
        checks = [
            self.check_env(),
            self.check_model(kwargs["model"]),
            self.check_embedding(kwargs["embeddings"]),
            self.check_mcp(kwargs["python_exe"], kwargs["server_script"]),
            self.check_chromadb(kwargs["chroma_dir"]),
        ]
        results = await asyncio.gather(*checks, return_exceptions=True)
        for r in results:
            if isinstance(r, Exception):
                self.results.append(CheckResult("异常", Status.FAIL, str(r)[:100]))
            else:
                self.results.append(r)
        return self.results

    def has_critical(self) -> bool:
        return any(r.status == Status.FAIL for r in self.results)

    def print_report(self):
        for r in self.results:
            print(f"  {r.status.value} {r.name:<15} {r.detail}")
