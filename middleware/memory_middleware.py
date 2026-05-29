from deepagents.middleware.memory import MemoryMiddleware

from deepagents.backends import FilesystemBackend
from langchain.agents.middleware.pii import PIIMiddleware
import os

base_dir = os.path.dirname(os.path.abspath(__file__))

backend = FilesystemBackend(root_dir=base_dir, virtual_mode=True)
memory_middleware = MemoryMiddleware(
    backend=backend,
    sources=[
        "~/.deepagent/AGENTS.md",  # 1. 全局配置（用户级）
        "./.deepagent/AGENTS.md",  # 2. 项目配置（项目级），覆盖或补充全局配置
    ],
)
pii_middleware = PIIMiddleware(
    pii_type="api_key",
    detector=r"sk-[a-zA-Z0-9]{32}",  # 自定义正则
    strategy="block",
    apply_to_input=True,
    apply_to_output=True,  # 同时对模型输出进行检测
)
