import os
from typing import Literal
from tavily import TavilyClient
from mcp.server.fastmcp import FastMCP
from dotenv import load_dotenv

load_dotenv()
# 创建一个 MCP 服务器
mcp = FastMCP("General Server")

tavily_client = TavilyClient(api_key=os.environ["TAVILY_API_KEY"])


@mcp.tool()
def internet_search(
    query: str,
    max_results: int = 5,
    topic: Literal["general", "news", "finance"] = "general",
    include_raw_content: bool = False,
):
    """网络搜索工具,使用tavily更加精细化的在线搜索"""
    return tavily_client.search(
        query,
        max_results=max_results,
        include_raw_content=include_raw_content,
        topic=topic,
    )
