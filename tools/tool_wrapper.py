import asyncio
import functools
import inspect

DEFAULT_RETRY_CONFIG = {
    "max_retries": 3,
    "base_delay": 1.0,
    "backoff": 2.0,  # 指数退避: 1s → 2s → 4s
}

# 可按工具名定制策略
TOOL_RETRY_CONFIG = {
    "internet_search": {"max_retries": 2, "base_delay": 2.0},
    "add": {"max_retries": 0},  # 计算工具无需重试
}


def wrap_tool_with_retry(tool, config=None):
    """给单个工具包装重试+超时"""
    cfg = {**DEFAULT_RETRY_CONFIG, **(config or {})}
    original = tool.func  # 原始 async 函数

    @functools.wraps(original)
    async def wrapped(*args, **kwargs):
        last_error = None
        for attempt in range(cfg["max_retries"] + 1):  # +1 = 首次执行也算在内
            try:
                if inspect.iscoroutinefunction()(original):
                    return await original(*args, **kwargs)
                else:
                    return original(*args, **kwargs)

            except Exception as e:
                last_error = e
                if attempt < cfg["max_retries"]:
                    delay = cfg["base_delay"] * (cfg["backoff"] ** attempt)
                    await asyncio.sleep(delay)
        # 全部重试失败 → 返回错误文本而不是抛异常
        tool_name = getattr(tool, "name", "unknown")
        return f"工具 '{tool_name}' 执行失败（重试{cfg['max_retries']}次）: {str(last_error)}"

    tool.func = wrapped
    return tool
