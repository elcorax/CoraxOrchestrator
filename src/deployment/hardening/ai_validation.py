"""
Corax Orchestrator — AI Stack Validation Module (Priority 3).

Provides AI orchestration validation:
- Ollama accessibility checks
- Model availability and integrity
- Inference sanity testing
- API connectivity validation
- Disk-space requirements for AI models
- GPU inference capability detection
- CPU fallback behavior validation
- AI readiness scoring
- Model corruption detection
- Interrupted pull recovery
- AI environment diagnostics

Requirements:
AI failures must NEVER crash deployment.
"""

from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
import os
import platform
import socket
import subprocess
import time
import urllib.request
import urllib.error

from src.core.logging import get_logger

logger = get_logger(__name__)


# ------------------------------------------------------------------
# Data Types
# ------------------------------------------------------------------

@dataclass
class AIValidationResult:
    """Result of an AI validation check."""
    check_name: str
    passed: bool = True
    details: Dict[str, Any] = field(default_factory=dict)
    errors: List[str] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)
    duration_ms: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "check_name": self.check_name,
            "passed": self.passed,
            "details": self.details,
            "errors": self.errors,
            "recommendations": self.recommendations,
            "duration_ms": round(self.duration_ms, 2),
        }


@dataclass
class AIReadinessScore:
    """Overall AI stack readiness assessment."""
    score: float  # 0.0 to 1.0
    grade: str  # A, B, C, D, F
    checks: List[AIValidationResult]
    summary: Dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "score": round(self.score, 3),
            "grade": self.grade,
            "checks": [c.to_dict() for c in self.checks],
            "summary": self.summary,
            "timestamp": self.timestamp,
        }


# ------------------------------------------------------------------
# AI Validation Engine
# ------------------------------------------------------------------

