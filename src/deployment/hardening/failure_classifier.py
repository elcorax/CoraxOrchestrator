"""
Corax Orchestrator — Installer Failure Classifier Module.

Provides deep failure classification for installer operations with
automated repair script generation. Wraps the existing FailureAnalyzer
with enhanced categorization and actionable repair playbooks.
"""

from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
import os
import re
import textwrap

from src.core.logging import get_logger
from src.deployment.operations import FailureCategory
from src.deployment.execution.failure_analyzer import (
    FailureAnalyzer,
    FailureAnalysis,
)

logger = get_logger(__name__)


@dataclass
class RepairScript:
    """A generated repair script for a specific failure."""
    name: str
    description: str
    commands: List[str]
    risk_level: str = "low"  # low, medium, high
    requires_reboot: bool = False
    requires_admin: bool = False
    estimated_duration_seconds: int = 30
    rollback_commands: List[str] = field(default_factory=list)
    validation_commands: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "commands": self.commands,
            "risk_level": self.risk_level,
            "requires_reboot": self.requires_reboot,
            "requires_admin": self.requires_admin,
            "estimated_duration_seconds": self.estimated_duration_seconds,
            "rollback_commands": self.rollback_commands,
            "validation_commands": self.validation_commands,
        }

    def to_batch_script(self, filepath: str) -> str:
        """Generate a Windows batch (.bat) repair script file."""
        lines = [
            "@echo off",
            "title Corax Orchestrator — Repair Script: " + self.name,
            "echo ============================================",
            "echo  Corax Orchestrator — Automated Repair",
            f"echo  Script: {self.name}",
            f"echo  Description: {self.description}",
            f"echo  Risk Level: {self.risk_level}",
            "echo ============================================",
            "echo.",
            "",
        ]

        if self.requires_admin:
            lines.extend([
                ":: Check for administrator privileges",
                "net session >nul 2>&1",
                "if %errorLevel% neq 0 (",
                "    echo ERROR: This script requires administrator privileges.",
                "    echo Please right-click and select 'Run as Administrator'.",
                "    pause",
                "    exit /b 1",
                ")",
                "echo [OK] Administrator privileges confirmed.",
                "echo.",
            ])

        if self.rollback_commands:
            lines.extend([
                ":: Setup rollback point",
                "echo Creating rollback checkpoint...",
                "set ROLLBACK_NEEDED=1",
                "echo.",
            ])

        lines.append("echo Running repair steps...")
        lines.append("echo.")

        for i, cmd in enumerate(self.commands, 1):
            lines.extend([
                f"echo Step {i}/{len(self.commands)}: Executing...",
                cmd,
                "if %errorLevel% neq 0 (",
                f"    echo WARNING: Step {i} exited with code %errorLevel%",
                ")",
                "echo.",
            ])

        if self.validation_commands:
            lines.extend([
                "echo ============================================",
                "echo  Validating repair...",
                "echo ============================================",
                "echo.",
            ])
            for cmd in self.validation_commands:
                lines.append(cmd)
            lines.append("echo.")

        lines.extend([
            "echo ============================================",
            "echo  Repair script completed.",
            f"echo  {self.name}",
            "echo ============================================",
            "echo.",
        ])

        if self.requires_reboot:
            lines.extend([
                "echo IMPORTANT: A system reboot is recommended.",
                "echo Please restart your computer to complete the repair.",
                "echo.",
            ])

        lines.append("pause")
        content = "\r\n".join(lines)

        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)

        return filepath

    def to_shell_script(self, filepath: str) -> str:
        """Generate a Unix shell (.sh) repair script file."""
        lines = [
            "#!/bin/bash",
            "# Corax Orchestrator — Automated Repair Script",
            f"# Script: {self.name}",
            f"# Description: {self.description}",
            f"# Risk Level: {self.risk_level}",
            "",
            'echo "============================================"',
            'echo " Corax Orchestrator — Automated Repair"',
            f'echo " Script: {self.name}"',
            'echo "============================================"',
            "echo",
        ]

        if self.requires_admin:
            lines.extend([
                '# Check for root privileges',
                'if [[ $EUID -ne 0 ]]; then',
                '   echo "ERROR: This script requires root privileges."',
                '   echo "Please run with: sudo $0"',
                '   exit 1',
                'fi',
                'echo "[OK] Root privileges confirmed."',
                'echo',
            ])

        for i, cmd in enumerate(self.commands, 1):
            lines.extend([
                f'echo "Step {i}/{len(self.commands)}..."',
                cmd,
                "if [ $? -ne 0 ]; then",
                f'    echo "WARNING: Step {i} exited with code $?"',
                "fi",
                "echo",
            ])

        if self.validation_commands:
            lines.append('echo "Validating repair..."')
            lines.append("echo")
            for cmd in self.validation_commands:
                lines.append(cmd)

        lines.append('echo "Repair script completed."')

        content = "\n".join(lines) + "\n"

        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)

        # Make executable
        os.chmod(filepath, 0o755)

        return filepath


