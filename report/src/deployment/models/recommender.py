"""
Corax Orchestrator - Model Recommender.

Hardware-aware model recommendation engine that selects optimal
models based on system capabilities, GPU availability, and use case.
"""

from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Tuple
import platform

from src.deployment.models.registry import ModelRegistry, ModelInfo, ModelCategory
from src.core.logging import get_logger

logger = get_logger(__name__)


@dataclass
class HardwareProfile:
    """
    System hardware capabilities for model recommendations.

    Attributes:
        total_ram_gb: Total system RAM in GB
        available_ram_gb: Available RAM in GB
        vram_gb: GPU VRAM in GB (0 if no GPU)
        has_gpu: Whether a compatible GPU is available
        gpu_name: GPU name if available
        gpu_vendor: GPU vendor (nvidia, amd, apple)
        cpu_cores: Number of CPU cores
        disk_free_gb: Free disk space in GB
    """
    total_ram_gb: float = 8.0
    available_ram_gb: float = 4.0
    vram_gb: float = 0.0
    has_gpu: bool = False
    gpu_name: str = ""
    gpu_vendor: str = ""
    cpu_cores: int = 4
    disk_free_gb: float = 50.0


@dataclass
class ModelRecommendation:
    """
    A recommended model with rationale.

    Attributes:
        model: The recommended model info
        score: Recommendation score (0-100)
        rationale: Why this model was recommended
        quantization: Recommended quantization
        estimated_disk_gb: Estimated disk usage
        fits_in_ram: Whether model fits in available RAM
        fits_in_vram: Whether model fits in VRAM
    """
    model: ModelInfo
    score: float
    rationale: str
    quantization: str
    estimated_disk_gb: float
    fits_in_ram: bool
    fits_in_vram: bool


