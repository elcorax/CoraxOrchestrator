"""
Corax Orchestrator - AI Provider Base.

Defines the abstract base class for all AI model providers.
Provides a unified interface for completion, embedding, and
model management operations.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, Any, List, Optional, AsyncIterator


@dataclass
class ProviderConfig:
    """Configuration for an AI provider."""
    api_base_url: str = "http://localhost:1234"
    api_key: Optional[str] = None
    timeout_seconds: int = 60
    max_retries: int = 3
    organization: Optional[str] = None
    extra_headers: Dict[str, str] = field(default_factory=dict)
    extra_params: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ModelInfo:
    """Information about an available model."""
    id: str
    name: str
    provider: str
    size_bytes: Optional[int] = None
    quantization: Optional[str] = None
    context_length: Optional[int] = None
    loaded: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class CompletionResult:
    """Result of a model completion request."""
    text: str
    model: str
    provider: str
    finish_reason: str = "stop"
    usage: Dict[str, int] = field(default_factory=lambda: {
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
    })
    duration_ms: Optional[float] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


class AIProvider(ABC):
    """
    Abstract base class for AI model providers.

    All providers (LM Studio, Ollama, OpenAI-compatible, etc.)
    must implement this interface to be used by the agent runtime.
    """

    def __init__(self, config: ProviderConfig) -> None:
        self.config = config
        self._name: str = self.__class__.__name__

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Get the provider name (e.g., 'lm_studio', 'ollama')."""
        ...

    @abstractmethod
    async def list_models(self) -> List[ModelInfo]:
        """List all available models from this provider."""
        ...

    @abstractmethod
    async def complete(
        self,
        prompt: str,
        model: Optional[str] = None,
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        stop: Optional[List[str]] = None,
    ) -> CompletionResult:
        """
        Generate a completion from the model.

        Args:
            prompt: The input prompt
            model: Model ID to use (uses default if None)
            system_prompt: Optional system-level instruction
            temperature: Sampling temperature (0.0 to 1.0)
            max_tokens: Maximum tokens to generate
            stop: Stop sequences

        Returns:
            CompletionResult with generated text
        """
        ...

    @abstractmethod
    async def complete_stream(
        self,
        prompt: str,
        model: Optional[str] = None,
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
    ) -> AsyncIterator[str]:
        """
        Stream a completion from the model.

        Args:
            prompt: The input prompt
            model: Model ID to use
            system_prompt: Optional system-level instruction
            temperature: Sampling temperature
            max_tokens: Maximum tokens to generate

        Yields:
            Text chunks as they are generated
        """
        ...

    @abstractmethod
    async def is_available(self) -> bool:
        """Check if the provider is available and responsive."""
        ...

    @abstractmethod
    async def get_model_info(self, model_id: str) -> Optional[ModelInfo]:
        """Get detailed information about a specific model."""
        ...

    async def embed(
        self,
        text: str,
        model: Optional[str] = None,
    ) -> List[float]:
        """
        Generate embeddings for text.

        Args:
            text: Text to embed
            model: Model ID to use

        Returns:
            Embedding vector as list of floats
        """
        raise NotImplementedError(f"{self.provider_name} does not support embeddings")

    async def health_check(self) -> Dict[str, Any]:
        """
        Perform a health check on the provider.

        Returns:
            Dict with status information
        """
        available = await self.is_available()
        models = await self.list_models() if available else []
        return {
            "provider": self.provider_name,
            "available": available,
            "models_available": len(models),
            "api_base": self.config.api_base_url,
        }

    def to_dict(self) -> Dict[str, Any]:
        """Serialize provider info to dictionary."""
        return {
            "provider": self.provider_name,
            "api_base": self.config.api_base_url,
            "timeout": self.config.timeout_seconds,
        }
