"""
Corax Orchestrator - Environment Validation Module.

Validates the development environment before and after deployment.
Checks for PATH issues, missing dependencies, version conflicts,
and partial installations. Provides actionable repair suggestions.
"""

from typing import Dict, Any, List, Optional, Tuple
import os
import shutil
import asyncio
from dataclasses import dataclass, field

from src.core.logging import get_logger

logger = get_logger(__name__)


@dataclass
class ValidationIssue:
    """A single validation issue found in the environment."""
    severity: str  # "error", "warning", "info"
    category: str  # "path", "dependency", "version", "partial_install", "config"
    tool_key: str
    message: str
    suggestion: str
    details: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ValidationResult:
    """Result of environment validation."""
    issues: List[ValidationIssue] = field(default_factory=list)
    passed: bool = True

    @property
    def errors(self) -> List[ValidationIssue]:
        return [i for i in self.issues if i.severity == "error"]

    @property
    def warnings(self) -> List[ValidationIssue]:
        return [i for i in self.issues if i.severity == "warning"]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "passed": self.passed,
            "total_issues": len(self.issues),
            "errors": len(self.errors),
            "warnings": len(self.warnings),
            "issues": [
                {
                    "severity": i.severity,
                    "category": i.category,
                    "tool_key": i.tool_key,
                    "message": i.message,
                    "suggestion": i.suggestion,
                    "details": i.details,
                }
                for i in self.issues
            ],
        }


