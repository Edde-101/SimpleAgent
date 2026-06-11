import asyncio
import os
import sys
from deepagents import create_deep_agent
from SimpleAgent.thread_managert import ThreadManager
from middleware.memory_middleware import memory_middleware, pii_middleware
from prompt.prompts import Assistant_PROMPT
from langchain_mcp_adapters.client import MultiServerMCPClient
from deepagents.backends import FilesystemBackend, CompositeBackend
from deepagents.middleware.filesystem import FilesystemPermission
from middleware.guard_middleware import GuardMiddleware
from memory.memory_store import remember, recall, forget
from memory.memory import init_checkpointer
from memory import memory as _memory_module
from startup_check import StartupChecker
from tools.subagent_tool import *
from tools.tool_wrapper import wrap_tool_with_retry, TOOL_RETRY_CONFIG
from traces.tracer import JsonlTracer
from models.model_registry import registry
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
    PROJECT_VPATH,
    AGENT_HOME_DIRS,
    LOCAL_SKILLS,
    LOCAL_MCP,
    LOCAL_MEMORY,
    LOCAL_TRACES,
)

base_dir = str(LOCAL_SKILLS.parent)  # SimpleAgent/
project_dir = str(LOCAL_SKILLS.parent.parent)  # myAgent/

# 项目所在盘符根（D:/），作为默认后端的 root_dir
_drive_root = os.path.splitdrive(base_dir)[0] + "/"
_project_vpath = PROJECT_VPATH

# 文件操作权限
PERMISSIONS = [
    # 1) 允许修改项目 skills/ mcp/ 子目录
    FilesystemPermission(
        operations=["read", "write"],
        paths=[
            f"{_project_vpath}skills/**",
            f"{_project_vpath}mcp/**",
        ],
        mode="allow",
    ),
    # 2) 允许修改 Agent 工作目录下的 skills/ mcps/ temp/ subagents/
    FilesystemPermission(
        operations=["read", "write"],
        paths=[
            f"{VIRTUAL_SKILLS_HOME}/**",
            f"{VIRTUAL_MCPS_HOME}/**",
            f"{VIRTUAL_TEMP}/**",
            f"{VIRTUAL_SUBAGENTS}/**",
        ],
        mode="allow",
    ),
    # 3) 本项目其余全部禁止（源码保护）
    FilesystemPermission(
        operations=["read", "write"],
        paths=[f"{_project_vpath}**"],
        mode="deny",
    ),
    # 4) 非本项目目录 → 默认放行（跨盘均可用）
    FilesystemPermission(
        operations=["read", "write"],
        paths=["/**"],
        mode="allow",
    ),
]


def _build_backend():
    """构建跨盘后端：/.simpleagent/ → C: 用户目录，其余 → D: 项目盘"""
    default = FilesystemBackend(root_dir=_drive_root, virtual_mode=True)
    agent_home = FilesystemBackend(root_dir=str(AGENT_HOME), virtual_mode=True)
    return CompositeBackend(default=default, routes={"/.simpleagent/": agent_home})


