"""
Corax Orchestrator - Environment Analyzer Module.

Analyzes the scanned system environment to determine:
- What tools are installed and their versions
- What tools are missing
- Compatibility with deployment requirements
- System readiness for AI development workloads
"""

from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Set

from src.core.logging import get_logger
from src.modules.system_scanner import ScanResult, HardwareSpecs, SoftwareInventory

logger = get_logger(__name__)


# Minimum requirements for AI development workstation
MINIMUM_REQUIREMENTS = {
    "ram_gb": 16,
    "disk_free_gb": 50,
    "cpu_cores": 4,
    "python": "3.10.0",
    "git": None,  # Any version
    "node": "18.0.0",
}


@dataclass
class ToolStatus:
    """Status of a specific tool."""
    name: str
    installed: bool
    version: Optional[str] = None
    required_version: Optional[str] = None
    compatible: bool = False
    install_path: Optional[str] = None
    status_message: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "installed": self.installed,
            "version": self.version,
            "required_version": self.required_version,
            "compatible": self.compatible,
            "install_path": self.install_path,
            "status_message": self.status_message,
        }


@dataclass
class EnvironmentAnalysis:
    """Complete environment analysis result."""
    system_ready: bool = False
    hardware_compatible: bool = False
    hardware_issues: List[str] = field(default_factory=list)
    tools: Dict[str, ToolStatus] = field(default_factory=dict)
    missing_tools: List[str] = field(default_factory=list)
    outdated_tools: List[str] = field(default_factory=list)
    compatible_tools: List[str] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    score: int = 0  # 0-100 readiness score

    def to_dict(self) -> Dict[str, Any]:
        return {
            "system_ready": self.system_ready,
            "hardware_compatible": self.hardware_compatible,
            "hardware_issues": self.hardware_issues,
            "tools": {k: v.to_dict() for k, v in self.tools.items()},
            "missing_tools": self.missing_tools,
            "outdated_tools": self.outdated_tools,
            "compatible_tools": self.compatible_tools,
            "recommendations": self.recommendations,
            "warnings": self.warnings,
            "score": self.score,
        }


