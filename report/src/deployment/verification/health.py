"""
Corax Orchestrator - Health Checker.

Comprehensive health verification for AI infrastructure.
Checks tool availability, API endpoints, service status,
and system resource adequacy.
"""

from typing import Dict, Any, List, Optional, Callable, Awaitable
import asyncio
import time
import platform

from src.deployment.verification.base import (
    VerificationResult,
    VerificationStatus,
)
from src.deployment.installers.base import AIInstallerBase
from src.core.logging import get_logger

logger = get_logger(__name__)


class HealthChecker:
    """
    Comprehensive health verification for AI infrastructure.

    Runs a series of checks against installed tools and system
    resources to determine overall deployment health.
    """

    def __init__(self) -> None:
        self._checks: List[Callable[[], Awaitable[VerificationResult]]] = []

    def add_check(self, check: Callable[[], Awaitable[VerificationResult]]) -> None:
        """Add a custom health check."""
        self._checks.append(check)

    async def run_all(self) -> List[VerificationResult]:
        """Run all registered health checks."""
        results = []
        for check in self._checks:
            try:
                start = time.time()
                result = await check()
                result.duration_ms = round((time.time() - start) * 1000, 2)
                results.append(result)
            except Exception as e:
                results.append(VerificationResult(
                    check_name=check.__name__,
                    status=VerificationStatus.UNKNOWN,
                    message=f"Check failed with error: {str(e)}",
                ))
        return results

    async def check_tool(self, installer: AIInstallerBase) -> VerificationResult:
        """Check health of a specific tool."""
        start = time.time()
        try:
            detect_result = await installer.detect()

            if detect_result.status.value == "installed":
                # Try API check if applicable
                api_ok = False
                if hasattr(installer, "_test_api"):
                    try:
                        api_ok = await installer._test_api()
                    except Exception:
                        pass

                status = VerificationStatus.HEALTHY if api_ok else VerificationStatus.DEGRADED
                message = f"{installer.tool_name} is installed"
                if not api_ok and installer.default_port:
                    message += " but API is not responding"

                return VerificationResult(
                    check_name=f"tool_{installer.tool_key}",
                    status=status,
                    message=message,
                    details={
                        "version": detect_result.version,
                        "install_path": detect_result.install_path,
                        "port": detect_result.port,
                        "api_responding": api_ok,
                    },
                    duration_ms=round((time.time() - start) * 1000, 2),
                    suggestions=(
                        [f"Start {installer.tool_name} service"]
                        if not api_ok and installer.default_port
                        else []
                    ),
                )
            else:
                return VerificationResult(
                    check_name=f"tool_{installer.tool_key}",
                    status=VerificationStatus.UNHEALTHY,
                    message=f"{installer.tool_name} is not installed",
                    duration_ms=round((time.time() - start) * 1000, 2),
                    suggestions=[f"Install {installer.tool_name} using the deployment system"],
                )
        except Exception as e:
            return VerificationResult(
                check_name=f"tool_{installer.tool_key}",
                status=VerificationStatus.UNKNOWN,
                message=f"Failed to check {installer.tool_name}: {str(e)}",
                duration_ms=round((time.time() - start) * 1000, 2),
            )

    async def check_system_resources(self) -> VerificationResult:
        """Check system resource adequacy."""
        start = time.time()
        try:
            import psutil

            ram = psutil.virtual_memory()
            disk = psutil.disk_usage("/")
            cpu_percent = psutil.cpu_percent(interval=0.5)

            issues = []
            status = VerificationStatus.HEALTHY

            if ram.percent > 90:
                status = VerificationStatus.DEGRADED
                issues.append(f"RAM usage at {ram.percent}%")
            if disk.percent > 90:
                status = VerificationStatus.DEGRADED
                issues.append(f"Disk usage at {disk.percent}%")
            if cpu_percent > 90:
                status = VerificationStatus.DEGRADED
                issues.append(f"CPU usage at {cpu_percent}%")

            return VerificationResult(
                check_name="system_resources",
                status=status,
                message="; ".join(issues) if issues else "System resources adequate",
                details={
                    "ram_total_gb": round(ram.total / (1024**3), 1),
                    "ram_available_gb": round(ram.available / (1024**3), 1),
                    "ram_percent": ram.percent,
                    "disk_free_gb": round(disk.free / (1024**3), 1),
                    "disk_percent": disk.percent,
                    "cpu_percent": cpu_percent,
                    "cpu_cores": psutil.cpu_count(logical=True),
                },
                duration_ms=round((time.time() - start) * 1000, 2),
                suggestions=(
                    ["Free up system resources"] if status == VerificationStatus.DEGRADED
                    else []
                ),
            )
        except ImportError:
            return VerificationResult(
                check_name="system_resources",
                status=VerificationStatus.NOT_APPLICABLE,
                message="psutil not available for resource checking",
                duration_ms=round((time.time() - start) * 1000, 2),
            )
        except Exception as e:
            return VerificationResult(
                check_name="system_resources",
                status=VerificationStatus.UNKNOWN,
                message=f"Resource check failed: {str(e)}",
                duration_ms=round((time.time() - start) * 1000, 2),
            )

    async def check_network_connectivity(self) -> VerificationResult:
        """Check network connectivity to essential services."""
        start = time.time()
        try:
            import aiohttp

            endpoints = [
                ("Ollama API", "http://localhost:11434/api/tags"),
                ("LM Studio API", "http://localhost:1234/v1/models"),
                ("Open WebUI", "http://localhost:3000"),
                ("AnythingLLM", "http://localhost:3001"),
                ("ComfyUI", "http://localhost:8188"),
            ]

            reachable = []
            unreachable = []

            async with aiohttp.ClientSession() as session:
                for name, url in endpoints:
                    try:
                        async with session.get(url, timeout=aiohttp.ClientTimeout(total=3)) as resp:
                            if resp.status < 500:
                                reachable.append(name)
                            else:
                                unreachable.append(name)
                    except Exception:
                        unreachable.append(name)

            if reachable and not unreachable:
                status = VerificationStatus.HEALTHY
                message = "All local AI endpoints reachable"
            elif reachable:
                status = VerificationStatus.DEGRADED
                message = f"Some endpoints unreachable: {', '.join(unreachable)}"
            else:
                status = VerificationStatus.DEGRADED
                message = "No local AI endpoints reachable"

            return VerificationResult(
                check_name="network_connectivity",
                status=status,
                message=message,
                details={
                    "reachable": reachable,
                    "unreachable": unreachable,
                },
                duration_ms=round((time.time() - start) * 1000, 2),
                suggestions=(
                    ["Start local AI services"] if not reachable else []
                ),
            )
        except ImportError:
            return VerificationResult(
                check_name="network_connectivity",
                status=VerificationStatus.NOT_APPLICABLE,
                message="aiohttp not available for connectivity check",
                duration_ms=round((time.time() - start) * 1000, 2),
            )
        except Exception as e:
            return VerificationResult(
                check_name="network_connectivity",
                status=VerificationStatus.UNKNOWN,
                message=f"Connectivity check failed: {str(e)}",
                duration_ms=round((time.time() - start) * 1000, 2),
            )

    async def check_python_environment(self) -> VerificationResult:
        """Check Python environment adequacy."""
        start = time.time()
        try:
            import sys
            import subprocess

            py_version = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
            issues = []
            status = VerificationStatus.HEALTHY

            if sys.version_info < (3, 10):
                status = VerificationStatus.DEGRADED
                issues.append(f"Python {py_version} is below recommended 3.10+")

            # Check pip
            result = subprocess.run(
                [sys.executable, "-m", "pip", "--version"],
                capture_output=True, text=True, timeout=10,
            )
            pip_ok = result.returncode == 0

            if not pip_ok:
                status = VerificationStatus.DEGRADED
                issues.append("pip is not available")

            return VerificationResult(
                check_name="python_environment",
                status=status,
                message="; ".join(issues) if issues else "Python environment adequate",
                details={
                    "python_version": py_version,
                    "python_path": sys.executable,
                    "pip_available": pip_ok,
                    "platform": platform.platform(),
                },
                duration_ms=round((time.time() - start) * 1000, 2),
            )
        except Exception as e:
            return VerificationResult(
                check_name="python_environment",
                status=VerificationStatus.UNKNOWN,
                message=f"Python check failed: {str(e)}",
                duration_ms=round((time.time() - start) * 1000, 2),
            )

    async def check_docker(self) -> VerificationResult:
        """Check Docker availability."""
        start = time.time()
        try:
            import subprocess

            result = subprocess.run(
                ["docker", "info", "--format", "{{.ServerVersion}}"],
                capture_output=True, text=True, timeout=10,
            )

            if result.returncode == 0:
                return VerificationResult(
                    check_name="docker",
                    status=VerificationStatus.HEALTHY,
                    message=f"Docker is available (version {result.stdout.strip()})",
                    details={"version": result.stdout.strip()},
                    duration_ms=round((time.time() - start) * 1000, 2),
                )
            else:
                return VerificationResult(
                    check_name="docker",
                    status=VerificationStatus.UNHEALTHY,
                    message="Docker is not available",
                    duration_ms=round((time.time() - start) * 1000, 2),
                    suggestions=["Install Docker Desktop"],
                )
        except FileNotFoundError:
            return VerificationResult(
                check_name="docker",
                status=VerificationStatus.UNHEALTHY,
                message="Docker is not installed",
                duration_ms=round((time.time() - start) * 1000, 2),
                suggestions=["Install Docker Desktop"],
            )
        except Exception as e:
            return VerificationResult(
                check_name="docker",
                status=VerificationStatus.UNKNOWN,
                message=f"Docker check failed: {str(e)}",
                duration_ms=round((time.time() - start) * 1000, 2),
            )

    def get_summary(self, results: List[VerificationResult]) -> Dict[str, Any]:
        """Get a summary of verification results."""
        healthy = sum(1 for r in results if r.is_healthy)
        degraded = sum(1 for r in results if r.is_degraded)
        unhealthy = sum(1 for r in results if r.is_unhealthy)
        unknown = sum(1 for r in results if r.status == VerificationStatus.UNKNOWN)
        na = sum(1 for r in results if r.status == VerificationStatus.NOT_APPLICABLE)

        all_suggestions = []
        for r in results:
            all_suggestions.extend(r.suggestions)

        return {
            "total": len(results),
            "healthy": healthy,
            "degraded": degraded,
            "unhealthy": unhealthy,
            "unknown": unknown,
            "not_applicable": na,
            "overall": (
                "healthy" if unhealthy == 0 and degraded == 0
                else "degraded" if unhealthy == 0
                else "unhealthy"
            ),
            "suggestions": list(set(all_suggestions)),
        }