class Agent:
    def __init__(self, model_name: str = None):
        self.model = registry.get(model_name)
        self.assistant_agent = None
        self.checkpointer = _memory_module.checkpointer
        self.backend = _build_backend()
        self.tracer = JsonlTracer(base_dir + "/traces/trace.jsonl")
        self.thread_mgr = ThreadManager()
        if not self.thread_mgr.current_id:
            self.thread_mgr.create()
        self.config = {"configurable": {"thread_id": self.thread_mgr.current_id}}
        self.interrupt_on = {
            "write_file": True,
            "edit_file": True,
            "execute": True,
            "delete_file": True,
            "install_skill": True,
        }

    async def get_mcp_tools(self):
        python_exe = sys.executable
        server_script1 = os.path.join(base_dir, "mcp", "general_server.py")
        server_script2 = os.path.join(base_dir, "mcp", "skill_manager_server.py")
        print(f"[MCP] 启动服务器: {python_exe} {server_script1} {server_script2}")
        client = MultiServerMCPClient(
            {
                "general": {
                    "transport": "stdio",
                    "command": python_exe,
                    "args": [server_script1],
                },
                "skill_manager": {
                    "transport": "stdio",
                    "command": python_exe,
                    "args": [server_script2],
                },
            }
        )
        try:
            mcp_tools = await client.get_tools()
        except Exception:
            import traceback

            print(f"[ERROR] 获取 MCP 工具失败:")
            traceback.print_exc()
            mcp_tools = []
        return [*mcp_tools, remember, recall, forget]

    async def check(self):
        checker = StartupChecker()
        await checker.run_all(
            model=self.model,
            embeddings=registry.get_embedding(),
            python_exe=sys.executable,
            server_script=os.path.join(base_dir, "mcp", "general_server.py"),
            chroma_dir=os.path.join(base_dir, "memory", "chroma_db"),
        )
        checker.print_report()
        if checker.has_critical():
            print("[FATAL] 关键组件未就绪，终止启动。")
            return False
        return True

    async def start_agent(self):
        # 确保 Agent 工作目录下所有标准化子目录存在
        for _dir in AGENT_HOME_DIRS:
            _dir.mkdir(parents=True, exist_ok=True)

        # 检查启动
        if not await self.check():
            return

        # 初始化持久化 checkpointer（AsyncSqliteSaver）
        await init_checkpointer()
        self.checkpointer = _memory_module.checkpointer

        # 加载工具tools
        tools = await self.get_mcp_tools()

        # 加载子Agent
        init_subagent_runtime(
            self.model,
            tools,
            _memory_module.checkpointer,
            skills=["./skills", "/.simpleagent/skills"],
            backend=self.backend,
            middleware=[GuardMiddleware(), memory_middleware],
            interrupt_on=self.interrupt_on,
        )

        tools = [
            *tools,
            dtask,
            list_subagents,
            add_subagent,
            delete_subagent,
        ]
        all_tools = [
            wrap_tool_with_retry(t, TOOL_RETRY_CONFIG.get(t.name)) for t in tools
        ]
        print(f"\n已注册 {len(all_tools)} 个工具:")
        print(f"   工具列表: {', '.join(t.name for t in all_tools)}")

        # 从磁盘加载持久化的子Agent
        loaded_subagents = load_subagents_from_disk()
        print(
            f"已加载 {len(loaded_subagents)} 个持久化子Agent: {[s['name'] for s in loaded_subagents]}"
        )
        # 创建deep agent
        self.assistant_agent = create_deep_agent(
            model=self.model,
            tools=all_tools,
            skills=["./skills", "/.simpleagent/skills"],
            backend=self.backend,
            system_prompt=Assistant_PROMPT,
            checkpointer=self.checkpointer,
            middleware=[
                GuardMiddleware(),
                memory_middleware,
                pii_middleware,
            ],
            interrupt_on=self.interrupt_on,
            subagents=loaded_subagents,
            permissions=PERMISSIONS,
        )

    async def reload_agent(self, model_name: str = None):
        """运行时切换模型，保留 thread_id（对话历史不丢）"""
        if model_name:
            self.model = registry.get(model_name)

        self.checkpointer = _memory_module.checkpointer

        tools = await self.get_mcp_tools()
        init_subagent_runtime(
            self.model,
            tools,
            _memory_module.checkpointer,
            skills=["./skills", "/.simpleagent/skills"],
            backend=self.backend,
            middleware=[GuardMiddleware(), memory_middleware],
            interrupt_on=self.interrupt_on,
        )

        tools = [*tools, dtask, list_subagents, add_subagent, delete_subagent]
        all_tools = [
            wrap_tool_with_retry(t, TOOL_RETRY_CONFIG.get(t.name)) for t in tools
        ]
        loaded_subagents = load_subagents_from_disk()

        self.assistant_agent = create_deep_agent(
            model=self.model,
            tools=all_tools,
            skills=["./skills", "/.simpleagent/skills"],
            backend=self.backend,
            system_prompt=Assistant_PROMPT,
            checkpointer=self.checkpointer,
            middleware=[GuardMiddleware(), memory_middleware, pii_middleware],
            interrupt_on=self.interrupt_on,
            subagents=loaded_subagents,
            permissions=PERMISSIONS,
        )

    def list_threads(self):
        return self.thread_mgr.list()

    def switch_thread(self, id):
        self.thread_mgr.switch(id)
        self.config["configurable"]["thread_id"] = id

    def delete_thread(self, id):
        self.thread_mgr.delete(id)

    def rename_thread(self, id, title):
        self.thread_mgr.rename(id, title)

    def new_thread(self, title=""):
        self.thread_mgr.create(title)
        self.config["configurable"]["thread_id"] = self.thread_mgr.current_id

    async def chat_stream(self, new_query):
        print("\n助手：", end="", flush=True)
        self.thread_mgr.touch(self.thread_mgr.current_id)  # 更新时间
        reasoning_started = False
        answer_started = False
        in_reasoning = False

        async for token, metadata in self.assistant_agent.astream(
            {"messages": [{"role": "user", "content": new_query}]},
            config={
                **self.config,
                "callbacks": [self.tracer],
            },
            stream_mode="messages",
        ):
            node = metadata.get("langgraph_node")
            if node != "model":
                continue

            reasoning = (token.additional_kwargs or {}).get("reasoning_content", "")
            if reasoning:
                if not reasoning_started:
                    print(f"\n💭 [思考]", end="", flush=True)
                    reasoning_started = True
                    in_reasoning = True
                print(reasoning, end="", flush=True)
                continue

            if token.content:
                if in_reasoning and not answer_started:
                    print("\n\n🤖 [答案]", end="", flush=True)
                    answer_started = True
                    in_reasoning = False
                elif not answer_started:
                    print("\n🤖 [答案]", end="", flush=True)
                    answer_started = True
                print(token.content, end="", flush=True)

        print("\n")

    async def chat_stream_re(self, new_query):
        """与 chat_stream 相同的流式逻辑，但不打印，改为 yield 结构化 dict

        每条 yield 的格式：
            {"type": "thinking", "content": "..."}   — 思考片段
            {"type": "answer",   "content": "..."}   — 答案片段
            {"type": "done"}                          — 流结束
        """
        reasoning_started = False
        in_reasoning = False
        self.thread_mgr.touch(self.thread_mgr.current_id)  # 更新时间

        async for token, metadata in self.assistant_agent.astream(
            {"messages": [{"role": "user", "content": new_query}]},
            config={**self.config, "callbacks": [self.tracer]},
            stream_mode="messages",
        ):
            node = metadata.get("langgraph_node")
            if node != "model":
                continue

            reasoning = (token.additional_kwargs or {}).get("reasoning_content", "")
            if reasoning:
                if not reasoning_started:
                    reasoning_started = True
                    in_reasoning = True
                yield {"type": "thinking", "content": reasoning}
                continue

            if token.content:
                if in_reasoning:
                    in_reasoning = False
                yield {"type": "answer", "content": token.content}

        yield {"type": "done"}


async def main():
    agent = Agent()
    await agent.start_agent()
    while True:
        user_input = input("请输入: ")
        if not user_input.strip():
            continue
        await agent.chat_stream(user_input)


async def main_re():
    agent = Agent()
    await agent.start_agent()
    while True:
        user_input = input("请输入: ")
        if not user_input.strip():
            continue
        thinking_started = False
        answer_started = False
        async for chunk in agent.chat_stream_re(user_input):
            t = chunk["type"]
            if t == "thinking":
                if not thinking_started:
                    print("\n💭 [思考]", end="", flush=True)
                    thinking_started = True
                print(chunk["content"], end="", flush=True)
            elif t == "answer":
                if not answer_started:
                    if thinking_started:
                        print("\n\n🤖 [答案]", end="", flush=True)
                    else:
                        print("\n🤖 [答案]", end="", flush=True)
                    answer_started = True
                print(chunk["content"], end="", flush=True)
            elif t == "done":
                print("\n")


if __name__ == "__main__":
    asyncio.run(main())
