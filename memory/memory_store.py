import os
from datetime import datetime

from dotenv import load_dotenv
from langchain.tools import tool
from langchain_chroma import Chroma
from langchain_openai import OpenAIEmbeddings
from models.models import embeddings
from models.model_registry import registry

load_dotenv()

base_dir = os.path.dirname(os.path.abspath(__file__))

# ————————————长期记忆，供后续对话使用——————————————————


# 创建 Chroma 向量数据库
vector_store = Chroma(
    collection_name="agent_memory",
    embedding_function=registry.get_embedding(),
    persist_directory=os.path.join(base_dir, "chroma_db"),
)
# ——————————tool 函数 对向量数据库进行io————————————————————


@tool
def remember(content: str, category: str = "general") -> str:
    """将重要的用户偏好、决策或背景信息存入长期记忆，供后续对话使用。

    当用户分享了以下内容时，你应当使用此工具：
    - 个人偏好（喜欢的饮品、工作习惯、沟通风格等）
    - 重要背景（职业、项目、家庭成员等）
    - 决策记录（用户做出的选择、优先事项等）
    - 重要事件
    - 值得在后续对话中保留的任何事实

    Args:
        content: 要记住的具体内容
        category: 分类标签，如 preference、contact、project、note
    """
    metadata = {
        "category": category,
        "timestamp": datetime.now().isoformat(),
    }
    vector_store.add_texts(texts=[content], metadatas=[metadata])
    return f"已记住: {content}"


@tool
def recall(query: str, n_results: int = 5) -> str:
    """从长期记忆中搜索相关的用户偏好、历史对话或已存储信息。

    在处理用户请求前，先用此工具检查是否有相关的历史记忆，
    确保你的回答基于用户已知的偏好和上下文。

    Args:
        query: 搜索查询，描述你需要查找的信息
        n_results: 返回结果数量，默认 5
    """
    docs_with_scores = vector_store.similarity_search_with_relevance_scores(
        query, k=n_results
    )
    if not docs_with_scores:
        return "未找到相关记忆。"

    lines = []
    for i, (doc, score) in enumerate(docs_with_scores, 1):
        cat = doc.metadata.get("category", "-")
        ts = doc.metadata.get("timestamp", "")[:10]
        lines.append(f"{i}. [{cat}] {doc.page_content} ({ts}) [相关度: {score:.2f}]")
    return "\n".join(lines)


@tool
def forget(query: str) -> str:
    """删除长期记忆中的某条信息。

    当用户明确要求删除、更正或表示某条记忆不再需要时，使用此工具。
    支持精确内容匹配和语义模糊匹配两种删除方式。

    Args:
        query: 要删除的记忆内容或描述
    """
    all_data = vector_store.get()
    if not all_data["ids"]:
        return "记忆库为空，没有可删除的内容。"

    q = query.strip().lower()

    # 1. 精确/包含匹配优先
    for i, doc_text in enumerate(all_data["documents"]):
        if q == doc_text.strip().lower() or q in doc_text.strip().lower():
            doc_id = all_data["ids"][i]
            vector_store.delete(ids=[doc_id])
            return f"已删除记忆: {doc_text[:100]}"

    # 2. 语义相似度兜底
    docs = vector_store.similarity_search(query, k=1)
    if not docs:
        return "未找到匹配的记忆。"

    match_content = docs[0].page_content
    for i, doc_text in enumerate(all_data["documents"]):
        if doc_text == match_content:
            doc_id = all_data["ids"][i]
            vector_store.delete(ids=[doc_id])
            return f"已删除最相似记忆: {doc_text[:100]}"

    return "未找到匹配的记忆。"
