from langchain.chat_models import init_chat_model
from langchain_core.messages import AIMessage
from dotenv import load_dotenv
import os
from typing import Union, Dict, Any
from langchain_deepseek import ChatDeepSeek
from typing import List
import httpx
from langchain_openai import OpenAIEmbeddings

load_dotenv()

ALI_URL = os.getenv("ALI_URL")
ALI_KEY = os.getenv("ALI_KEY")
DP_URL = os.getenv("DEEPSEEK_URL")
DP_KEY = os.getenv("DEEPSEEK_KEY")
DP_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")


model = ChatDeepSeek(
    model="deepseek-v4-pro",  # 模型名称
    api_key=DP_KEY,  # API密钥
    thinking={"type": "enabled"},  # 启用思考模式
    reasoning_effort="high",  # 设置思考强度
    temperature=0.3,  # 控制随机性
    timeout=60,  # 设置超时时间
)

# 向量模型（BGE 中文 Embedding）
_embedding_url = os.environ["EMBEDDING_URL"]
# OpenAI client 会自动追加 /embeddings，这里去重防止 404
if _embedding_url.endswith("/embeddings"):
    _embedding_url = _embedding_url[: -len("/embeddings")]
embeddings = OpenAIEmbeddings(
    model="BAAI/bge-large-zh-v1.5",
    api_key=os.environ["EMBEDDING_KEY"],
    base_url=_embedding_url,
)
