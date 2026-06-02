"""
TUI 对话界面 — Claude CLI 风格
Rich 渲染 + prompt_toolkit 输入

运行方式:
    cd <项目根目录>
    python -m tui.chat_tui
"""

import asyncio
import sys
import os
import msvcrt
from datetime import datetime
from pathlib import Path

# 确保可以导入父目录的模块
_parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _parent_dir not in sys.path:
    sys.path.insert(0, _parent_dir)

from SimpleAgent.models.model_registry import registry
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.text import Text
from rich.box import MINIMAL, ROUNDED
from rich.theme import Theme

from prompt_toolkit import PromptSession
from prompt_toolkit.history import FileHistory
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.styles import Style as PTStyle
from prompt_toolkit.completion import Completer, Completion
from prompt_toolkit.formatted_text import HTML

from deep_agent import Agent
from langgraph.types import Command

# ═══════════════════════════════════════════
# 主题 & 样式
# ═══════════════════════════════════════════

THEME = Theme(
    {
        "thinking": "dim cyan",
        "answer": "bright_white",
        "tool": "green",
        "tool_result": "dim green",
        "error": "bold red",
        "info": "bright_blue",
        "welcome": "bold magenta",
        "user": "bold yellow",
        "dim": "dim",
        "highlight": "bold bright_white",
    }
)

console = Console(theme=THEME)

PT_STYLE = PTStyle.from_dict(
    {
        "prompt": "bold yellow",
        "": "white",
    }
)

COMMANDS = ["/help", "/exit", "/quit", "/clear", "/model", "/history", "/save"]
HISTORY_FILE = Path.home() / ".deep_agent_history"


class CommandCompleter(Completer):
    """只在输入 / 时触发指令补全，其他情况不提示"""

    def get_completions(self, document, complete_event):
        text = document.text_before_cursor
        # 找到最后一个 / 的位置，检查它是否是一个"词"的起始
        idx = text.rfind("/")
        if idx == -1:
            return
        word = text[idx:]
        # 确保 / 是词的起始（前面是空白或行首）
        if idx > 0 and text[idx - 1] not in (" ", "\n", "\t"):
            return
        for cmd in COMMANDS:
            if cmd.startswith(word):
                yield Completion(cmd, start_position=-len(word))

# ═══════════════════════════════════════════
# UI 组件
# ═══════════════════════════════════════════


def build_welcome() -> Panel:
    """欢迎界面"""
    body = Text()
    body.append("\n")
    body.append("◈ Simple Agent TUI ◈\n", style="bold bright_white")
    body.append("\n")
    for cmd, desc in [
        ("/help   ", "帮助    "),
        ("/clear  ", "清屏    "),
        ("/model  ", "切换模型"),
        ("/save   ", "保存对话"),
        ("/exit   ", "退出    "),
        ("/history", "历史\n"),
    ]:
        body.append(f"  {cmd}", style="dim")
        body.append(f"{desc}\n")
    return Panel(body, box=ROUNDED, border_style="welcome")


def build_tool_panel(name: str, args: str, result: str = "") -> Panel:
    """工具调用面板"""
    body = Text()
    body.append("🔧 ", style="bold green")
    body.append(name, style="bold green")
    if args:
        try:
            import json

            args_obj = json.loads(args)
            args_str = json.dumps(args_obj, ensure_ascii=False, indent=2)
        except Exception:
            args_str = args
        body.append(f"\n{args_str[:200]}", style="dim")
    if result:
        body.append(f"\n→ {result[:300]}", style="tool_result")
    return Panel(body, border_style="green", box=MINIMAL, padding=(0, 2))


def build_interrupt_panel(name: str, args: str) -> Panel:
    """中断确认面板——等待用户批准危险操作"""
    body = Text()
    body.append("⏸ ", style="bold yellow")
    body.append(name, style="bold yellow")
    if args:
        try:
            import json

            args_obj = json.loads(args)
            args_str = json.dumps(args_obj, ensure_ascii=False, indent=2)
        except Exception:
            args_str = args
        body.append(f"\n{args_str[:300]}", style="dim")
    body.append("\n\n", style="dim")
    body.append("是否执行此操作？ [y/N] ", style="dim")
    return Panel(
        body,
        title="🔐 等待确认",
        title_align="left",
        border_style="yellow",
        box=MINIMAL,
        padding=(0, 2),
    )


# ═══════════════════════════════════════════
# 主 TUI 类
# ═══════════════════════════════════════════