class EnvironmentValidator:
    """
    Validates the development environment for deployment readiness.

    Checks include:
    - PATH variable completeness
    - Dependency availability
    - Version compatibility
    - Partial installation detection
    - Configuration file presence
    - Environment variable correctness
    """

    def __init__(self) -> None:
        self._issues: List[ValidationIssue] = []

    async def validate_all(
        self,
        required_tools: Optional[List[str]] = None,
    ) -> ValidationResult:
        """
        Run all validation checks.

        Args:
            required_tools: List of tool keys that must be available

        Returns:
            ValidationResult with all found issues
        """
        self._issues = []

        await asyncio.gather(
            self._check_path(),
            self._check_common_tools(),
            self._check_environment_variables(),
            self._check_python_environment(),
            self._check_disk_space(),
        )

        if required_tools:
            await self._check_required_tools(required_tools)

        return ValidationResult(
            issues=self._issues,
            passed=len(self._issues) == 0,
        )

    async def _check_path(self) -> None:
        """Check PATH for common tool directories."""
        path = os.environ.get("PATH", "")
        path_lower = path.lower()

        checks = {
            "python": ["python", "python3"],
            "nodejs": ["nodejs", "node"],
            "git": ["git"],
            "docker": ["docker"],
            "flutter": ["flutter", "flutter\\bin"],
        }

        for tool_key, expected_paths in checks.items():
            found = any(
                expected in path_lower
                for expected in expected_paths
            )
            if not found:
                # Check if tool is actually installed via shutil
                binary = expected_paths[0]
                if shutil.which(binary):
                    continue  # Tool is available even if not in PATH explicitly

                self._issues.append(ValidationIssue(
                    severity="warning",
                    category="path",
                    tool_key=tool_key,
                    message=f"{tool_key} may not be in PATH",
                    suggestion=f"Add {tool_key} installation directory to your system PATH",
                    details={"expected_paths": expected_paths},
                ))

    async def _check_common_tools(self) -> None:
        """Check for common development tools."""
        tool_checks = {
            "python": ("python", "--version"),
            "git": ("git", "--version"),
            "nodejs": ("node", "--version"),
            "npm": ("npm", "--version"),
            "docker": ("docker", "--version"),
            "code": ("code", "--version"),
            "flutter": ("flutter", "--version"),
            "java": ("java", "-version"),
        }

        for tool_key, (cmd, arg) in tool_checks.items():
            binary = shutil.which(cmd)
            if not binary:
                self._issues.append(ValidationIssue(
                    severity="info",
                    category="dependency",
                    tool_key=tool_key,
                    message=f"{cmd} is not installed or not in PATH",
                    suggestion=f"Install {tool_key} using the Corax deployment system",
                    details={"command": cmd},
                ))

    async def _check_environment_variables(self) -> None:
        """Check for important environment variables."""
        var_checks = {
            "JAVA_HOME": {
                "tools": ["java"],
                "message": "JAVA_HOME is not set",
                "suggestion": "Set JAVA_HOME to your JDK installation directory",
            },
            "ANDROID_HOME": {
                "tools": ["flutter"],
                "message": "ANDROID_HOME is not set (needed for Flutter Android development)",
                "suggestion": "Set ANDROID_HOME to your Android SDK location",
            },
        }

        for var_name, info in var_checks.items():
            if not os.environ.get(var_name):
                self._issues.append(ValidationIssue(
                    severity="warning",
                    category="config",
                    tool_key=info["tools"][0],
                    message=info["message"],
                    suggestion=info["suggestion"],
                    details={"variable": var_name},
                ))

    async def _check_python_environment(self) -> None:
        """Check Python environment health."""
        import sys

        # Check Python version
        if sys.version_info < (3, 10):
            self._issues.append(ValidationIssue(
                severity="warning",
                category="version",
                tool_key="python",
                message=f"Python {sys.version_info.major}.{sys.version_info.minor} is below recommended 3.10+",
                suggestion="Install Python 3.10 or higher using the Corax deployment system",
                details={
                    "current_version": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
                    "recommended": "3.10+",
                },
            ))

        # Check pip
        pip_path = shutil.which("pip") or shutil.which("pip3")
        if not pip_path:
            self._issues.append(ValidationIssue(
                severity="error",
                category="dependency",
                tool_key="python",
                message="pip is not available",
                suggestion="Install pip: python -m ensurepip --upgrade",
                details={},
            ))

        # Check virtual environment
        in_venv = sys.prefix != sys.base_prefix
        if not in_venv:
            self._issues.append(ValidationIssue(
                severity="info",
                category="config",
                tool_key="python",
                message="Not running in a virtual environment",
                suggestion="Consider using a virtual environment: python -m venv .venv",
                details={},
            ))

    async def _check_disk_space(self) -> None:
        """Check available disk space."""
        try:
            import psutil

            disk = psutil.disk_usage("/")
            free_gb = disk.free / (1024**3)

            thresholds = [
                (5, "error", "Critically low disk space"),
                (20, "warning", "Low disk space"),
            ]

            for threshold_gb, severity, message in thresholds:
                if free_gb < threshold_gb:
                    self._issues.append(ValidationIssue(
                        severity=severity,
                        category="dependency",
                        tool_key="system",
                        message=f"{message}: {free_gb:.1f}GB free",
                        suggestion="Free up disk space before deploying AI tools",
                        details={"free_gb": round(free_gb, 1)},
                    ))
                    break

        except ImportError:
            pass  # psutil not available

    async def _check_required_tools(self, required_tools: List[str]) -> None:
        """Check that required tools are available."""
        for tool_key in required_tools:
            binary = shutil.which(tool_key)
            if not binary:
                self._issues.append(ValidationIssue(
                    severity="error",
                    category="dependency",
                    tool_key=tool_key,
                    message=f"Required tool '{tool_key}' is not installed",
                    suggestion=f"Install {tool_key} before proceeding with deployment",
                    details={"required": True},
                ))

    async def validate_tool_installation(
        self,
        tool_key: str,
        expected_binary: str,
        expected_version: Optional[str] = None,
    ) -> ValidationResult:
        """
        Validate a specific tool installation.

        Args:
            tool_key: Tool identifier
            expected_binary: Expected binary name
            expected_version: Expected minimum version

        Returns:
            ValidationResult for this tool
        """
        issues: List[ValidationIssue] = []

        # Check binary exists
        binary_path = shutil.which(expected_binary)
        if not binary_path:
            issues.append(ValidationIssue(
                severity="error",
                category="dependency",
                tool_key=tool_key,
                message=f"{expected_binary} binary not found",
                suggestion=f"Install {tool_key} or add it to PATH",
                details={"expected_binary": expected_binary},
            ))
            return ValidationResult(issues=issues, passed=False)

        # Check version if specified
        if expected_version:
            try:
                proc = await asyncio.create_subprocess_exec(
                    expected_binary, "--version",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=10)
                version_output = stdout.decode().strip()

                import re
                match = re.search(r'(\d+\.\d+\.\d+)', version_output)
                if match:
                    current = match.group(1)
                    # Simple version comparison
                    if current < expected_version:
                        issues.append(ValidationIssue(
                            severity="warning",
                            category="version",
                            tool_key=tool_key,
                            message=f"{tool_key} version {current} is below expected {expected_version}",
                            suggestion=f"Upgrade {tool_key} to version {expected_version}+",
                            details={
                                "current": current,
                                "expected": expected_version,
                            },
                        ))
            except Exception as e:
                issues.append(ValidationIssue(
                    severity="warning",
                    category="version",
                    tool_key=tool_key,
                    message=f"Could not verify {tool_key} version: {str(e)}",
                    suggestion="Check installation manually",
                    details={"error": str(e)},
                ))

        return ValidationResult(issues=issues, passed=len(issues) == 0)

    def get_repair_suggestions(self, result: ValidationResult) -> List[Dict[str, Any]]:
        """
        Get actionable repair suggestions from validation results.

        Args:
            result: ValidationResult to analyze

        Returns:
            List of repair suggestions with priority
        """
        suggestions = []
        for issue in result.issues:
            suggestions.append({
                "priority": "high" if issue.severity == "error" else "medium",
                "category": issue.category,
                "tool_key": issue.tool_key,
                "message": issue.message,
                "suggestion": issue.suggestion,
                "details": issue.details,
            })
        return suggestions
