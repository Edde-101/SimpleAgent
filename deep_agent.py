import asyncio
import os
from deepagents import create_deep_agent

# from models.models import embeddings

# from models.models import model
from middleware.memory_middleware import memory_middleware, pii_middleware
from prompt.prompts import Assistant_PROMPT
from langchain_mcp_adapters.client import MultiServerMCPClient
from deepagents.backends import FilesystemBackend
from middleware.guard_middleware import GuardMiddleware
from memory.memory_store import remember, recall, forget
from memory.memory import checkpointer
from startup_check import StartupChecker
from tools.subagent_tool import *
from tools.tool_wrapper import wrap_tool_with_retry, TOOL_RETRY_CONFIG
from traces.tracer import JsonlTracer
from models.model_registry import registry

base_dir = os.path.dirname(os.path.abspath(__file__))
project_dir = os.path.dirname(base_dir)


class Agent:
    def __init__(self, model_name: str = None):
        self.model = registry.get(model_name)
        self.assistant_agent = None
        # 使用自定义的 checkpointer
        self.checkpointer = checkpointer
        self.backend = FilesystemBackend(root_dir=base_dir, virtual_mode=True)
        self.tracer = JsonlTracer(base_dir + "/traces/trace.jsonl")
        self.config = {"configurable": {"thread_id": "user-session-abc"}}
        self.interrupt_on = {
            "write_file": True,
            "edit_file": True,
            "execute": True,
            "delete_file": True,
        }

    async def get_mcp_tools(self):

        python_exe = os.path.join(project_dir, "venv", "Scripts", "python.exe")
        server_script = os.path.join(base_dir, "mcp", "calc_server.py")
        print(f"[MCP] 启动服务器: {python_exe} {server_script}")
        client = MultiServerMCPClient(
            {
                "math": {
                    "transport": "stdio",
                    "command": python_exe,
                    "args": [server_script],
                }
            }
        )
        try:
            mcp_tools = await client.get_tools()
        except Exception:
            import traceback

            print(f"[ERROR] 获取 MCP 工具失败:")
            traceback.print_exc()
            mcp_tools = []
        tools = [*mcp_tools, remember, recall, forget]
        return tools

    async def check(self):
        # 启动检查
        checker = StartupChecker()
        await checker.run_all(
            model=self.model,
            embeddings=registry.get_embedding(),  # 从 models.py 导入
            python_exe=os.path.join(project_dir, "venv", "Scripts", "python.exe"),
            server_script=os.path.join(base_dir, "mcp", "calc_server.py"),
            chroma_dir=os.path.join(base_dir, "memory", "chroma_db"),
        )
        checker.print_report()
        if checker.has_critical():
            print("[FATAL] 关键组件未就绪，终止启动。")
            return False
        return True

    async def start_agent(self):

        # 检查启动
        if not await self.check():
            return

        # 加载工具tools
        tools = await self.get_mcp_tools()

        # 加载子Agent
        init_subagent_runtime(
            self.model,
            tools,
            checkpointer,
            skills=["./skills"],
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
            skills=["./skills"],
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
        )

    async def reload_agent(self, model_name: str = None):
        """运行时切换模型，保留 thread_id（对话历史不丢）"""
        if model_name:
            self.model = registry.get(model_name)

        tools = await self.get_mcp_tools()
        init_subagent_runtime(
            self.model,
            tools,
            checkpointer,
            skills=["./skills"],
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
            skills=["./skills"],
            backend=self.backend,
            system_prompt=Assistant_PROMPT,
            checkpointer=self.checkpointer,
            middleware=[GuardMiddleware(), memory_middleware],
            interrupt_on=self.interrupt_on,
            subagents=loaded_subagents,
        )

    async def chat_stream(self, new_query):
        print("\n助手：", end="", flush=True)
        # 状态变量
        reasoning_started = False  # 是否已打印过思考标题
        answer_started = False  # 是否已打印过答案标题
        in_reasoning = False  # 当前是否正在输出思考内容（用于判断切换到答案）

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

            # 1. 处理思考内容
            reasoning = token.additional_kwargs.get("reasoning_content")
            if reasoning:
                if not reasoning_started:
                    # 第一次遇到思考内容：打印标题，并标记已在思考中
                    print(f"\n💭 [思考]", end="", flush=True)
                    reasoning_started = True
                    in_reasoning = True
                # 输出思考内容（不换行，连续）
                print(reasoning, end="", flush=True)
                continue  # 本 token 无答案内容，跳过后续答案处理

            # 2. 处理最终答案（content）
            if token.content:
                # 如果之前正在输出思考，且现在开始输出答案，需要换行并打印答案标题
                if in_reasoning and not answer_started:
                    print("\n\n🤖 [答案]", end="", flush=True)
                    answer_started = True
                    in_reasoning = False
                elif not answer_started:
                    # 没有思考内容，直接打印答案标题
                    print("\n🤖 [答案]", end="", flush=True)
                    answer_started = True
                # 输出答案内容
                print(token.content, end="", flush=True)

        print("\n")  # 最终换行


async def main():
    agent = Agent()
    await agent.start_agent()
    while True:
        user_input = input("请输入: ")
        if not user_input.strip():
            continue
        await agent.chat_stream(user_input)


if __name__ == "__main__":
    asyncio.run(main())
