from tools import mcp, internet_search


# 用装饰器暴露一个工具
@mcp.tool()
def add(a: int, b: int) -> int:
    """两个数字相加"""
    return a + b


# 启动服务器（默认通过 stdio 通信）
if __name__ == "__main__":
    mcp.run(transport="stdio")