class EnvironmentAnalyzer:
    """
    Analyzes system environment for AI development readiness.

    Evaluates hardware capabilities, installed tools, and provides
    recommendations for missing or outdated components.
    """

    # Core tools that define an AI development workstation
    CORE_TOOLS = {
        "git": {"required": True, "min_version": None},
        "python": {"required": True, "min_version": "3.10.0"},
        "pip": {"required": True, "min_version": None},
        "node": {"required": True, "min_version": "18.0.0"},
        "npm": {"required": True, "min_version": None},
        "docker": {"required": False, "min_version": None},
        "code": {"required": False, "min_version": None},
        "ollama": {"required": False, "min_version": None},
        "windsurf": {"required": False, "min_version": None},
    }

    def __init__(self) -> None:
        self._last_analysis: Optional[EnvironmentAnalysis] = None

    def analyze(self, scan_result: ScanResult) -> EnvironmentAnalysis:
        """
        Analyze the scanned system environment.

        Args:
            scan_result: Result from SystemScanner.scan()

        Returns:
            EnvironmentAnalysis with readiness assessment
        """
        logger.info("Starting environment analysis")

        analysis = EnvironmentAnalysis()

        # Analyze hardware
        self._analyze_hardware(scan_result.hardware, analysis)

        # Analyze tools
        self._analyze_tools(scan_result.software, analysis)

        # Calculate readiness score
        analysis.score = self._calculate_score(analysis)

        # Determine overall readiness
        analysis.system_ready = (
            analysis.hardware_compatible
            and len(analysis.missing_tools) == 0
            and len(analysis.outdated_tools) == 0
        )

        # Generate recommendations
        analysis.recommendations = self._generate_recommendations(analysis)

        self._last_analysis = analysis
        logger.info(
            "Environment analysis completed",
            score=analysis.score,
            system_ready=analysis.system_ready,
            missing_tools=len(analysis.missing_tools),
            warnings=len(analysis.warnings),
        )
        return analysis

    def _analyze_hardware(
        self, hardware: HardwareSpecs, analysis: EnvironmentAnalysis
    ) -> None:
        """Analyze hardware specifications against requirements."""
        issues: List[str] = []

        # Check RAM
        ram_gb = hardware.memory.get("total_gb", 0)
        if ram_gb < MINIMUM_REQUIREMENTS["ram_gb"]:
            issues.append(
                f"Insufficient RAM: {ram_gb:.1f} GB (minimum {MINIMUM_REQUIREMENTS['ram_gb']} GB)"
            )

        # Check disk space
        if hardware.disks:
            main_disk = hardware.disks[0]
            free_gb = main_disk.get("free_gb", 0)
            if free_gb < MINIMUM_REQUIREMENTS["disk_free_gb"]:
                issues.append(
                    f"Low disk space: {free_gb:.1f} GB free "
                    f"(recommended {MINIMUM_REQUIREMENTS['disk_free_gb']} GB)"
                )

        # Check CPU cores
        cores = hardware.cpu.get("cores", 0)
        if cores < MINIMUM_REQUIREMENTS["cpu_cores"]:
            issues.append(
                f"Insufficient CPU cores: {cores} (minimum {MINIMUM_REQUIREMENTS['cpu_cores']})"
            )

        # Check GPU
        if not hardware.gpus:
            analysis.warnings.append(
                "No GPU detected. AI model inference will be CPU-only."
            )
        else:
            for gpu in hardware.gpus:
                vram = gpu.get("memory_gb", 0)
                if vram and vram < 4:
                    analysis.warnings.append(
                        f"GPU VRAM ({vram} GB) may be insufficient for large models"
                    )

        analysis.hardware_issues = issues
        analysis.hardware_compatible = len(issues) == 0

    def _analyze_tools(
        self, software: SoftwareInventory, analysis: EnvironmentAnalysis
    ) -> None:
        """Analyze installed tools against requirements."""
        dev_tools = software.development_tools

        for tool_name, requirements in self.CORE_TOOLS.items():
            version = dev_tools.get(tool_name)
            min_version = requirements.get("min_version")

            status = ToolStatus(
                name=tool_name,
                installed=version is not None,
                version=version,
                required_version=min_version,
            )

            if version:
                if min_version:
                    status.compatible = self._check_version_compatibility(
                        version, min_version
                    )
                    if not status.compatible:
                        status.status_message = (
                            f"Version {version} is below minimum {min_version}"
                        )
                        analysis.outdated_tools.append(tool_name)
                    else:
                        status.status_message = f"Version {version} is compatible"
                        analysis.compatible_tools.append(tool_name)
                else:
                    status.compatible = True
                    status.status_message = f"Installed: {version}"
                    analysis.compatible_tools.append(tool_name)
            else:
                if requirements["required"]:
                    status.status_message = "Not installed (required)"
                    analysis.missing_tools.append(tool_name)
                else:
                    status.status_message = "Not installed (optional)"
                    analysis.warnings.append(
                        f"Optional tool '{tool_name}' is not installed"
                    )

            analysis.tools[tool_name] = status

    def _check_version_compatibility(
        self, version_str: str, min_version_str: str
    ) -> bool:
        """Check if a version meets minimum requirements."""
        try:
            # Extract version number from string (e.g., "Python 3.11.4" -> "3.11.4")
            import re
            version_match = re.search(r"(\d+\.\d+\.\d+)", version_str)
            min_match = re.search(r"(\d+\.\d+\.\d+)", min_version_str)

            if not version_match:
                return True  # Can't parse, assume compatible

            current = tuple(int(x) for x in version_match.group(1).split("."))
            minimum = tuple(int(x) for x in min_match.group(1).split("."))

            return current >= minimum
        except Exception:
            return True  # On error, assume compatible

    def _calculate_score(self, analysis: EnvironmentAnalysis) -> int:
        """Calculate a 0-100 readiness score."""
        score = 100

        # Deduct for hardware issues
        score -= len(analysis.hardware_issues) * 15

        # Deduct for missing required tools
        score -= len(analysis.missing_tools) * 10

        # Deduct for outdated tools
        score -= len(analysis.outdated_tools) * 5

        # Deduct for warnings
        score -= len(analysis.warnings) * 3

        return max(0, min(100, score))

    def _generate_recommendations(
        self, analysis: EnvironmentAnalysis
    ) -> List[str]:
        """Generate actionable recommendations."""
        recommendations = []

        if analysis.hardware_issues:
            recommendations.append(
                "Address hardware limitations before proceeding with deployment"
            )

        for tool in analysis.missing_tools:
            recommendations.append(f"Install required tool: {tool}")

        for tool in analysis.outdated_tools:
            status = analysis.tools.get(tool)
            if status:
                recommendations.append(
                    f"Update {tool} from {status.version} to {status.required_version}+"
                )

        if any("No GPU detected" in w for w in analysis.warnings):
            recommendations.append(
                "Consider using cloud GPU instances for model training"
            )

        return recommendations

    def get_last_analysis(self) -> Optional[EnvironmentAnalysis]:
        """Get the last analysis result."""
        return self._last_analysis
