"""
Corax Orchestrator - Model Manager Module.

Manages local AI models including downloading, listing, removing,
and tracking model metadata across different providers.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Dict, Any, List, Optional

from src.core.logging import get_logger
from src.core.exceptions import ModelError
from src.platform.factory import PlatformFactory

logger = get_logger(__name__)


class ModelProvider(Enum):
    """Supported model providers."""
    OLLAMA = "ollama"
    LM_STUDIO = "lm_studio"
    HUGGINGFACE = "huggingface"
    LOCAL = "local"


@dataclass
class ModelInfo:
    """Information about an AI model."""
    name: str
    provider: ModelProvider
    path: Optional[Path] = None
    size_bytes: int = 0
    quantization: Optional[str] = None
    family: Optional[str] = None
    description: Optional[str] = None
    downloaded: bool = False
    download_progress: float = 0.0
    tags: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "provider": self.provider.value,
            "path": str(self.path) if self.path else None,
            "size_bytes": self.size_bytes,
            "size_gb": round(self.size_bytes / (1024**3), 2),
            "quantization": self.quantization,
            "family": self.family,
            "description": self.description,
            "downloaded": self.downloaded,
            "download_progress": self.download_progress,
            "tags": self.tags,
        }


@dataclass
class ModelDownloadConfig:
    """Configuration for model downloads."""
    model_name: str
    provider: ModelProvider
    quantization: str = "Q4_K_M"
    destination: Optional[Path] = None
    hf_token: Optional[str] = None
    use_mirror: bool = False


class ModelManager:
    """
    Manages local AI models across different providers.

    Supports downloading models from Ollama, HuggingFace, and
    managing locally stored models. Tracks model metadata and
    provides progress reporting for downloads.
    """

    def __init__(self, models_dir: Optional[Path] = None) -> None:
        self.models_dir = models_dir or Path("data/models")
        self.models_dir.mkdir(parents=True, exist_ok=True)
        self._models: Dict[str, ModelInfo] = {}
        self._platform = PlatformFactory.create()

    async def list_models(self, provider: Optional[ModelProvider] = None) -> List[ModelInfo]:
        """
        List all managed models, optionally filtered by provider.

        Args:
            provider: Optional provider filter

        Returns:
            List of ModelInfo objects
        """
        if provider:
            return [m for m in self._models.values() if m.provider == provider]
        return list(self._models.values())

    async def list_ollama_models(self) -> List[ModelInfo]:
        """
        List models available in the local Ollama installation.

        Returns:
            List of ModelInfo from Ollama
        """
        models = []
        try:
            import subprocess
            result = subprocess.run(
                ["ollama", "list"],
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode == 0:
                lines = result.stdout.strip().split("\n")[1:]  # Skip header
                for line in lines:
                    if line.strip():
                        parts = line.split()
                        if len(parts) >= 3:
                            name = parts[0]
                            size_str = parts[2]
                            models.append(ModelInfo(
                                name=name,
                                provider=ModelProvider.OLLAMA,
                                size_bytes=self._parse_size(size_str),
                                downloaded=True,
                            ))
        except (FileNotFoundError, subprocess.TimeoutExpired) as e:
            logger.warning("Failed to list Ollama models", error=str(e))

        return models

    async def pull_ollama_model(
        self, model_name: str, stream: bool = True
    ) -> ModelInfo:
        """
        Pull/download a model from Ollama.

        Args:
            model_name: Name of the Ollama model (e.g., "llama3.2:3b")
            stream: Whether to stream download progress

        Returns:
            ModelInfo for the downloaded model
        """
        logger.info("Pulling Ollama model", model=model_name)

        try:
            import subprocess
            result = subprocess.run(
                ["ollama", "pull", model_name],
                capture_output=True, text=True, timeout=600,
            )
            if result.returncode != 0:
                raise ModelError(
                    message=f"Failed to pull model: {model_name}",
                    model_name=model_name,
                    provider="ollama",
                    details={"output": result.stderr},
                )

            model_info = ModelInfo(
                name=model_name,
                provider=ModelProvider.OLLAMA,
                downloaded=True,
                download_progress=100.0,
            )
            self._models[model_name] = model_info
            logger.info("Model pulled successfully", model=model_name)
            return model_info

        except FileNotFoundError:
            raise ModelError(
                message="Ollama is not installed",
                model_name=model_name,
                provider="ollama",
            )

    async def remove_model(self, model_name: str, provider: ModelProvider) -> bool:
        """
        Remove a model from the local system.

        Args:
            model_name: Name of the model to remove
            provider: Provider of the model

        Returns:
            True if removed successfully
        """
        logger.info("Removing model", model=model_name, provider=provider.value)

        if provider == ModelProvider.OLLAMA:
            try:
                import subprocess
                result = subprocess.run(
                    ["ollama", "rm", model_name],
                    capture_output=True, text=True, timeout=30,
                )
                if result.returncode == 0:
                    self._models.pop(model_name, None)
                    return True
                else:
                    raise ModelError(
                        message=f"Failed to remove model: {result.stderr}",
                        model_name=model_name,
                        provider="ollama",
                    )
            except FileNotFoundError:
                raise ModelError(
                    message="Ollama is not installed",
                    model_name=model_name,
                    provider="ollama",
                )

        elif provider == ModelProvider.LOCAL:
            model_path = self.models_dir / model_name
            if model_path.exists():
                import shutil
                shutil.rmtree(model_path)
                self._models.pop(model_name, None)
                return True

        return False

    async def get_model_info(self, model_name: str) -> Optional[ModelInfo]:
        """
        Get detailed information about a specific model.

        Args:
            model_name: Name of the model

        Returns:
            ModelInfo if found, None otherwise
        """
        return self._models.get(model_name)

    def _parse_size(self, size_str: str) -> int:
        """Parse a size string (e.g., '3.5 GB') to bytes."""
        try:
            size_str = size_str.upper().replace(",", "")
            if "GB" in size_str:
                return int(float(size_str.replace("GB", "").strip()) * 1024**3)
            elif "MB" in size_str:
                return int(float(size_str.replace("MB", "").strip()) * 1024**2)
            elif "KB" in size_str:
                return int(float(size_str.replace("KB", "").strip()) * 1024)
            else:
                return int(float(size_str.strip()))
        except (ValueError, AttributeError):
            return 0

    def get_storage_usage(self) -> Dict[str, Any]:
        """Get storage usage statistics for models."""
        total_size = sum(m.size_bytes for m in self._models.values())
        return {
            "total_models": len(self._models),
            "total_size_bytes": total_size,
            "total_size_gb": round(total_size / (1024**3), 2),
            "models_dir": str(self.models_dir),
        }
