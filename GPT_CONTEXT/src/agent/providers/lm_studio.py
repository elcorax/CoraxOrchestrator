"""
Corax Orchestrator - LM Studio Provider.

Implements the AIProvider interface for LM Studio's local API server.
LM Studio provides a local OpenAI-compatible API for running LLMs.
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


class LMStudioProvider(AIProvider):
    """
    Provider for LM Studio's local API.

    LM Studio runs models locally and exposes an OpenAI-compatible
    API at http://localhost:1234 by default.
    """

    @property
    def provider_name(self) -> str:
        return "lm_studio"

    async def list_models(self) -> List[ModelInfo]:
        """List models available in LM Studio."""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.config.api_base_url}/v1/models",
                    timeout=aiohttp.ClientTimeout(total=self.config.timeout_seconds),
                ) as response:
                    if response.status != 200:
                        logger.error(
                            "Failed to list LM Studio models",
                            status=response.status,
                        )
                        return []

                    data = await response.json()
                    models = []

                    for model_data in data.get("data", []):
                        model_id = model_data.get("id", "")
                        models.append(ModelInfo(
                            id=model_id,
                            name=model_id,
                            provider=self.provider_name,
                            loaded=True,
                            metadata=model_data,
                        ))

                    return models

        except aiohttp.ClientError as e:
            logger.error("LM Studio connection error", error=str(e))
            return []
        except Exception as e:
            logger.error("LM Studio list models error", error=str(e))
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
        """Generate a completion using LM Studio."""
        start_time = time.time()
        messages = []

        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        payload = {
            "messages": messages,
            "temperature": temperature,
            "stream": False,
        }

        if model:
            payload["model"] = model
        if max_tokens:
            payload["max_tokens"] = max_tokens
        if stop:
            payload["stop"] = stop

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.config.api_base_url}/v1/chat/completions",
                    json=payload,
                    headers={"Content-Type": "application/json"},
                    timeout=aiohttp.ClientTimeout(total=self.config.timeout_seconds),
                ) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        raise RuntimeError(
                            f"LM Studio API error {response.status}: {error_text}"
                        )

                    data = await response.json()
                    choice = data["choices"][0]
                    usage = data.get("usage", {})

                    duration_ms = (time.time() - start_time) * 1000

                    return CompletionResult(
                        text=choice["message"]["content"],
                        model=data.get("model", model or "unknown"),
                        provider=self.provider_name,
                        finish_reason=choice.get("finish_reason", "stop"),
                        usage={
                            "prompt_tokens": usage.get("prompt_tokens", 0),
                            "completion_tokens": usage.get("completion_tokens", 0),
                            "total_tokens": usage.get("total_tokens", 0),
                        },
                        duration_ms=duration_ms,
                    )

        except aiohttp.ClientError as e:
            logger.error("LM Studio completion error", error=str(e))
            raise

    async def complete_stream(
        self,
        prompt: str,
        model: Optional[str] = None,
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
    ) -> AsyncIterator[str]:
        """Stream a completion from LM Studio."""
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        payload = {
            "messages": messages,
            "temperature": temperature,
            "stream": True,
        }

        if model:
            payload["model"] = model
        if max_tokens:
            payload["max_tokens"] = max_tokens

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.config.api_base_url}/v1/chat/completions",
                    json=payload,
                    headers={"Content-Type": "application/json"},
                    timeout=aiohttp.ClientTimeout(total=self.config.timeout_seconds),
                ) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        raise RuntimeError(
                            f"LM Studio API error {response.status}: {error_text}"
                        )

                    async for line in response.content:
                        if line:
                            line = line.decode("utf-8").strip()
                            if line.startswith("data: "):
                                data_str = line[6:]
                                if data_str == "[DONE]":
                                    break
                                try:
                                    data = json.loads(data_str)
                                    delta = data["choices"][0].get("delta", {})
                                    content = delta.get("content", "")
                                    if content:
                                        yield content
                                except json.JSONDecodeError:
                                    continue

        except aiohttp.ClientError as e:
            logger.error("LM Studio stream error", error=str(e))
            raise

    async def is_available(self) -> bool:
        """Check if LM Studio is running and responsive."""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.config.api_base_url}/v1/models",
                    timeout=aiohttp.ClientTimeout(total=5),
                ) as response:
                    return response.status == 200
        except Exception:
            return False

    async def get_model_info(self, model_id: str) -> Optional[ModelInfo]:
        """Get info about a specific model in LM Studio."""
        models = await self.list_models()
        for model in models:
            if model.id == model_id:
                return model
        return None