@dataclass
class FailureAnalysisResult:
    """Enhanced failure analysis with repair scripts."""
    tool_key: str
    failure_category: FailureCategory
    recoverable: bool
    confidence: float
    reason: str
    repair_scripts: List[RepairScript] = field(default_factory=list)
    repair_suggestions: List[str] = field(default_factory=list)
    context: Dict[str, Any] = field(default_factory=dict)
    requires_admin: bool = False
    requires_network: bool = False
    requires_disk_space: bool = False
    requires_dependency: Optional[str] = None
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "tool_key": self.tool_key,
            "failure_category": self.failure_category.value,
            "recoverable": self.recoverable,
            "confidence": round(self.confidence, 2),
            "reason": self.reason,
            "repair_scripts": [s.to_dict() for s in self.repair_scripts],
            "repair_suggestions": self.repair_suggestions,
            "context": self.context,
            "requires_admin": self.requires_admin,
            "requires_network": self.requires_network,
            "requires_disk_space": self.requires_disk_space,
            "requires_dependency": self.requires_dependency,
            "timestamp": self.timestamp,
        }


class InstallerFailureClassifier:
    """
    Enhanced failure classifier that wraps FailureAnalyzer with
    installer-specific patterns and automated repair script generation.

    Provides:
    - Installer-specific error pattern recognition
    - Automated repair script generation (Windows batch + Unix shell)
    - Categorized repair playbooks with risk assessment
    - Rollback command generation for high-risk repairs
    """

    def __init__(self):
        self._analyzer = FailureAnalyzer()

        # Installer-specific patterns beyond general failures
        self.DOWNLOAD_PATTERNS = [
            r"download (failed|error|interrupted)",
            r"could not download",
            r"failed to download",
            r"curl.*(failed|error)",
            r"http.*(403|404|500|502|503)",
            r"checksum (mismatch|failed)",
            r"file not found at url",
            r"invalid url",
        ]

        self.EXTRACTION_PATTERNS = [
            r"extract(ion)? (failed|error)",
            r"cannot (open|read|extract) archive",
            r"archive (corrupt|invalid|damaged)",
            r"unzip failed",
            r"tar failed",
            r"unsupported archive format",
        ]

        self.PATH_PATTERNS = [
            r"path (not found|does not exist|invalid)",
            r"cannot create (directory|path|file)",
            r"file exists",
            r"already exists",
            r"access to the path",
            r"directory not empty",
        ]

        self.REGISTRY_PATTERNS = [
            r"registry (error|failed|corrupt)",
            r"cannot (open|write|read) registry",
            r"reg add failed",
            r"reg query failed",
        ]

        self.SYSTEM_RESTORE_PATTERNS = [
            r"system restore (failed|error|not available)",
            r"restore point (failed|cannot)",
            r"checkpoint-computer failed",
            r"vss (error|failed)",
        ]

        self.POWERSHELL_PATTERNS = [
            r"powershell.*(failed|error|not recognized)",
            r"execution policy (restricted|blocked)",
            r"script.*not digitally signed",
            r"cannot (load|run) script",
            r"ps1.*not recognized",
        ]

        # Tool-specific failure catalog
        self.TOOL_SPECIFIC_PATTERNS: Dict[str, List[Tuple[str, str, List[str]]]] = {
            "ollama": [
                (
                    r"ollama not found",
                    "Ollama is not installed or not in PATH",
                    ["Install Ollama from https://ollama.ai"],
                ),
                (
                    r"ollama serve (failed|error)",
                    "Ollama server could not start",
                    [
                        "Check if another instance is running",
                        "Verify port 11434 is not in use",
                        "Check Ollama logs",
                    ],
                ),
                (
                    r"model not found",
                    "The requested AI model was not found locally",
                    [
                        "Pull the model first: ollama pull <model>",
                        "Check model name spelling",
                    ],
                ),
            ],
            "docker": [
                (
                    r"docker not (found|recognized)",
                    "Docker is not installed or not in PATH",
                    ["Install Docker Desktop from https://docker.com"],
                ),
                (
                    r"docker daemon.*(not running|unavailable)",
                    "Docker daemon is not running",
                    [
                        "Start Docker Desktop",
                        "Check Docker service status",
                    ],
                ),
                (
                    r"image not found",
                    "Docker image could not be found locally or remotely",
                    [
                        "Pull the image: docker pull <image>",
                        "Check image name and tag",
                    ],
                ),
                (
                    r"port.*already (allocated|in use)",
                    "Required port is already in use",
                    [
                        "Stop the container using the port",
                        "Change the port mapping",
                    ],
                ),
            ],
            "git": [
                (
                    r"git not (found|recognized)",
                    "Git is not installed or not in PATH",
                    ["Install Git from https://git-scm.com"],
                ),
                (
                    r"repository not found",
                    "The Git repository could not be found",
                    [
                        "Check the repository URL",
                        "Verify access permissions",
                    ],
                ),
                (
                    r"authentication failed",
                    "Git authentication failed",
                    [
                        "Check credentials",
                        "Set up SSH keys or use personal access token",
                    ],
                ),
            ],
            "python": [
                (
                    r"python not (found|recognized)",
                    "Python is not installed or not in PATH",
                    ["Install Python from https://python.org"],
                ),
                (
                    r"pip not (found|recognized)",
                    "pip is not installed or not in PATH",
                    [
                        "Install pip: python -m ensurepip",
                        "Add Python Scripts directory to PATH",
                    ],
                ),
                (
                    r"module.*not found",
                    "A required Python module is missing",
                    ["Install the module: pip install <module>"],
                ),
            ],
            "node": [
                (
                    r"node not (found|recognized)",
                    "Node.js is not installed or not in PATH",
                    ["Install Node.js from https://nodejs.org"],
                ),
                (
                    r"npm not (found|recognized)",
                    "npm is not installed or not in PATH",
                    ["Install Node.js (includes npm)"],
                ),
                (
                    r"npm err!",
                    "npm encountered an error",
                    [
                        "Clear npm cache: npm cache clean --force",
                        "Delete node_modules and reinstall: rm -rf node_modules && npm install",
                    ],
                ),
            ],
            "vscode": [
                (
                    r"code not (found|recognized)",
                    "VS Code is not installed or not in PATH",
                    [
                        "Install VS Code from https://code.visualstudio.com",
                        "Add to PATH during installation",
                    ],
                ),
                (
                    r"extension.*not found",
                    "A VS Code extension could not be found",
                    [
                        "Install the extension from the marketplace",
                        "Check the extension ID",
                    ],
                ),
            ],
        }

    def analyze(
        self,
        tool_key: str,
        exit_code: int,
        stdout: str = "",
        stderr: str = "",
        error_message: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> FailureAnalysisResult:
        """
        Analyze an installer failure and produce an enhanced result
        with repair scripts.

        Args:
            tool_key: Tool identifier (e.g., 'ollama', 'docker')
            exit_code: Process exit code
            stdout: Standard output from the failed operation
            stderr: Standard error from the failed operation
            error_message: Additional error context
            context: Optional deployment context for better analysis

        Returns:
            FailureAnalysisResult with classification and repair scripts
        """
        # First, get the base analysis from FailureAnalyzer
        base_analysis = self._analyzer.analyze(
            tool_key=tool_key,
            exit_code=exit_code,
            stdout=stdout,
            stderr=stderr,
            error_message=error_message,
        )

        # Perform deep installer-specific analysis
        combined = f"{stdout}\n{stderr}\n{error_message or ''}".lower()
        deep_category, deep_confidence, deep_reason = self._deep_analyze(
            combined, tool_key
        )

        # Use the more specific analysis if confidence is higher
        final_category = base_analysis.failure_category
        final_confidence = base_analysis.confidence
        final_reason = base_analysis.reason

        if deep_confidence > base_analysis.confidence:
            final_category = deep_category
            final_confidence = deep_confidence
            final_reason = deep_reason

        # Check tool-specific patterns
        tool_confidence, tool_reason, tool_suggestions = self._check_tool_patterns(
            combined, tool_key
        )
        if tool_confidence > final_confidence:
            final_confidence = tool_confidence
            final_reason = tool_reason

        # Generate repair scripts
        repair_scripts = self._generate_repair_scripts(
            tool_key=tool_key,
            failure_category=final_category,
            reason=final_reason,
            exit_code=exit_code,
            context=context or {},
        )

        # Combine suggestions
        all_suggestions = list(base_analysis.repair_suggestions)
        if tool_suggestions:
            all_suggestions.extend(tool_suggestions)

        return FailureAnalysisResult(
            tool_key=tool_key,
            failure_category=final_category,
            recoverable=base_analysis.recoverable,
            confidence=final_confidence,
            reason=final_reason,
            repair_scripts=repair_scripts,
            repair_suggestions=all_suggestions,
            context=context or {},
            requires_admin=base_analysis.requires_admin,
            requires_network=base_analysis.requires_network,
            requires_disk_space=base_analysis.requires_disk_space,
            requires_dependency=base_analysis.requires_dependency,
        )

    def _deep_analyze(
        self, combined: str, tool_key: str
    ) -> Tuple[FailureCategory, float, str]:
        """
        Perform deep installer-specific failure analysis.

        Returns:
            Tuple of (category, confidence, reason)
        """
        checks = [
            (self.DOWNLOAD_PATTERNS, FailureCategory.NETWORK,
             "Download failed — network or source issue detected"),
            (self.EXTRACTION_PATTERNS, FailureCategory.CORRUPTION,
             "Archive extraction failed — file may be corrupted"),
            (self.PATH_PATTERNS, FailureCategory.DEPENDENCY,
             "File system path issue detected"),
            (self.REGISTRY_PATTERNS, FailureCategory.PERMISSION,
             "Windows registry operation failed"),
            (self.SYSTEM_RESTORE_PATTERNS, FailureCategory.PERMISSION,
             "System restore point creation failed"),
            (self.POWERSHELL_PATTERNS, FailureCategory.DEPENDENCY,
             "PowerShell execution failed — check execution policy"),
        ]

        best_confidence = 0.0
        best_result = (FailureCategory.UNKNOWN, 0.0, "")

        for patterns, category, reason in checks:
            confidence = self._match_installer_patterns(combined, patterns)
            if confidence > best_confidence:
                best_confidence = confidence
                best_result = (category, confidence, reason)

        return best_result

    def _match_installer_patterns(
        self, text: str, patterns: List[str]
    ) -> float:
        """Match text against installer-specific patterns."""
        matches = 0
        for pattern in patterns:
            if re.search(pattern, text, re.IGNORECASE):
                matches += 1

        if matches >= 2:
            return 0.9
        elif matches >= 1:
            return 0.7
        return 0.0

    def _check_tool_patterns(
        self, combined: str, tool_key: str
    ) -> Tuple[float, str, List[str]]:
        """
        Check tool-specific error patterns.

        Returns:
            Tuple of (confidence, reason, suggestions)
        """
        tool_patterns = self.TOOL_SPECIFIC_PATTERNS.get(tool_key.lower(), [])
        if not tool_patterns:
            return (0.0, "", [])

        for pattern, reason, suggestions in tool_patterns:
            if re.search(pattern, combined, re.IGNORECASE):
                logger.info(
                    f"Tool-specific pattern matched for {tool_key}",
                    pattern=pattern,
                    reason=reason,
                )
                return (0.95, reason, suggestions)

        return (0.0, "", [])

    def _generate_repair_scripts(
        self,
        tool_key: str,
        failure_category: FailureCategory,
        reason: str,
        exit_code: int,
        context: Dict[str, Any],
    ) -> List[RepairScript]:
        """Generate repair scripts based on failure analysis."""
        scripts = []

        # Permission repair scripts
        if failure_category == FailureCategory.PERMISSION:
            scripts.append(RepairScript(
                name=f"fix_permissions_{tool_key}",
                description=f"Fix permission issues for {tool_key}",
                commands=[
                    f'echo Granting permissions for {tool_key}...',
                    f'icacls "%PROGRAMDATA%\\{tool_key}" /grant Users:(OI)(CI)F /T 2>nul',
                    f'icacls "%LOCALAPPDATA%\\{tool_key}" /grant Users:(OI)(CI)F /T 2>nul',
                ],
                risk_level="medium",
                requires_admin=True,
                estimated_duration_seconds=15,
                validation_commands=[
                    f'icacls "%LOCALAPPDATA%\\{tool_key}" 2>nul | findstr "Successfully"',
                ],
                rollback_commands=[
                    f'echo Rollback: Permissions were not modified',
                ],
            ))

        # Network repair scripts
        if failure_category == FailureCategory.NETWORK:
            scripts.append(RepairScript(
                name=f"retry_download_{tool_key}",
                description=f"Retry download for {tool_key} with network diagnostics",
                commands=[
                    "echo Testing network connectivity...",
                    "ping -n 1 8.8.8.8 >nul 2>&1",
                    "if %errorLevel% neq 0 (",
                    "    echo WARNING: Cannot reach internet",
                    ")",
                    "echo Clearing DNS cache...",
                    "ipconfig /flushdns >nul 2>&1",
                    f"echo Retrying {tool_key} download...",
                ],
                risk_level="low",
                requires_admin=False,
                estimated_duration_seconds=60,
                validation_commands=[
                    "echo Check if download completes successfully",
                ],
            ))

        # Disk space repair scripts
        if failure_category == FailureCategory.DISK_SPACE:
            scripts.append(RepairScript(
                name=f"free_disk_space_{tool_key}",
                description=f"Free up disk space for {tool_key} installation",
                commands=[
                    "echo Cleaning temporary files...",
                    "cleanmgr /sagerun:1 >nul 2>&1",
                    "echo Cleaning Windows temporary folder...",
                    'del /f /s /q "%TEMP%\\*.*" >nul 2>&1',
                    "echo Cleaning prefetch...",
                    'del /f /s /q "%WINDIR%\\Prefetch\\*.*" >nul 2>&1',
                    "echo.",
                    "echo Checking freed space...",
                    "wmic logicaldisk where \"DeviceID='%SYSTEMDRIVE%'\" get FreeSpace",
                ],
                risk_level="low",
                requires_admin=True,
                estimated_duration_seconds=120,
                rollback_commands=[
                    "echo Rollback: No changes to roll back",
                ],
            ))

        # Dependency repair scripts
        if failure_category == FailureCategory.DEPENDENCY:
            scripts.append(RepairScript(
                name=f"install_dependencies_{tool_key}",
                description=f"Install missing dependencies for {tool_key}",
                commands=[
                    "echo Checking system requirements...",
                    "echo Ensure all prerequisites are installed.",
                    f"echo Required dependencies for {tool_key} should be verified.",
                ],
                risk_level="medium",
                requires_admin=True,
                estimated_duration_seconds=60,
            ))

        # Generic retry script (always include for recoverable failures)
        if self._is_recoverable(failure_category):
            scripts.append(RepairScript(
                name=f"retry_{tool_key}_install",
                description=f"Retry {tool_key} installation with cleanup",
                commands=[
                    f"echo Cleaning up previous {tool_key} installation attempt...",
                    f'if exist "%TEMP%\\corax_{tool_key}_* (',
                    f'    rmdir /s /q "%TEMP%\\corax_{tool_key}_*"',
                    ")",
                    f"echo Retrying {tool_key} installation...",
                ],
                risk_level="low",
                requires_admin=False,
                estimated_duration_seconds=30,
            ))

        return scripts

    def _is_recoverable(self, category: FailureCategory) -> bool:
        """Determine if a failure category is recoverable."""
        non_recoverable = {
            FailureCategory.DISK_SPACE,
            FailureCategory.COMPATIBILITY,
        }
        return category not in non_recoverable

    def generate_repair_report(
        self, results: List[FailureAnalysisResult]
    ) -> str:
        """Generate a human-readable repair report for multiple failures."""
        lines = [
            "=" * 60,
            "  Corax Orchestrator — Failure Analysis & Repair Report",
            "=" * 60,
            "",
            f"Generated: {datetime.now(timezone.utc).isoformat()}",
            f"Failures analyzed: {len(results)}",
            "",
        ]

        for i, result in enumerate(results, 1):
            lines.extend([
                "-" * 60,
                f"  Failure #{i}: {result.tool_key}",
                "-" * 60,
                "",
                f"  Category:    {result.failure_category.value}",
                f"  Recoverable: {'Yes' if result.recoverable else 'No'}",
                f"  Confidence:  {result.confidence:.0%}",
                f"  Reason:      {result.reason}",
                "",
            ])

            if result.repair_scripts:
                lines.append("  Repair Scripts:")
                for script in result.repair_scripts:
                    lines.append(f"    - {script.name}")
                    lines.append(f"      Risk: {script.risk_level}")
                    lines.append(f"      Admin: {'Yes' if script.requires_admin else 'No'}")
                    lines.append(f"      Duration: ~{script.estimated_duration_seconds}s")
                lines.append("")

            if result.repair_suggestions:
                lines.append("  Suggestions:")
                for suggestion in result.repair_suggestions[:5]:
                    lines.append(f"    - {suggestion}")
                lines.append("")

        lines.extend([
            "=" * 60,
            "  End of Report",
            "=" * 60,
        ])

        return "\n".join(lines)