class TUIChat:
    """Claude CLI 风格对话界面"""

    def __init__(self):
        self.agent = Agent()
        self.session: PromptSession | None = None
        self.conversation_log: list[dict] = []
        self._generating = False

    def _create_session(self) -> PromptSession:
        """创建 prompt_toolkit 输入会话"""
        bindings = KeyBindings()

        @bindings.add("enter")
        def _(event):
            """Enter: 发送消息"""
            event.current_buffer.validate_and_handle()

        @bindings.add("escape", "enter")
        def _(event):
            """Alt+Enter: 插入换行"""
            event.current_buffer.insert_text("\n")

        return PromptSession(
            history=FileHistory(str(HISTORY_FILE)),
            completer=CommandCompleter(),
            key_bindings=bindings,
            style=PT_STYLE,
            multiline=True,
            prompt_continuation=". ",
            wrap_lines=True,
        )

    def _check_interrupt(self) -> dict | None:
        """检查是否有挂起的中断。返回 HITLRequest 或 None。"""
        state = self.agent.assistant_agent.get_state(self.agent.config)
        interrupts = state.interrupts
        if not interrupts:
            return None
        return interrupts[0].value

    def _handle_interrupt(self, data: dict) -> list[dict]:
        """显示中断面板，获取用户确认。返回 decisions 列表。"""
        action_requests = data["action_requests"]
        decisions = []
        for ar in action_requests:
            name = ar["name"]
            args = ar.get("args", {})
            try:
                import json

                args_str = json.dumps(args, ensure_ascii=False, indent=2)
            except Exception:
                args_str = str(args)

            console.print(build_interrupt_panel(name, args_str))
            # 使用 msvcrt 直接读键，绕过 Live 后终端输入模式异常的问题
            decisions.append(self._confirm_input())
        return decisions

    def _confirm_input(self) -> dict:
        """使用 msvcrt 直接读取键盘输入，返回 decision dict。"""
        console.print("是否执行此操作？ [y/N] ", end="")
        chars: list[str] = []
        while True:
            ch = msvcrt.getwch()
            if ch in ("\r", "\n"):
                console.print()
                break
            if ch in ("\x08", "\x7f"):
                if chars:
                    chars.pop()
                    console.print("\b \b", end="")
                continue
            if ch == "\x03":
                console.print()
                raise KeyboardInterrupt
            console.print(ch, end="")
            chars.append(ch)
        resp = "".join(chars).strip().lower()
        return {"type": "approve" if resp in ("y", "yes") else "reject"}

    async def start(self):
        """启动 TUI"""
        await self.agent.start_agent()

        console.print()
        console.print(build_welcome())
        console.print()

        self.session = self._create_session()
        await self._main_loop()

    async def _main_loop(self):
        """主对话循环"""
        while True:
            try:
                user_input = await self.session.prompt_async(
                    HTML("<prompt>▸</prompt> "),
                )
            except KeyboardInterrupt:
                console.print("\n[info]输入 /exit 退出程序[/]\n")
                continue
            except EOFError:
                console.print("\n\n[info]👋 再见！[/]\n")
                return

            user_input = user_input.strip()
            if not user_input:
                continue

            # 处理命令
            if user_input.startswith("/"):
                should_exit = await self._handle_command(user_input)
                if should_exit:
                    return
                continue

            # 显示用户消息
            console.print()
            console.print(f"[user]⏺[/] [user]{user_input}[/]")
            console.print()

            # 流式获取并渲染回复
            try:
                await self._stream_response(user_input)
            except (KeyboardInterrupt, asyncio.CancelledError):
                console.print("\n[info]⏹ 已中断[/]\n")
            except Exception:
                import traceback

                console.print("\n[error]❌ 生成出错[/]\n")
                from rich.markup import escape

                console.print(escape(traceback.format_exc()), style="dim")
                console.print()

    async def _handle_command(self, cmd: str) -> bool:
        """处理 / 命令。返回 True 表示应退出。"""
        parts = cmd.strip().split(maxsplit=1)
        action = parts[0].lower()

        if action in ("/exit", "/quit", "/q"):
            console.print("\n[info]👋 再见！[/]\n")
            return True

        elif action == "/help":
            self._cmd_help()

        elif action == "/clear":
            console.clear()
            console.print(build_welcome())
            console.print()

        elif action == "/model":
            name = parts[1] if len(parts) > 1 else ""
            if not name:
                current = registry.get().__class__.__name__
                models = registry.list_models()
                console.print(f"[dim]当前模型:[/] [highlight]{current}[/]")
                console.print(f"[dim]可用模型:[/] {', '.join(models)}")
                console.print(f"[dim]用法: /model <模型名>[/]\n")
            elif name not in registry.list_models():
                console.print(
                    f"[error]模型 '{name}' 不存在，可用: {registry.list_models()}[/]\n"
                )
            else:
                await self.agent.reload_agent(name)
                registry.update(name)
                console.print(f"[info]已切换到 {name}[/]\n")

        elif action == "/save":
            self._cmd_save()

        elif action == "/history":
            self._cmd_history()

        else:
            console.print(f"[error]未知命令: {action}，输入 /help 查看帮助[/]\n")

        return False

    def _cmd_help(self):
        t = Text()
        t.append("\n📖 命令列表\n\n", style="bold bright_white")
        for cmd, desc in [
            ("/help", "显示此帮助"),
            ("/clear", "清空屏幕"),
            ("/model", "切换模型"),
            ("/exit", "退出程序"),
            ("/save", "保存对话到 Markdown 文件"),
            ("/history", "显示本轮对话历史摘要"),
        ]:
            t.append(f"  {cmd:<10}", style="dim")
            t.append(f"{desc}\n", style="info")
        t.append("\n⌨ 快捷键\n\n", style="bold bright_white")
        for key, desc in [
            ("Enter", "发送消息"),
            ("Alt+Enter", "换行"),
            ("Ctrl+C", "中断 AI 生成"),
            ("Ctrl+D", "退出程序"),
            ("↑ / ↓", "浏览输入历史"),
        ]:
            t.append(f"  {key:<10}", style="dim")
            t.append(f"{desc}\n", style="info")
        console.print(Panel(t, title="Help", border_style="info", padding=(1, 2)))
        console.print()

    def _cmd_save(self):
        if not self.conversation_log:
            console.print("[dim]暂无对话记录[/]\n")
            return
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        save_path = Path.cwd() / f"conversation_{ts}.md"
        with open(save_path, "w", encoding="utf-8") as f:
            f.write(
                f"# Deep Agent 对话记录\n\n保存时间: {datetime.now().isoformat()}\n\n---\n\n"
            )
            for i, entry in enumerate(self.conversation_log, 1):
                f.write(f"## 第 {i} 轮\n\n**⏺ 用户**: {entry['user']}\n\n")
                if entry.get("thinking"):
                    f.write(
                        f"<details>\n<summary>💭 思考过程</summary>\n\n{entry['thinking']}\n\n</details>\n\n"
                    )
                if entry.get("tool_calls"):
                    f.write("**🔧 工具调用**:\n\n")
                    for tc in entry["tool_calls"]:
                        f.write(f"- `{tc['name']}`\n")
                        if tc.get("args"):
                            f.write(f"  - 入参: `{tc['args'][:200]}`\n")
                        if tc.get("result"):
                            f.write(f"  - 结果: {tc['result'][:300]}\n")
                    f.write("\n")
                f.write(f"**🤖 助手**:\n\n{entry['answer']}\n\n---\n\n")
        console.print(f"[info]✅ 已保存到 {save_path}[/]\n")

    def _cmd_history(self):
        if not self.conversation_log:
            console.print("[dim]暂无对话记录[/]\n")
            return
        console.print()
        for i, entry in enumerate(self.conversation_log, 1):
            preview = entry["user"][:80] + ("…" if len(entry["user"]) > 80 else "")
            console.print(f"  [dim]{i:>2}.[/] [user]{preview}[/]")
        console.print()

    # ── 流式响应核心 ──

    async def _stream_response(self, user_input: str):
        """流式获取 Agent 回复并实时渲染

        - 思考：流式 dim 输出
        - 答案：打字机流式 → ANSI 回退 → Markdown 原地重渲染，无重复
        """
        thinking_text = ""
        answer_text = ""
        tool_calls: list[dict] = []
        thinking_header_printed = False
        answer_header_printed = False
        in_thinking = False
        cursor_saved = False

        current_input = {"messages": [{"role": "user", "content": user_input}]}

        try:
            while True:
                async for token, metadata in self.agent.assistant_agent.astream(
                    current_input,
                    config={
                        **self.agent.config,
                        "callbacks": [self.agent.tracer],
                    },
                    stream_mode="messages",
                ):
                    node = metadata.get("langgraph_node")

                    if node == "model":
                        # ── 思考（流式）──
                        reasoning = (token.additional_kwargs or {}).get(
                            "reasoning_content", ""
                        ) or ""
                        if reasoning:
                            if not thinking_header_printed:
                                console.print()
                                console.print("▌💭 思考中", style="bold dim cyan")
                                console.print()
                                thinking_header_printed = True
                                in_thinking = True
                            thinking_text += reasoning
                            console.print(reasoning, end="", style="thinking")

                        # ── 答案（打字机流式 + 累积）──
                        if token.content:
                            content_piece = ""
                            if isinstance(token.content, str):
                                content_piece = token.content
                            elif isinstance(token.content, list):
                                for block in token.content:
                                    if isinstance(block, dict):
                                        content_piece += block.get("text", "")
                                    else:
                                        content_piece += str(block)
                            if content_piece:
                                if not answer_header_printed:
                                    if in_thinking:
                                        console.print()
                                        console.print()
                                    # 在打印答案头之前保存光标
                                    console.file.write("\033[s")
                                    console.file.flush()
                                    cursor_saved = True
                                    console.print()
                                    console.print(
                                        "▌🤖 回答", style="bold bright_white"
                                    )
                                    console.print()
                                    answer_header_printed = True
                                    in_thinking = False
                                answer_text += content_piece
                                console.print(content_piece, end="")

                        # ── 工具调用 ──
                        tc_chunks = (token.additional_kwargs or {}).get(
                            "tool_calls", []
                        )
                        for tc in tc_chunks:
                            tc_id = tc.get("id")
                            tc_idx = tc.get("index", 0)
                            func = tc.get("function", {})

                            existing = None
                            if tc_id:
                                for entry in tool_calls:
                                    if entry["id"] == tc_id:
                                        existing = entry
                                        break
                            if existing is None and tc_idx < len(tool_calls):
                                candidate = tool_calls[tc_idx]
                                if (
                                    not candidate["id"]
                                    or not tc_id
                                    or candidate["id"] == tc_id
                                ):
                                    existing = candidate
                            if existing is None:
                                existing = {"id": "", "name": "", "args": ""}
                                tool_calls.append(existing)
                            if tc_id:
                                existing["id"] = tc_id
                            if func.get("name"):
                                existing["name"] += func["name"]
                            if func.get("arguments"):
                                existing["args"] += func["arguments"]

                    elif node == "tools":
                        tc_id = getattr(token, "tool_call_id", "")
                        tc_content = getattr(token, "content", "")
                        if tc_id:
                            for tc in tool_calls:
                                if tc.get("id") == tc_id:
                                    tc["result"] = tc_content[:500]
                                    break

                # ── 一轮 stream 结束 ──
                interrupt_data = self._check_interrupt()
                if not interrupt_data:
                    break

                decisions = self._handle_interrupt(interrupt_data)
                thinking_text = ""
                answer_text = ""
                tool_calls = []
                thinking_header_printed = False
                answer_header_printed = False
                in_thinking = False
                cursor_saved = False
                current_input = Command(resume={"decisions": decisions})

        finally:
            pass

        # ── ANSI 回退 → Markdown 重渲染 ──
        if cursor_saved and answer_text:
            console.file.write("\033[u")  # 回到答案区起点
            console.file.write("\033[J")  # 清至屏底
            console.file.flush()
        if answer_text:
            console.print()
            console.print("▌🤖 回答", style="bold bright_white")
            console.print()
            console.print(Markdown(answer_text))

        # ── 工具调用面板 ──
        for tc in tool_calls:
            if tc.get("name"):
                console.print()
                console.print(
                    build_tool_panel(
                        tc["name"], tc.get("args", ""), tc.get("result", "")
                    )
                )

        if not thinking_text and not answer_text and not tool_calls:
            console.print("[dim](无输出)[/]")

        console.print()

        self.conversation_log.append(
            {
                "time": datetime.now().isoformat(),
                "user": user_input,
                "thinking": thinking_text,
                "answer": answer_text,
                "tool_calls": [
                    {
                        "name": tc["name"],
                        "args": tc.get("args", ""),
                        "result": tc.get("result", ""),
                    }
                    for tc in tool_calls
                    if tc.get("name")
                ],
            }
        )


async def tui_main():
    tui = TUIChat()
    await tui.start()


if __name__ == "__main__":
    asyncio.run(tui_main())
