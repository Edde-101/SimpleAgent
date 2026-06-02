from datetime import datetime

from tools import mcp, internet_search


# 用装饰器暴露一个工具
@mcp.tool()
def add(a: int, b: int) -> int:
    """两个数字相加"""
    return a + b


@mcp.tool()
def get_time():
    """
    获取当前的系统时间
    """
    # 本地时间（系统时区）
    local_time = datetime.now()
    time_str = "本地时间:" + local_time.strftime("%Y-%m-%d %H:%M:%S")
    return time_str


# 启动服务器（默认通过 stdio 通信）
if __name__ == "__main__":
    mcp.run(transport="stdio")
