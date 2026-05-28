"""
Corax Orchestrator - Model Registry.

Central registry of recommended AI models organized by category,
with metadata for hardware requirements, quantization, and use cases.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Any, List, Optional
import json
import os


class ModelCategory(Enum):
    """Categories of AI models."""
    CODING = "coding"
    WRITING = "writing"
    CHAT = "chat"
    INSTRUCTION = "instruction"
    EMBEDDING = "embedding"
    IMAGE_GENERATION = "image_generation"
    IMAGE_UNDERSTANDING = "image_understanding"
    LIGHTWEIGHT = "lightweight"
    GENERAL = "general"


@dataclass
class ModelInfo:
    """
    Metadata for a single AI model.

    Attributes:
        name: Display name
        model_id: Model identifier for the runtime
        category: Model category
        provider: Runtime provider (ollama, lm_studio, huggingface)
        description: Human-readable description
        min_ram_gb: Minimum RAM required in GB
        min_vram_gb: Minimum VRAM required in GB (0 for CPU-only)
        disk_gb: Disk space required in GB
        quantization: Available quantizations
        recommended_quantization: Best quantization for most users
        context_length: Maximum context length in tokens
        use_cases: List of recommended use cases
        tags: Searchable tags
        url: Model source URL
    """
    name: str
    model_id: str
    category: ModelCategory
    provider: str  # "ollama", "lm_studio", "huggingface"
    description: str
    min_ram_gb: float = 8.0
    min_vram_gb: float = 0.0
    disk_gb: float = 4.0
    quantization: List[str] = field(default_factory=lambda: ["q4_k_m", "q5_k_m", "q8_0"])
    recommended_quantization: str = "q4_k_m"
    context_length: int = 4096
    use_cases: List[str] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)
    url: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "model_id": self.model_id,
            "category": self.category.value,
            "provider": self.provider,
            "description": self.description,
            "min_ram_gb": self.min_ram_gb,
            "min_vram_gb": self.min_vram_gb,
            "disk_gb": self.disk_gb,
            "quantization": self.quantization,
            "recommended_quantization": self.recommended_quantization,
            "context_length": self.context_length,
            "use_cases": self.use_cases,
            "tags": self.tags,
            "url": self.url,
        }


class ModelRegistry:
    """
    Central registry of recommended AI models.

    Provides curated model lists organized by category and use case,
    with hardware-aware filtering capabilities.
    """

    def __init__(self) -> None:
        self._models: Dict[str, ModelInfo] = {}
        self._load_defaults()

    def _load_defaults(self) -> None:
        """Load the default curated model list."""
        defaults = [
            # === CODING MODELS ===
            ModelInfo(
                name="CodeGemma 2B",
                model_id="codegemma:2b",
                category=ModelCategory.CODING,
                provider="ollama",
                description="Google's lightweight code generation model",
                min_ram_gb=4.0,
                min_vram_gb=0,
                disk_gb=1.5,
                quantization=["q4_k_m", "q8_0"],
                recommended_quantization="q4_k_m",
                context_length=8192,
                use_cases=["code completion", "code generation", "explain code"],
                tags=["coding", "lightweight", "google"],
            ),
            ModelInfo(
                name="CodeGemma 7B",
                model_id="codegemma:7b",
                category=ModelCategory.CODING,
                provider="ollama",
                description="Google's full code generation model",
                min_ram_gb=8.0,
                min_vram_gb=6.0,
                disk_gb=4.5,
                quantization=["q4_k_m", "q5_k_m", "q8_0"],
                recommended_quantization="q4_k_m",
                context_length=8192,
                use_cases=["code completion", "code review", "refactoring"],
                tags=["coding", "google"],
            ),
            ModelInfo(
                name="DeepSeek Coder V2",
                model_id="deepseek-coder-v2",
                category=ModelCategory.CODING,
                provider="ollama",
                description="DeepSeek's advanced code generation model",
                min_ram_gb=16.0,
                min_vram_gb=12.0,
                disk_gb=8.0,
                quantization=["q4_k_m", "q5_k_m"],
                recommended_quantization="q4_k_m",
                context_length=16384,
                use_cases=["code generation", "multi-file editing", "code analysis"],
                tags=["coding", "advanced", "deepseek"],
            ),
            ModelInfo(
                name="Qwen2.5 Coder 7B",
                model_id="qwen2.5-coder:7b",
                category=ModelCategory.CODING,
                provider="ollama",
                description="Alibaba's code-specialized model",
                min_ram_gb=8.0,
                min_vram_gb=6.0,
                disk_gb=4.5,
                quantization=["q4_k_m", "q5_k_m", "q8_0"],
                recommended_quantization="q4_k_m",
                context_length=32768,
                use_cases=["code generation", "code completion", "debugging"],
                tags=["coding", "qwen", "alibaba"],
            ),
            ModelInfo(
                name="Qwen2.5 Coder 1.5B",
                model_id="qwen2.5-coder:1.5b",
                category=ModelCategory.CODING,
                provider="ollama",
                description="Lightweight code model for low-resource systems",
                min_ram_gb=2.0,
                min_vram_gb=0,
                disk_gb=1.0,
                quantization=["q4_k_m", "q8_0"],
                recommended_quantization="q4_k_m",
                context_length=32768,
                use_cases=["code completion", "simple code gen"],
                tags=["coding", "lightweight", "qwen"],
            ),
            ModelInfo(
                name="Starcoder2 15B",
                model_id="starcoder2:15b",
                category=ModelCategory.CODING,
                provider="ollama",
                description="BigCode's large code generation model",
                min_ram_gb=16.0,
                min_vram_gb=12.0,
                disk_gb=9.0,
                quantization=["q4_k_m"],
                recommended_quantization="q4_k_m",
                context_length=16384,
                use_cases=["code generation", "code completion"],
                tags=["coding", "bigcode", "starcoder"],
            ),

            # === WRITING MODELS ===
            ModelInfo(
                name="Llama 3.2 3B",
                model_id="llama3.2:3b",
                category=ModelCategory.WRITING,
                provider="ollama",
                description="Meta's efficient general-purpose model",
                min_ram_gb=4.0,
                min_vram_gb=0,
                disk_gb=2.0,
                quantization=["q4_k_m", "q8_0"],
                recommended_quantization="q4_k_m",
                context_length=8192,
                use_cases=["writing", "chat", "summarization", "general QA"],
                tags=["writing", "general", "meta", "lightweight"],
            ),
            ModelInfo(
                name="Llama 3.1 8B",
                model_id="llama3.1:8b",
                category=ModelCategory.WRITING,
                provider="ollama",
                description="Meta's balanced general-purpose model",
                min_ram_gb=8.0,
                min_vram_gb=6.0,
                disk_gb=4.7,
                quantization=["q4_k_m", "q5_k_m", "q8_0"],
                recommended_quantization="q4_k_m",
                context_length=131072,
                use_cases=["writing", "chat", "analysis", "creative writing"],
                tags=["writing", "general", "meta", "popular"],
            ),
            ModelInfo(
                name="Mistral 7B",
                model_id="mistral:7b",
                category=ModelCategory.WRITING,
                provider="ollama",
                description="Mistral AI's efficient general model",
                min_ram_gb=8.0,
                min_vram_gb=6.0,
                disk_gb=4.1,
                quantization=["q4_k_m", "q5_k_m", "q8_0"],
                recommended_quantization="q4_k_m",
                context_length=32768,
                use_cases=["writing", "chat", "instruction following"],
                tags=["writing", "general", "mistral"],
            ),
            ModelInfo(
                name="Phi-3 Medium",
                model_id="phi3:medium",
                category=ModelCategory.WRITING,
                provider="ollama",
                description="Microsoft's capable small model",
                min_ram_gb=8.0,
                min_vram_gb=4.0,
                disk_gb=4.0,
                quantization=["q4_k_m", "q8_0"],
                recommended_quantization="q4_k_m",
                context_length=128000,
                use_cases=["writing", "reasoning", "analysis"],
                tags=["writing", "microsoft", "phi3"],
            ),

            # === CHAT MODELS ===
            ModelInfo(
                name="Llama 3.2 1B",
                model_id="llama3.2:1b",
                category=ModelCategory.CHAT,
                provider="ollama",
                description="Ultra-lightweight chat model",
                min_ram_gb=1.0,
                min_vram_gb=0,
                disk_gb=0.7,
                quantization=["q4_k_m", "q8_0"],
                recommended_quantization="q4_k_m",
                context_length=8192,
                use_cases=["simple chat", "classification", "lightweight tasks"],
                tags=["chat", "lightweight", "meta"],
            ),
            ModelInfo(
                name="Qwen2.5 7B",
                model_id="qwen2.5:7b",
                category=ModelCategory.CHAT,
                provider="ollama",
                description="Alibaba's strong general chat model",
                min_ram_gb=8.0,
                min_vram_gb=6.0,
                disk_gb=4.5,
                quantization=["q4_k_m", "q5_k_m", "q8_0"],
                recommended_quantization="q4_k_m",
                context_length=32768,
                use_cases=["chat", "instruction following", "reasoning"],
                tags=["chat", "qwen", "alibaba"],
            ),
            ModelInfo(
                name="Gemma 2 9B",
                model_id="gemma2:9b",
                category=ModelCategory.CHAT,
                provider="ollama",
                description="Google's high-quality chat model",
                min_ram_gb=8.0,
                min_vram_gb=6.0,
                disk_gb=5.5,
                quantization=["q4_k_m", "q8_0"],
                recommended_quantization="q4_k_m",
                context_length=8192,
                use_cases=["chat", "instruction following"],
                tags=["chat", "google", "gemma"],
            ),

            # === INSTRUCTION MODELS ===
            ModelInfo(
                name="Nous Hermes 2 Mixtral",
                model_id="mixtral:8x7b",
                category=ModelCategory.INSTRUCTION,
                provider="ollama",
                description="High-quality instruction following (MoE)",
                min_ram_gb=24.0,
                min_vram_gb=16.0,
                disk_gb=26.0,
                quantization=["q4_k_m", "q5_k_m"],
                recommended_quantization="q4_k_m",
                context_length=32768,
                use_cases=["complex tasks", "agent orchestration", "advanced reasoning"],
                tags=["instruction", "mixtral", "moe", "advanced"],
            ),
            ModelInfo(
                name="DeepSeek R1 7B",
                model_id="deepseek-r1:7b",
                category=ModelCategory.INSTRUCTION,
                provider="ollama",
                description="DeepSeek's reasoning-focused model",
                min_ram_gb=8.0,
                min_vram_gb=6.0,
                disk_gb=4.5,
                quantization=["q4_k_m", "q8_0"],
                recommended_quantization="q4_k_m",
                context_length=32768,
                use_cases=["reasoning", "problem solving", "analysis"],
                tags=["instruction", "reasoning", "deepseek"],
            ),

            # === EMBEDDING MODELS ===
            ModelInfo(
                name="Nomic Embed Text",
                model_id="nomic-embed-text",
                category=ModelCategory.EMBEDDING,
                provider="ollama",
                description="Text embedding model for RAG",
                min_ram_gb=2.0,
                min_vram_gb=0,
                disk_gb=0.3,
                quantization=["f16"],
                recommended_quantization="f16",
                context_length=8192,
                use_cases=["RAG", "semantic search", "document embedding"],
                tags=["embedding", "rag", "nomic"],
            ),
            ModelInfo(
                name="MXBai Embed Large",
                model_id="mxbai-embed-large",
                category=ModelCategory.EMBEDDING,
                provider="ollama",
                description="High-quality embedding model",
                min_ram_gb=4.0,
                min_vram_gb=0,
                disk_gb=0.7,
                quantization=["f16"],
                recommended_quantization="f16",
                context_length=512,
                use_cases=["RAG", "semantic search", "document retrieval"],
                tags=["embedding", "rag"],
            ),

            # === IMAGE GENERATION MODELS ===
            ModelInfo(
                name="Stable Diffusion XL",
                model_id="sd_xl_base",
                category=ModelCategory.IMAGE_GENERATION,
                provider="huggingface",
                description="High-quality image generation",
                min_ram_gb=16.0,
                min_vram_gb=8.0,
                disk_gb=7.0,
                quantization=["fp16", "fp32"],
                recommended_quantization="fp16",
                context_length=0,
                use_cases=["image generation", "art", "design"],
                tags=["image", "stable-diffusion", "sdxl"],
            ),
            ModelInfo(
                name="FLUX.1 Schnell",
                model_id="black-forest-labs/FLUX.1-schnell",
                category=ModelCategory.IMAGE_GENERATION,
                provider="huggingface",
                description="Fast, high-quality image generation",
                min_ram_gb=16.0,
                min_vram_gb=8.0,
                disk_gb=12.0,
                quantization=["fp16"],
                recommended_quantization="fp16",
                context_length=0,
                use_cases=["image generation", "fast inference"],
                tags=["image", "flux", "black-forest-labs"],
            ),

            # === LIGHTWEIGHT FALLBACK MODELS ===
            ModelInfo(
                name="TinyLlama 1.1B",
                model_id="tinylama:1.1b",
                category=ModelCategory.LIGHTWEIGHT,
                provider="ollama",
                description="Smallest viable chat model",
                min_ram_gb=1.0,
                min_vram_gb=0,
                disk_gb=0.7,
                quantization=["q4_k_m", "q8_0"],
                recommended_quantization="q4_k_m",
                context_length=2048,
                use_cases=["fallback", "simple tasks", "testing"],
                tags=["lightweight", "fallback", "tiny"],
            ),
            ModelInfo(
                name="Llama 3.2 3B",
                model_id="llama3.2:3b",
                category=ModelCategory.LIGHTWEIGHT,
                provider="ollama",
                description="Good balance of size and capability",
                min_ram_gb=4.0,
                min_vram_gb=0,
                disk_gb=2.0,
                quantization=["q4_k_m", "q8_0"],
                recommended_quantization="q4_k_m",
                context_length=8192,
                use_cases=["fallback", "general tasks", "CPU inference"],
                tags=["lightweight", "fallback", "meta"],
            ),
        ]

        for model in defaults:
            self._models[model.model_id] = model

    def get_all(self) -> List[ModelInfo]:
        """Get all registered models."""
        return list(self._models.values())

    def get_by_category(self, category: ModelCategory) -> List[ModelInfo]:
        """Get models by category."""
        return [m for m in self._models.values() if m.category == category]

    def get_by_provider(self, provider: str) -> List[ModelInfo]:
        """Get models by provider."""
        return [m for m in self._models.values() if m.provider == provider]

    def get_by_id(self, model_id: str) -> Optional[ModelInfo]:
        """Get a model by its ID."""
        return self._models.get(model_id)

    def search(self, query: str) -> List[ModelInfo]:
        """Search models by name, description, or tags."""
        query = query.lower()
        results = []
        for model in self._models.values():
            if (query in model.name.lower()
                    or query in model.description.lower()
                    or any(query in tag.lower() for tag in model.tags)
                    or query in model.model_id.lower()):
                results.append(model)
        return results

    def get_coding_models(self) -> List[ModelInfo]:
        """Get recommended coding models."""
        return self.get_by_category(ModelCategory.CODING)

    def get_writing_models(self) -> List[ModelInfo]:
        """Get recommended writing models."""
        return self.get_by_category(ModelCategory.WRITING)

    def get_lightweight_models(self) -> List[ModelInfo]:
        """Get lightweight fallback models."""
        return self.get_by_category(ModelCategory.LIGHTWEIGHT)

    def get_embedding_models(self) -> List[ModelInfo]:
        """Get embedding models for RAG."""
        return self.get_by_category(ModelCategory.EMBEDDING)

    def get_image_models(self) -> List[ModelInfo]:
        """Get image generation models."""
        return self.get_by_category(ModelCategory.IMAGE_GENERATION)

    def register_model(self, model: ModelInfo) -> None:
        """Register a custom model."""
        self._models[model.model_id] = model

    def to_dict(self) -> Dict[str, Any]:
        """Export registry as dictionary."""
        return {
            "models": [m.to_dict() for m in self._models.values()],
            "count": len(self._models),
        }

    def save(self, path: str) -> None:
        """Save registry to JSON file."""
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            json.dump(self.to_dict(), f, indent=2)

    @classmethod
    def load(cls, path: str) -> "ModelRegistry":
        """Load registry from JSON file."""
        registry = cls()
        if os.path.exists(path):
            with open(path, "r") as f:
                data = json.load(f)
            for model_data in data.get("models", []):
                model = ModelInfo(
                    name=model_data["name"],
                    model_id=model_data["model_id"],
                    category=ModelCategory(model_data["category"]),
                    provider=model_data["provider"],
                    description=model_data["description"],
                    min_ram_gb=model_data.get("min_ram_gb", 8.0),
                    min_vram_gb=model_data.get("min_vram_gb", 0.0),
                    disk_gb=model_data.get("disk_gb", 4.0),
                    quantization=model_data.get("quantization", ["q4_k_m"]),
                    recommended_quantization=model_data.get("recommended_quantization", "q4_k_m"),
                    context_length=model_data.get("context_length", 4096),
                    use_cases=model_data.get("use_cases", []),
                    tags=model_data.get("tags", []),
                    url=model_data.get("url", ""),
                )
                registry.register_model(model)
        return registry
