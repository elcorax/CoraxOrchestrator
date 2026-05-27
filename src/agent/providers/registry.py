"""
Corax Orchestrator - Provider Registry.

Manages discovery, registration, and lifecycle of AI model providers.
Supports automatic provider detection and fallback chains.
"""

from typing import Dict, Any, List, Optional, Type
import asyncio

from src.core.logging import get_logger
from src.agent.providers.base import AIProvider, ProviderConfig, ModelInfo, CompletionResult

logger = get_logger(__name__)


class ProviderRegistry:
    """
    Registry for AI model providers.

    Manages provider registration, discovery, and selection.
    Supports automatic detection of available providers and
    fallback chains for high availability.
    """

    def __init__(self) -> None:
        self._providers: Dict[str, AIProvider] = {}
        self._provider_classes: Dict[str, Type[AIProvider]] = {}
        self._default_provider: Optional[str] = None
        self._fallback_chain: List[str] = []

    def register_provider_class(
        self,
        name: str,
        provider_class: Type[AIProvider],
    ) -> None:
        """
        Register a provider class for later instantiation.

        Args:
            name: Provider name (e.g., 'lm_studio', 'ollama')
            provider_class: The provider class to register
        """
        self._provider_classes[name] = provider_class
        logger.debug("Provider class registered", name=name)

    def register_instance(
        self,
        name: str,
        provider: AIProvider,
        make_default: bool = False,
    ) -> None:
        """
        Register an already-instantiated provider.

        Args:
            name: Provider name
            provider: Provider instance
            make_default: Whether to set as default
        """
        self._providers[name] = provider
        if make_default or self._default_provider is None:
            self._default_provider = name
        logger.info("Provider instance registered", name=name)

    def create_provider(
        self,
        name: str,
        config: Optional[ProviderConfig] = None,
        make_default: bool = False,
    ) -> Optional[AIProvider]:
        """
        Create and register a provider instance.

        Args:
            name: Provider name matching a registered class
            config: Provider configuration
            make_default: Whether to set as default

        Returns:
            The created provider, or None if class not found
        """
        provider_class = self._provider_classes.get(name)
        if not provider_class:
            logger.error("Provider class not found", name=name)
            return None

        provider = provider_class(config or ProviderConfig())
        self.register_instance(name, provider, make_default)
        return provider

    def get_provider(self, name: Optional[str] = None) -> Optional[AIProvider]:
        """
        Get a provider by name, or the default provider.

        Args:
            name: Provider name (uses default if None)

        Returns:
            The provider instance, or None
        """
        if name:
            return self._providers.get(name)
        if self._default_provider:
            return self._providers.get(self._default_provider)
        # Return first available
        for provider in self._providers.values():
            return provider
        return None

    def remove_provider(self, name: str) -> bool:
        """Remove a provider from the registry."""
        if name in self._providers:
            del self._providers[name]
            if self._default_provider == name:
                self._default_provider = (
                    next(iter(self._providers)) if self._providers else None
                )
            logger.info("Provider removed", name=name)
            return True
        return False

    def set_default(self, name: str) -> bool:
        """Set the default provider."""
        if name in self._providers:
            self._default_provider = name
            logger.info("Default provider set", name=name)
            return True
        return False

    def set_fallback_chain(self, provider_names: List[str]) -> None:
        """
        Set the fallback chain for provider selection.

        When the primary provider fails, the next in the chain
        will be tried automatically.

        Args:
            provider_names: Ordered list of provider names
        """
        self._fallback_chain = [
            name for name in provider_names if name in self._providers
        ]
        logger.info("Fallback chain set", chain=self._fallback_chain)

    async def get_available_providers(self) -> List[str]:
        """Get list of providers that are currently available."""
        available = []
        for name, provider in self._providers.items():
            try:
                if await provider.is_available():
                    available.append(name)
            except Exception:
                pass
        return available

    async def discover_providers(
        self,
        configs: Optional[Dict[str, ProviderConfig]] = None,
    ) -> List[str]:
        """
        Discover and register available providers.

        Checks each registered provider class by attempting to
        connect and list models.

        Args:
            configs: Optional dict of provider name -> config

        Returns:
            List of discovered and available provider names
        """
        discovered = []
        configs = configs or {}

        for name, provider_class in self._provider_classes.items():
            config = configs.get(name, ProviderConfig())
            provider = provider_class(config)
            try:
                if await provider.is_available():
                    self.register_instance(name, provider)
                    discovered.append(name)
                    logger.info("Provider discovered", name=name)
            except Exception as e:
                logger.debug(
                    "Provider not available",
                    name=name,
                    error=str(e),
                )

        return discovered

    async def complete_with_fallback(
        self,
        prompt: str,
        model: Optional[str] = None,
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
    ) -> Optional[CompletionResult]:
        """
        Get a completion with automatic fallback.

        Tries the default provider first, then falls back
        through the configured fallback chain.

        Args:
            prompt: The input prompt
            model: Model ID to use
            system_prompt: Optional system-level instruction
            temperature: Sampling temperature
            max_tokens: Maximum tokens to generate

        Returns:
            CompletionResult or None if all providers fail
        """
        providers_to_try = []

        # Build ordered list of providers to try
        if self._default_provider:
            providers_to_try.append(self._default_provider)
        providers_to_try.extend(
            name for name in self._fallback_chain
            if name != self._default_provider
        )

        for provider_name in providers_to_try:
            provider = self._providers.get(provider_name)
            if not provider:
                continue

            try:
                result = await provider.complete(
                    prompt=prompt,
                    model=model,
                    system_prompt=system_prompt,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
                if result:
                    return result
            except Exception as e:
                logger.warning(
                    "Provider fallback",
                    provider=provider_name,
                    error=str(e),
                )
                continue

        logger.error("All providers failed for completion")
        return None

    def list_providers(self) -> List[Dict[str, Any]]:
        """List all registered providers with status."""
        return [
            {
                "name": name,
                "provider": provider.provider_name,
                "is_default": name == self._default_provider,
                "api_base": provider.config.api_base_url,
            }
            for name, provider in self._providers.items()
        ]

    def get_registered_classes(self) -> List[str]:
        """List all registered provider class names."""
        return list(self._provider_classes.keys())

    def to_dict(self) -> Dict[str, Any]:
        """Serialize registry state to dictionary."""
        return {
            "providers": self.list_providers(),
            "default_provider": self._default_provider,
            "fallback_chain": list(self._fallback_chain),
            "registered_classes": self.get_registered_classes(),
        }
