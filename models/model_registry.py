import importlib
import os

# import yaml
from pathlib import Path
from ruamel.yaml import YAML

yaml = YAML()


class ModelRegistry:
    def __init__(self, config_path: str):
        self.config_path = config_path
        with open(self.config_path, "r") as f:
            self.old_config = yaml.load(f)
        raw = Path(config_path).read_text()
        for key, val in os.environ.items():
            raw = raw.replace(f"${{{key}}}", val)

        self.config = yaml.load(raw)
        self._chat_instances: dict[str, object] = {}
        self._embedding_instances: dict[str, object] = {}

    # ── Chat 模型 ──

    def _resolve_chat_cls(self, provider: str):
        """provider → Chat 模型类（懒加载）"""
        if provider == "deepseek":
            from langchain_deepseek import ChatDeepSeek

            return ChatDeepSeek
        if provider == "anthropic":
            from langchain_anthropic import ChatAnthropic

            return ChatAnthropic
        if provider == "openai" or provider == "openai_compatible":
            from langchain_openai import ChatOpenAI

            return ChatOpenAI
        if "." in provider:
            module_path, class_name = provider.rsplit(".", 1)
            module = importlib.import_module(module_path)
            return getattr(module, class_name)
        # 未知 → 当作 OpenAI 兼容
        from langchain_openai import ChatOpenAI

        return ChatOpenAI

    def get(self, name: str = None):
        """按名称取模型，不传则用 default"""
        name = name or self.config["default"]
        if name not in self._chat_instances:
            self._chat_instances[name] = self._build_chat(name)
        return self._chat_instances[name]

    def _build_chat(self, name: str):
        cfg = dict(self.config["models"][name])
        provider = cfg.pop("provider", "openai_compatible")
        cls = self._resolve_chat_cls(provider)
        extra = cfg.pop("extra_params", {})
        # 所有模型统一开启流式输出，确保 TUI 实时渲染
        cfg.setdefault("streaming", True)
        return cls(**cfg, **extra)

    def list_models(self) -> list[str]:
        return list(self.config["models"].keys())

    def update(self, default_model_name: str = None):
        if default_model_name:
            self.config["default"] = default_model_name
            self.old_config["default"] = default_model_name
        with open(self.config_path, "w") as f:
            yaml.dump(self.old_config, f)

    # ── Embedding 模型 ──

    def get_embedding(self, name: str = None):
        """按名称取 Embedding 模型，不传则用 models_embedding.default"""
        name = name or self.config["models_embedding"]["default"]
        if name not in self._embedding_instances:
            self._embedding_instances[name] = self._build_embedding(name)
        return self._embedding_instances[name]

    def _build_embedding(self, name: str):
        from langchain_openai import OpenAIEmbeddings

        cfg = dict(self.config["models_embedding"][name])
        cfg.pop("provider", None)
        extra = cfg.pop("extra_params", {})

        # OpenAI client 自动追加 /embeddings，这里去重防止 404
        base_url = cfg.get("base_url", "")
        if base_url.endswith("/embeddings"):
            cfg["base_url"] = base_url[: -len("/embeddings")]

        return OpenAIEmbeddings(**cfg, **extra)


base_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(base_dir)
# 全局单例
registry = ModelRegistry(f"{parent_dir}/models.yaml")