class AIValidationEngine:
    """
    Validates AI stack readiness for deployment.

    All checks are safe - they never modify system state and
    never crash the deployment on failure.
    """

    # Default models to check
    DEFAULT_MODELS = [
        "llama3.2",
        "llama3.1:8b",
        "mistral",
        "codellama",
    ]

    # Ollama API endpoints
    OLLAMA_TAGS_URL = "http://localhost:11434/api/tags"
    OLLAMA_PULL_URL = "http://localhost:11434/api/pull"
    OLLAMA_GENERATE_URL = "http://localhost:11434/api/generate"

    # Minimum free disk space for AI models (GB)
    MIN_DISK_SPACE_GB = 10.0

    def __init__(self):
        self._check_results: List[AIValidationResult] = []

    # ------------------------------------------------------------------
    # Ollama Accessibility
    # ------------------------------------------------------------------

    def check_ollama_accessibility(self) -> AIValidationResult:
        """
        Check if Ollama is installed and accessible.
        Never crashes - returns result with errors on failure.
        """
        start = time.time()
        result = AIValidationResult(check_name="ollama_accessibility")

        try:
            # Check if ollama binary exists
            ollama_path = self._find_ollama()
            if not ollama_path:
                result.passed = False
                result.errors.append("Ollama not found in PATH")
                result.recommendations.append(
                    "Install Ollama from https://ollama.ai"
                )
                result.duration_ms = (time.time() - start) * 1000
                return result

            result.details["binary_path"] = ollama_path

            # Check version
            try:
                proc = subprocess.run(
                    [ollama_path, "--version"],
                    capture_output=True, text=True, timeout=15,
                )
                if proc.returncode == 0:
                    result.details["version"] = proc.stdout.strip()
                else:
                    result.details["version_error"] = proc.stderr.strip()
            except (subprocess.TimeoutExpired, OSError) as e:
                result.details["version_error"] = str(e)

            # Check if ollama server is running
            server_running = self._check_ollama_server()
            result.details["server_running"] = server_running

            if server_running:
                result.passed = True
            else:
                result.passed = False
                result.errors.append("Ollama server is not running")
                result.recommendations.append(
                    "Start Ollama server: 'ollama serve'"
                )

        except Exception as e:
            result.passed = False
            result.errors.append(f"Accessibility check failed: {e}")

        result.duration_ms = (time.time() - start) * 1000
        return result

    def _find_ollama(self) -> Optional[str]:
        """Find ollama binary in PATH."""
        # Common locations
        candidates = ["ollama"]
        if platform.system() == "Windows":
            candidates.extend([
                os.path.expandvars(r"%LOCALAPPDATA%\Ollama\ollama.exe"),
                os.path.expandvars(r"%PROGRAMFILES%\Ollama\ollama.exe"),
                os.path.expandvars(r"%PROGRAMFILES(X86)%\Ollama\ollama.exe"),
            ])

        for cmd in candidates:
            try:
                proc = subprocess.run(
                    [cmd, "--version"],
                    capture_output=True, text=True, timeout=5,
                )
                if proc.returncode == 0:
                    return cmd
            except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
                continue

        return None

    def _check_ollama_server(self) -> bool:
        """Check if Ollama server is responding."""
        try:
            req = urllib.request.Request(
                self.OLLAMA_TAGS_URL, method="GET"
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                return resp.status < 500
        except Exception:
            return False

    # ------------------------------------------------------------------
    # Model Availability
    # ------------------------------------------------------------------

    def check_model_availability(
        self, models: Optional[List[str]] = None
    ) -> AIValidationResult:
        """
        Check which AI models are available locally.

        Args:
            models: List of model names to check, or None for defaults
        """
        start = time.time()
        result = AIValidationResult(check_name="model_availability")
        models_to_check = models or self.DEFAULT_MODELS

        try:
            # Get installed models from Ollama
            installed_models = self._get_installed_models()
            result.details["installed_models"] = installed_models

            # Check each requested model
            available: List[str] = []
            missing: List[str] = []
            for model in models_to_check:
                if any(model in m for m in installed_models):
                    available.append(model)
                else:
                    missing.append(model)

            result.details["available"] = available
            result.details["missing"] = missing
            result.details["requested"] = models_to_check

            if missing:
                result.passed = False
                result.errors.append(
                    f"Models not found: {', '.join(missing)}"
                )
                for m in missing:
                    result.recommendations.append(
                        f"Pull model: ollama pull {m}"
                    )
            else:
                result.passed = True

        except Exception as e:
            result.passed = False
            result.errors.append(f"Model check failed: {e}")
            result.recommendations.append(
                "Ensure Ollama server is running and try again"
            )

        result.duration_ms = (time.time() - start) * 1000
        return result

    def _get_installed_models(self) -> List[str]:
        """Get list of installed Ollama models."""
        try:
            req = urllib.request.Request(self.OLLAMA_TAGS_URL, method="GET")
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode())
                return [
                    m.get("name", "")
                    for m in data.get("models", [])
                ]
        except Exception:
            return []

    # ------------------------------------------------------------------
    # Inference Sanity
    # ------------------------------------------------------------------

    def check_inference_sanity(
        self, model: str = "llama3.2", timeout: int = 30
    ) -> AIValidationResult:
        """
        Test that a model can perform basic inference.

        Sends a simple prompt and verifies a non-empty response.
        Never crashes - returns result with errors on failure.

        Args:
            model: Model to test
            timeout: Maximum wait time for response
        """
        start = time.time()
        result = AIValidationResult(check_name="inference_sanity")
        result.details["model"] = model

        try:
            prompt = "Reply with exactly one word: hello"
            payload = json.dumps({
                "model": model,
                "prompt": prompt,
                "stream": False,
                "options": {"num_predict": 10},
            }).encode()

            req = urllib.request.Request(
                self.OLLAMA_GENERATE_URL,
                data=payload,
                method="POST",
                headers={"Content-Type": "application/json"},
            )

            with urllib.request.urlopen(req, timeout=timeout) as resp:
                response = json.loads(resp.read().decode())
                response_text = response.get("response", "").strip()

                result.details["response_received"] = bool(response_text)
                result.details["response_length"] = len(response_text)
                result.details["response_preview"] = response_text[:100]

                if response_text:
                    result.passed = True
                else:
                    result.passed = False
                    result.errors.append("Empty response from model")
                    result.recommendations.append(
                        f"Check model '{model}' integrity: ollama pull {model}"
                    )

        except urllib.error.HTTPError as e:
            result.passed = False
            result.errors.append(f"HTTP {e.code}: {e.reason}")
            if e.code == 404:
                result.recommendations.append(
                    f"Model '{model}' not found. Pull it: ollama pull {model}"
                )
        except urllib.error.URLError as e:
            result.passed = False
            result.errors.append(f"Connection failed: {e.reason}")
            result.recommendations.append("Ensure Ollama server is running")
        except socket.timeout:
            result.passed = False
            result.errors.append(f"Inference timed out after {timeout}s")
            result.recommendations.append(
                "Model may be too large. Try a smaller model."
            )
        except Exception as e:
            result.passed = False
            result.errors.append(f"Inference check failed: {e}")

        result.duration_ms = (time.time() - start) * 1000
        return result

    # ------------------------------------------------------------------
    # API Connectivity
    # ------------------------------------------------------------------

    def check_api_connectivity(self) -> AIValidationResult:
        """
        Check connectivity to AI-related APIs.

        Tests:
        - Ollama API (localhost:11434)
        - Hugging Face (huggingface.co)
        - GitHub (github.com)
        """
        start = time.time()
        result = AIValidationResult(check_name="api_connectivity")
        endpoints = {
            "ollama_api": ("http://localhost:11434/api/tags", 5),
            "huggingface": ("https://huggingface.co", 10),
            "github": ("https://github.com", 10),
            "pypi": ("https://pypi.org", 10),
        }

        connectivity: Dict[str, bool] = {}
        errors: List[str] = []

        for name, (url, timeout) in endpoints.items():
            try:
                req = urllib.request.Request(url, method="HEAD")
                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    connectivity[name] = resp.status < 500
            except Exception as e:
                connectivity[name] = False
                errors.append(f"{name}: {e}")

        result.details["connectivity"] = connectivity
        result.details["reachable"] = sum(1 for v in connectivity.values() if v)
        result.details["total"] = len(connectivity)

        if errors:
            result.passed = False
            result.errors = errors[:3]
            result.recommendations.append(
                "Check network connectivity and firewall settings"
            )
        else:
            result.passed = True

        result.duration_ms = (time.time() - start) * 1000
        return result

    # ------------------------------------------------------------------
    # Disk Space Requirements
    # ------------------------------------------------------------------

    def check_disk_space_for_ai(self) -> AIValidationResult:
        """
        Check if sufficient disk space is available for AI models.

        AI models typically require 5-20 GB per model. We check
        that at least MIN_DISK_SPACE_GB is available.
        """
        start = time.time()
        result = AIValidationResult(check_name="ai_disk_space")

        try:
            import shutil
            usage = shutil.disk_usage(os.getcwd())
            free_gb = usage.free / (1024 ** 3)

            result.details["free_gb"] = round(free_gb, 2)
            result.details["minimum_required_gb"] = self.MIN_DISK_SPACE_GB
            result.details["total_gb"] = round(usage.total / (1024 ** 3), 2)

            if free_gb >= self.MIN_DISK_SPACE_GB:
                result.passed = True
            else:
                result.passed = False
                result.errors.append(
                    f"Insufficient disk space: {free_gb:.1f} GB free, "
                    f"need {self.MIN_DISK_SPACE_GB} GB"
                )
                result.recommendations.append(
                    f"Free up at least {self.MIN_DISK_SPACE_GB} GB for AI models"
                )

        except ImportError:
            result.passed = True
            result.details["note"] = "Could not check disk space (shutil unavailable)"
        except Exception as e:
            result.passed = False
            result.errors.append(f"Disk space check failed: {e}")

        result.duration_ms = (time.time() - start) * 1000
        return result

    # ------------------------------------------------------------------
    # GPU Inference Capability
    # ------------------------------------------------------------------

    def check_gpu_capability(self) -> AIValidationResult:
        """
        Check if GPU inference is available.

        Checks for:
        - NVIDIA GPU via nvidia-smi
        - CUDA availability
        - DirectML (Windows)
        - Vulkan support
        """
        start = time.time()
        result = AIValidationResult(check_name="gpu_capability")

        try:
            gpu_info: Dict[str, Any] = {
                "nvidia_gpu": False,
                "nvidia_driver": None,
                "cuda_available": False,
                "directml_available": False,
                "gpu_count": 0,
                "gpu_details": [],
            }

            # Check NVIDIA GPU
            try:
                proc = subprocess.run(
                    ["nvidia-smi", "--query-gpu=name,driver_version,memory.total",
                     "--format=csv,noheader"],
                    capture_output=True, text=True, timeout=15,
                )
                if proc.returncode == 0:
                    gpu_info["nvidia_gpu"] = True
                    lines = proc.stdout.strip().splitlines()
                    gpu_info["gpu_count"] = len(lines)
                    for line in lines:
                        parts = [p.strip() for p in line.split(",")]
                        gpu_info["gpu_details"].append({
                            "name": parts[0] if len(parts) > 0 else "unknown",
                            "driver": parts[1] if len(parts) > 1 else "unknown",
                            "memory": parts[2] if len(parts) > 2 else "unknown",
                        })
                    gpu_info["nvidia_driver"] = (
                        gpu_info["gpu_details"][0]["driver"]
                        if gpu_info["gpu_details"] else None
                    )

                    # Check CUDA
                    try:
                        proc2 = subprocess.run(
                            ["nvcc", "--version"],
                            capture_output=True, text=True, timeout=10,
                        )
                        if proc2.returncode == 0:
                            gpu_info["cuda_available"] = True
                            gpu_info["cuda_version"] = proc2.stdout.strip()
                    except (FileNotFoundError, subprocess.TimeoutExpired):
                        pass

            except FileNotFoundError:
                # No nvidia-smi (no NVIDIA driver or not in PATH)
                pass

            # Check DirectML (Windows)
            if platform.system() == "Windows":
                try:
                    import torch
                    gpu_info["directml_available"] = (
                        hasattr(torch, "dml") or
                        hasattr(torch.backends, "mps")
                    )
                except ImportError:
                    pass

            result.details = gpu_info

            if gpu_info["nvidia_gpu"] or gpu_info["directml_available"]:
                result.passed = True
            else:
                result.passed = True  # Not a failure - CPU fallback is valid
                result.errors.append("No GPU detected - will use CPU fallback")
                result.recommendations.append(
                    "For better performance, install NVIDIA CUDA or DirectML"
                )

        except Exception as e:
            result.passed = True  # Never fail on GPU check - CPU fallback OK
            result.errors.append(f"GPU check error (non-fatal): {e}")
            result.details = {"note": "CPU fallback will be used"}

        result.duration_ms = (time.time() - start) * 1000
        return result

    # ------------------------------------------------------------------
    # Model Corruption Check
    # ------------------------------------------------------------------

    def check_model_integrity(
        self, model: str = "llama3.2"
    ) -> AIValidationResult:
        """
        Check if an AI model is corrupted by testing inference.

        A corrupted model will typically:
        - Return empty/garbled responses
        - Crash the inference process
        - Take unusually long to respond
        """
        start = time.time()
        result = AIValidationResult(check_name="model_integrity")
        result.details["model"] = model

        try:
            # Quick inference test
            prompt = "Reply with OK if you can read this."
            payload = json.dumps({
                "model": model,
                "prompt": prompt,
                "stream": False,
                "options": {"num_predict": 5},
            }).encode()

            req = urllib.request.Request(
                self.OLLAMA_GENERATE_URL,
                data=payload,
                method="POST",
                headers={"Content-Type": "application/json"},
            )

            inference_start = time.time()
            with urllib.request.urlopen(req, timeout=30) as resp:
                response = json.loads(resp.read().decode())
                inference_time = (time.time() - inference_start) * 1000

                response_text = response.get("response", "").strip()
                eval_count = response.get("eval_count", 0)

                result.details["response_length"] = len(response_text)
                result.details["eval_count"] = eval_count
                result.details["inference_time_ms"] = round(inference_time, 1)

                # Heuristic: model is corrupted if response is empty
                # or contains only whitespace/special chars
                if not response_text:
                    result.passed = False
                    result.errors.append(
                        f"Model '{model}' returned empty response"
                    )
                    result.recommendations.append(
                        f"Re-pull model: ollama pull {model}"
                    )
                elif len(response_text) < 3:
                    result.passed = False
                    result.errors.append(
                        f"Model '{model}' returned suspiciously short response"
                    )
                    result.recommendations.append(
                        f"Verify model integrity: ollama pull {model}"
                    )
                else:
                    result.passed = True
                    result.details["integrity"] = "ok"

        except urllib.error.HTTPError as e:
            if e.code == 500:
                result.passed = False
                result.errors.append(
                    f"Model '{model}' caused internal server error (possible corruption)"
                )
                result.recommendations.append(
                    f"Re-pull model: ollama pull {model}"
                )
            else:
                result.passed = False
                result.errors.append(f"HTTP {e.code}: {e.reason}")
        except Exception as e:
            result.passed = False
            result.errors.append(f"Integrity check failed: {e}")

        result.duration_ms = (time.time() - start) * 1000
        return result

    # ------------------------------------------------------------------
    # Pull Recovery (Non-destructive check)
    # ------------------------------------------------------------------

    def check_pull_recovery(
        self, model: str = "llama3.2"
    ) -> AIValidationResult:
        """
        Check if an interrupted pull can be resumed.

        This is a read-only check - it inspects the Ollama manifest
        directory to detect partial downloads without modifying anything.
        """
        start = time.time()
        result = AIValidationResult(check_name="pull_recovery")

        try:
            # Ollama stores model manifests in specific locations
            manifest_paths = []
            if platform.system() == "Windows":
                base = os.path.expandvars(r"%LOCALAPPDATA%\Ollama")
                manifest_paths = [
                    os.path.join(base, "models", "manifests"),
                    os.path.join(base, "models", "blobs"),
                ]
            elif platform.system() == "Linux":
                manifest_paths = [
                    os.path.expanduser("~/.ollama/models/manifests"),
                    os.path.expanduser("~/.ollama/models/blobs"),
                ]
            elif platform.system() == "Darwin":
                manifest_paths = [
                    os.path.expanduser("~/.ollama/models/manifests"),
                    os.path.expanduser("~/.ollama/models/blobs"),
                ]

            result.details["checked_paths"] = manifest_paths

            # Check for partial downloads (blobs without manifests)
            partial_downloads = []
            for path in manifest_paths:
                if os.path.isdir(path):
                    files = os.listdir(path)
                    # Look for temp/partial files
                    partial = [
                        f for f in files
                        if f.endswith(".partial")
                        or f.startswith(".")
                        or f.endswith(".tmp")
                    ]
                    partial_downloads.extend(partial)

            result.details["partial_downloads_found"] = len(partial_downloads)
            result.details["partial_files"] = partial_downloads[:10]

            if partial_downloads:
                result.passed = False
                result.errors.append(
                    f"Found {len(partial_downloads)} partial downloads"
                )
                result.recommendations.append(
                    f"Retry pull: ollama pull {model}"
                )
            else:
                result.passed = True

        except Exception as e:
            result.passed = True  # Don't fail on filesystem check
            result.details["note"] = f"Could not check pull state: {e}"

        result.duration_ms = (time.time() - start) * 1000
        return result

    # ------------------------------------------------------------------
    # AI Environment Diagnostics
    # ------------------------------------------------------------------

    def generate_ai_diagnostics(self) -> Dict[str, Any]:
        """
        Generate comprehensive AI environment diagnostics.

        Runs all checks and produces a structured diagnostic report.
        """
        diagnostics = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "platform": platform.platform(),
            "python_version": platform.python_version(),
            "checks": {},
        }

        # Ollama accessibility
        acc = self.check_ollama_accessibility()
        diagnostics["checks"]["ollama_accessibility"] = acc.to_dict()

        # If Ollama is accessible, run more checks
        if acc.passed:
            diagnostics["checks"]["model_availability"] = (
                self.check_model_availability().to_dict()
            )
            diagnostics["checks"]["inference_sanity"] = (
                self.check_inference_sanity().to_dict()
            )
            diagnostics["checks"]["model_integrity"] = (
                self.check_model_integrity().to_dict()
            )
            diagnostics["checks"]["pull_recovery"] = (
                self.check_pull_recovery().to_dict()
            )

        # General checks
        diagnostics["checks"]["api_connectivity"] = (
            self.check_api_connectivity().to_dict()
        )
        diagnostics["checks"]["ai_disk_space"] = (
            self.check_disk_space_for_ai().to_dict()
        )
        diagnostics["checks"]["gpu_capability"] = (
            self.check_gpu_capability().to_dict()
        )

        # Summary
        all_passed = all(
            c.get("passed", False)
            for c in diagnostics["checks"].values()
        )
        diagnostics["all_checks_passed"] = all_passed
        diagnostics["total_checks"] = len(diagnostics["checks"])

        return diagnostics

    # ------------------------------------------------------------------
    # AI Readiness Score
    # ------------------------------------------------------------------

    def calculate_readiness_score(
        self, run_checks: bool = True
    ) -> AIReadinessScore:
        """
        Calculate overall AI readiness score.

        Args:
            run_checks: If True, runs checks now. If False, uses cached.

        Returns:
            AIReadinessScore with score, grade, and check results
        """
        checks: List[AIValidationResult] = []

        if run_checks:
            checks.append(self.check_ollama_accessibility())
            checks.append(self.check_model_availability())
            checks.append(self.check_api_connectivity())
            checks.append(self.check_disk_space_for_ai())
            checks.append(self.check_gpu_capability())

        # Calculate weighted score
        if not checks:
            return AIReadinessScore(
                score=0.0,
                grade="F",
                checks=[],
                summary={"error": "No checks were run"},
            )

        # Weight: critical checks weigh more
        weights = {
            "ollama_accessibility": 0.30,
            "model_availability": 0.25,
            "api_connectivity": 0.15,
            "ai_disk_space": 0.15,
            "gpu_capability": 0.15,
        }

        weighted_score = 0.0
        total_weight = 0.0
        passed_count = 0
        failed_count = 0

        for check in checks:
            weight = weights.get(check.check_name, 0.1)
            if check.passed:
                weighted_score += weight
                passed_count += 1
            else:
                failed_count += 1
            total_weight += weight

        final_score = weighted_score / total_weight if total_weight > 0 else 0.0
        final_score = max(0.0, min(1.0, final_score))

        # Grade
        if final_score >= 0.9:
            grade = "A"
        elif final_score >= 0.75:
            grade = "B"
        elif final_score >= 0.5:
            grade = "C"
        elif final_score >= 0.25:
            grade = "D"
        else:
            grade = "F"

        return AIReadinessScore(
            score=final_score,
            grade=grade,
            checks=checks,
            summary={
                "passed": passed_count,
                "failed": failed_count,
                "total": len(checks),
                "all_passed": passed_count == len(checks),
            },
        )
