"""
Corax Orchestrator - AI Provider Abstraction Layer.

Provides a unified interface for AI model providers (LM Studio, Ollama,
OpenAI-compatible APIs, etc.) enabling the agent to use local and remote
AI models for reasoning, planning, and decision-making.

Architecture:
    providers/
    ├── __init__.py          # Package exports
    ├── base.py              # Abstract base provider
    ├── lm_studio.py         # LM Studio provider
    ├── ollama.py            # Ollama provider
    ├── openai_compat.py     # OpenAI-compatible API provider
    └── registry.py          # Provider registry and discovery
"""

from src.agent.providers.base import AIProvider, ProviderConfig, ModelInfo, CompletionResult
from src.agent.providers.registry import ProviderRegistry

__all__ = [
    "AIProvider",
    "ProviderConfig",
    "ModelInfo",
    "CompletionResult",
    "ProviderRegistry",
]