class ModelRecommender:
    """
    Hardware-aware model recommendation engine.

    Analyzes system hardware and recommends optimal models
    based on available resources and desired use cases.
    """

    def __init__(self, registry: Optional[ModelRegistry] = None) -> None:
        self._registry = registry or ModelRegistry()

    async def recommend(
        self,
        hardware: HardwareProfile,
        use_cases: Optional[List[str]] = None,
        max_models: int = 5,
    ) -> List[ModelRecommendation]:
        """
        Recommend models based on hardware and use cases.

        Args:
            hardware: System hardware profile
            use_cases: Desired use cases (coding, writing, chat, etc.)
            max_models: Maximum number of recommendations

        Returns:
            List of model recommendations sorted by score
        """
        candidates = self._get_candidates(use_cases)
        scored = self._score_models(candidates, hardware)
        scored.sort(key=lambda r: r.score, reverse=True)
        return scored[:max_models]

    def _get_candidates(self, use_cases: Optional[List[str]]) -> List[ModelInfo]:
        """Get candidate models based on use cases."""
        if not use_cases:
            return self._registry.get_all()

        candidates = []
        for use_case in use_cases:
            use_case = use_case.lower()

            if use_case in ("coding", "code", "development"):
                candidates.extend(self._registry.get_coding_models())
            elif use_case in ("writing", "writing assistant", "content"):
                candidates.extend(self._registry.get_writing_models())
            elif use_case in ("chat", "conversation"):
                candidates.extend(self._registry.get_by_category(ModelCategory.CHAT))
            elif use_case in ("instruction", "agent", "orchestration"):
                candidates.extend(self._registry.get_by_category(ModelCategory.INSTRUCTION))
            elif use_case in ("embedding", "rag", "search"):
                candidates.extend(self._registry.get_embedding_models())
            elif use_case in ("image", "image generation", "art"):
                candidates.extend(self._registry.get_image_models())
            elif use_case in ("lightweight", "fallback", "low-resource"):
                candidates.extend(self._registry.get_lightweight_models())
            else:
                candidates.extend(self._registry.search(use_case))

        # Deduplicate
        seen = set()
        unique = []
        for model in candidates:
            if model.model_id not in seen:
                seen.add(model.model_id)
                unique.append(model)

        return unique

    def _score_models(
        self,
        models: List[ModelInfo],
        hardware: HardwareProfile,
    ) -> List[ModelRecommendation]:
        """Score models against hardware capabilities."""
        recommendations = []

        for model in models:
            score = 50.0  # Base score
            reasons = []

            # RAM scoring
            fits_ram = hardware.available_ram_gb >= model.min_ram_gb
            if fits_ram:
                score += 20
                if hardware.available_ram_gb >= model.min_ram_gb * 2:
                    score += 10  # Bonus for headroom
                    reasons.append("ample RAM headroom")
                else:
                    reasons.append("fits in RAM")
            else:
                score -= 30
                reasons.append(f"needs {model.min_ram_gb}GB RAM, has {hardware.available_ram_gb}GB")

            # VRAM scoring
            fits_vram = hardware.vram_gb >= model.min_vram_gb
            if model.min_vram_gb > 0:
                if hardware.has_gpu and fits_vram:
                    score += 25
                    reasons.append("GPU accelerated")
                    if hardware.vram_gb >= model.min_vram_gb * 1.5:
                        score += 10
                        reasons.append("ample VRAM")
                elif hardware.has_gpu and not fits_vram:
                    score -= 20
                    reasons.append(f"needs {model.min_vram_gb}GB VRAM, has {hardware.vram_gb}GB")
                else:
                    score -= 15
                    reasons.append("no GPU available")
            else:
                # CPU-only model
                score += 5
                reasons.append("CPU-friendly")

            # Disk space scoring
            if hardware.disk_free_gb >= model.disk_gb:
                score += 10
                if hardware.disk_free_gb >= model.disk_gb * 3:
                    score += 5
            else:
                score -= 20
                reasons.append(f"needs {model.disk_gb}GB disk, has {hardware.disk_free_gb}GB")

            # Popularity bonus
            if model.tags and "popular" in model.tags:
                score += 5

            # Context length bonus
            if model.context_length >= 32768:
                score += 5
            elif model.context_length >= 8192:
                score += 3

            # Quantization selection
            quantization = self._select_quantization(model, hardware)

            # Determine best quantization
            estimated_disk = model.disk_gb
            if quantization == "q4_k_m":
                estimated_disk = model.disk_gb * 0.6
            elif quantization == "q8_0":
                estimated_disk = model.disk_gb * 0.9

            rationale = "; ".join(reasons) if reasons else "recommended model"

            recommendations.append(ModelRecommendation(
                model=model,
                score=max(0, min(100, score)),
                rationale=rationale,
                quantization=quantization,
                estimated_disk_gb=round(estimated_disk, 1),
                fits_in_ram=fits_ram,
                fits_in_vram=fits_vram if model.min_vram_gb > 0 else True,
            ))

        return recommendations

    def _select_quantization(self, model: ModelInfo, hardware: HardwareProfile) -> str:
        """Select the best quantization for available hardware."""
        if not model.quantization:
            return "q4_k_m"

        # Prefer q4_k_m for low-RAM systems
        if hardware.available_ram_gb < 8:
            if "q4_k_m" in model.quantization:
                return "q4_k_m"
            return model.quantization[0]

        # Prefer q5_k_m for mid-range systems
        if hardware.available_ram_gb < 16:
            if "q5_k_m" in model.quantization:
                return "q5_k_m"
            if "q4_k_m" in model.quantization:
                return "q4_k_m"
            return model.quantization[0]

        # Use recommended for high-RAM systems
        if model.recommended_quantization in model.quantization:
            return model.recommended_quantization

        return model.quantization[0]

    async def detect_hardware(self) -> HardwareProfile:
        """
        Detect system hardware capabilities.

        Returns:
            HardwareProfile with detected system specs
        """
        import psutil

        # RAM detection
        ram = psutil.virtual_memory()
        total_ram_gb = round(ram.total / (1024 ** 3), 1)
        available_ram_gb = round(ram.available / (1024 ** 3), 1)

        # CPU detection
        cpu_cores = psutil.cpu_count(logical=True) or 4

        # Disk detection
        disk = psutil.disk_usage("/")
        disk_free_gb = round(disk.free / (1024 ** 3), 1)

        # GPU detection (best effort)
        vram_gb = 0.0
        has_gpu = False
        gpu_name = ""
        gpu_vendor = ""

        try:
            # Try nvidia-smi
            import subprocess
            result = subprocess.run(
                ["nvidia-smi", "--query-gpu=name,memory.total",
                 "--format=csv,noheader,nounits"],
                capture_output=True, text=True, timeout=10,
            )
            if result.returncode == 0 and result.stdout.strip():
                has_gpu = True
                gpu_vendor = "nvidia"
                parts = result.stdout.strip().split(",")
                gpu_name = parts[0].strip()
                if len(parts) > 1:
                    try:
                        vram_gb = round(float(parts[1].strip()) / 1024, 1)
                    except ValueError:
                        pass
        except Exception:
            pass

        if not has_gpu:
            try:
                # Try macOS GPU detection
                if platform.system() == "Darwin":
                    result = subprocess.run(
                        ["system_profiler", "SPDisplaysDataType"],
                        capture_output=True, text=True, timeout=10,
                    )
                    if "Metal" in result.stdout or "Apple" in result.stdout:
                        has_gpu = True
                        gpu_vendor = "apple"
                        # Apple Silicon has unified memory
                        vram_gb = total_ram_gb
            except Exception:
                pass

        return HardwareProfile(
            total_ram_gb=total_ram_gb,
            available_ram_gb=available_ram_gb,
            vram_gb=vram_gb,
            has_gpu=has_gpu,
            gpu_name=gpu_name,
            gpu_vendor=gpu_vendor,
            cpu_cores=cpu_cores,
            disk_free_gb=disk_free_gb,
        )

    def get_default_recommendations(self, hardware: HardwareProfile) -> Dict[str, List[ModelRecommendation]]:
        """
        Get default recommendations for common use cases.

        Returns:
            Dict mapping use case names to model recommendations
        """
        return {
            "coding": self._score_models(
                self._registry.get_coding_models(), hardware
            )[:3],
            "writing": self._score_models(
                self._registry.get_writing_models(), hardware
            )[:3],
            "chat": self._score_models(
                self._registry.get_by_category(ModelCategory.CHAT), hardware
            )[:2],
            "embedding": self._score_models(
                self._registry.get_embedding_models(), hardware
            )[:2],
            "lightweight": self._score_models(
                self._registry.get_lightweight_models(), hardware
            )[:2],
        }
