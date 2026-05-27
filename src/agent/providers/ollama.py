"""
Corax Orchestrator - Ollama Provider.

Implements the AIProvider interface for Ollama's local API.
Ollama provides a simple local API for running LLMs with
built-in model management.
"""

from typing import Dict, Any, List, Optional, AsyncIterator
import json
import time
import aiohttp

from src.core.logging import get_logger
from src.agent.providers.base import (
    AIProvider,
    ProviderConfig,
    ModelInfo,
    CompletionResult,
)

logger = get_logger(__name__)


class OllamaProvider(AIProvider):
    """
    Provider for Ollama's local API.

    Ollama runs models locally and exposes an API at
    http://localhost:11434 by default.
    """

    @property
    def provider_name(self) -> str:
        return "ollama"

    async def list_models(self) -> List[ModelInfo]:
        """List models available in Ollama."""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.config.api_base_url}/api/tags",
                    timeout=aiohttp.ClientTimeout(total=self.config.timeout_seconds),
                ) as response:
                    if response.status != 200:
                        logger.error(
                            "Failed to list Ollama models",
                            status=response.status,
                        )
                        return []

                    data = await response.json()
                    models = []

                    for model_data in data.get("models", []):
                        model_name = model_data.get("name", "")
                        models.append(ModelInfo(
                            id=model_name,
                            name=model_name,
                            provider=self.provider_name,
                            size_bytes=model_data.get("size"),
                            loaded=False,
                            metadata=model_data,
                        ))

                    return models

        except aiohttp.ClientError as e:
            logger.error("Ollama connection error", error=str(e))
            return []
        except Exception as e:
            logger.error("Ollama list models error", error=str(e))
            return []

    async def complete(
        self,
        prompt: str,
        model: Optional[str] = None,
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        stop: Optional[List[str]] = None,
    ) -> CompletionResult:
        """Generate a completion using Ollama."""
        start_time = time.time()

        payload = {
            "prompt": prompt,
            "temperature": temperature,
            "stream": False,
        }

        if model:
            payload["model"] = model
        if system_prompt:
            payload["system"] = system_prompt
        if max_tokens:
            payload["num_predict"] = max_tokens
        if stop:
            payload["stop"] = stop

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.config.api_base_url}/api/generate",
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=self.config.timeout_seconds),
                ) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        raise RuntimeError(
                            f"Ollama API error {response.status}: {error_text}"
                        )

                    data = await response.json()
                    duration_ms = (time.time() - start_time) * 1000

                    return CompletionResult(
                        text=data.get("response", ""),
                        model=data.get("model", model or "unknown"),
                        provider=self.provider_name,
                        finish_reason="stop",
                        usage={
                            "prompt_tokens": data.get("prompt_eval_count", 0),
                            "completion_tokens": data.get("eval_count", 0),
                            "total_tokens": (
                                data.get("prompt_eval_count", 0)
                                + data.get("eval_count", 0)
                            ),
                        },
                        duration_ms=duration_ms,
                    )

        except aiohttp.ClientError as e:
            logger.error("Ollama completion error", error=str(e))
            raise

    async def complete_stream(
        self,
        prompt: str,
        model: Optional[str] = None,
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
    ) -> AsyncIterator[str]:
        """Stream a completion from Ollama."""
        payload = {
            "prompt": prompt,
            "temperature": temperature,
            "stream": True,
        }

        if model:
            payload["model"] = model
        if system_prompt:
            payload["system"] = system_prompt
        if max_tokens:
            payload["num_predict"] = max_tokens

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.config.api_base_url}/api/generate",
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=self.config.timeout_seconds),
                ) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        raise RuntimeError(
                            f"Ollama API error {response.status}: {error_text}"
                        )

                    async for line in response.content:
                        if line:
                            try:
                                data = json.loads(line)
                                content = data.get("response", "")
                                if content:
                                    yield content
                                if data.get("done", False):
                                    break
                            except json.JSONDecodeError:
                                continue

        except aiohttp.ClientError as e:
            logger.error("Ollama stream error", error=str(e))
            raise

    async def is_available(self) -> bool:
        """Check if Ollama is running and responsive."""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.config.api_base_url}/api/tags",
                    timeout=aiohttp.ClientTimeout(total=5),
                ) as response:
                    return response.status == 200
        except Exception:
            return False

    async def get_model_info(self, model_id: str) -> Optional[ModelInfo]:
        """Get info about a specific model in Ollama."""
        models = await self.list_models()
        for model in models:
            if model.id == model_id:
                return model
        return None

    async def pull_model(self, model_name: str) -> bool:
        """
        Pull a model from Ollama's registry.

        Args:
            model_name: Name of the model to pull

        Returns:
            True if successful
        """
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.config.api_base_url}/api/pull",
                    json={"name": model_name},
                    timeout=aiohttp.ClientTimeout(total=600),
                ) as response:
                    return response.status == 200
        except Exception as e:
            logger.error("Ollama pull model error", error=str(e))
            return False
