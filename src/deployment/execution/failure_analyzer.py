"""
Corax Orchestrator - Failure Analyzer.

Analyzes deployment failures to classify them, determine recoverability,
and generate repair recommendations. Used by the retry queue and repair engine.
"""

from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass, field
import re

from src.core.logging import get_logger
from src.deployment.operations import FailureCategory

logger = get_logger(__name__)


@dataclass
class FailureAnalysis:
    """Analysis result for a deployment failure."""
    tool_key: str
    failure_category: FailureCategory
    recoverable: bool
    confidence: float  # 0.0 to 1.0
    reason: str
    repair_suggestions: List[str] = field(default_factory=list)
    requires_admin: bool = False
    requires_network: bool = False
    requires_disk_space: bool = False
    requires_dependency: Optional[str] = None
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "tool_key": self.tool_key,
            "failure_category": self.failure_category.value,
            "recoverable": self.recoverable,
            "confidence": round(self.confidence, 2),
            "reason": self.reason,
            "repair_suggestions": self.repair_suggestions,
            "requires_admin": self.requires_admin,
            "requires_network": self.requires_network,
            "requires_disk_space": self.requires_disk_space,
            "requires_dependency": self.requires_dependency,
            "details": self.details,
        }


class FailureAnalyzer:
    """
    Analyzes deployment failures to classify and determine recoverability.

    Uses pattern matching on error messages, exit codes, and stderr output
    to classify failures into categories and generate repair suggestions.
    """

    # Patterns for common failure types
    PERMISSION_PATTERNS = [
        r"access denied",
        r"permission denied",
        r"requires admin",
        r"administrator",
        r"elevated",
        r"access is denied",
        r"0x5",  # Windows access denied
        r"unauthorized",
        r"insufficient privileges",
    ]

    NETWORK_PATTERNS = [
        r"connection refused",
        r"connection timed out",
        r"network (is |not )?unreachable",
        r"no route to host",
        r"dns lookup failed",
        r"name or service not known",
        r"could not resolve",
        r"download failed",
        r"timeout",
        r"ssl error",
        r"certificate verify failed",
        r"connection reset",
        r"broken pipe",
        r"errno 1006[0-1]",  # Windows connection errors
    ]

    DISK_PATTERNS = [
        r"disk (space|full)",
        r"no space left",
        r"insufficient disk",
        r"not enough space",
        r"disk quota",
        r"errno 28",  # ENOSPC
        r"out of (disk|storage)",
    ]

    DEPENDENCY_PATTERNS = [
        r"dependency (missing|not found|required)",
        r"requires .* to be installed",
        r"command not found",
        r"not recognized",
        r"is not installed",
        r"missing (dependency|package|module)",
        r"cannot find",
        r"no such file or directory",
        r"dll not found",
        r"module not found",
    ]

    CORRUPTION_PATTERNS = [
        r"corrupt(ed|ion)?",
        r"checksum (mismatch|failed|invalid)",
        r"hash (mismatch|failed|invalid)",
        r"invalid (file|archive|package)",
        r"unexpected end of",
        r"bad (file|archive|download)",
        r"crc (mismatch|failed)",
    ]

    COMPATIBILITY_PATTERNS = [
        r"not compatible",
        r"incompatible",
        r"unsupported (version|platform|os)",
        r"requires (x64|arm64|windows|macos)",
        r"not supported on",
        r"wrong architecture",
        r"platform (not )?supported",
    ]

    TIMEOUT_PATTERNS = [
        r"timed? ?out",
        r"timeout",
        r"took too long",
        r"did not respond",
        r"hung",
    ]

    def analyze(
        self,
        tool_key: str,
        exit_code: int,
        stdout: str = "",
        stderr: str = "",
        error_message: Optional[str] = None,
    ) -> FailureAnalysis:
        """
        Analyze a failure and produce a classification.

        Args:
            tool_key: Tool identifier
            exit_code: Process exit code
            stdout: Standard output
            stderr: Standard error
            error_message: Additional error context

        Returns:
            FailureAnalysis with classification and repair suggestions
        """
        combined = f"{stdout}\n{stderr}\n{error_message or ''}".lower()

        # Check patterns in priority order
        checks = [
            (self.PERMISSION_PATTERNS, FailureCategory.PERMISSION, self._analyze_permission),
            (self.NETWORK_PATTERNS, FailureCategory.NETWORK, self._analyze_network),
            (self.DISK_PATTERNS, FailureCategory.DISK_SPACE, self._analyze_disk),
            (self.DEPENDENCY_PATTERNS, FailureCategory.DEPENDENCY, self._analyze_dependency),
            (self.CORRUPTION_PATTERNS, FailureCategory.CORRUPTION, self._analyze_corruption),
            (self.COMPATIBILITY_PATTERNS, FailureCategory.COMPATIBILITY, self._analyze_compatibility),
            (self.TIMEOUT_PATTERNS, FailureCategory.TIMEOUT, self._analyze_timeout),
        ]

        best_match = None
        best_confidence = 0.0

        for patterns, category, analyzer in checks:
            confidence = self._match_patterns(combined, patterns)
            if confidence > best_confidence:
                best_confidence = confidence
                best_match = (category, analyzer)

        # Check exit code patterns
        if best_confidence < 0.5:
            exit_code_analysis = self._analyze_exit_code(exit_code)
            if exit_code_analysis:
                category, confidence, reason = exit_code_analysis
                if confidence > best_confidence:
                    best_confidence = confidence
                    best_match = (category, lambda tk, ec, so, se, em: FailureAnalysis(
                        tool_key=tk,
                        failure_category=category,
                        recoverable=self._is_recoverable(category),
                        confidence=confidence,
                        reason=reason,
                        repair_suggestions=self._get_suggestions(category, tk),
                    ))

        if best_match and best_confidence >= 0.3:
            category, analyzer = best_match
            return analyzer(tool_key, exit_code, stdout, stderr, error_message)

        # Default: unknown failure
        return FailureAnalysis(
            tool_key=tool_key,
            failure_category=FailureCategory.UNKNOWN,
            recoverable=True,
            confidence=0.3,
            reason=f"Unknown failure (exit code {exit_code})",
            repair_suggestions=[
                f"Check {tool_key} installation manually",
                "Review the error output above for details",
                "Try running the installer manually to see the full error",
            ],
            details={
                "exit_code": exit_code,
                "stderr_preview": (stderr or "")[:300],
            },
        )

    def _match_patterns(self, text: str, patterns: List[str]) -> float:
        """Match text against patterns and return confidence score."""
        matches = 0
        for pattern in patterns:
            if re.search(pattern, text, re.IGNORECASE):
                matches += 1

        if matches == 0:
            return 0.0

        # Confidence based on number of matches
        # A single match is enough for high confidence if it's a good pattern
        if matches >= 3:
            return 0.95
        elif matches >= 2:
            return 0.85
        elif matches >= 1:
            return 0.75
        return 0.0

    def _analyze_exit_code(self, exit_code: int) -> Optional[Tuple[FailureCategory, float, str]]:
        """Analyze exit code for failure classification."""
        if exit_code == -1:
            return (FailureCategory.TIMEOUT, 0.8, "Command timed out")
        elif exit_code == -2:
            return (FailureCategory.DEPENDENCY, 0.9, "Command not found")
        elif exit_code == -3:
            return (FailureCategory.UNKNOWN, 0.5, "Execution error")
        elif exit_code == 5:
            return (FailureCategory.PERMISSION, 0.7, "Access denied (exit code 5)")
        elif exit_code == 9009:
            return (FailureCategory.DEPENDENCY, 0.8, "Command not recognized (exit code 9009)")
        return None

    def _analyze_permission(self, tool_key, exit_code, stdout, stderr, error_message) -> FailureAnalysis:
        return FailureAnalysis(
            tool_key=tool_key,
            failure_category=FailureCategory.PERMISSION,
            recoverable=True,
            confidence=0.85,
            reason="Permission denied - requires elevated privileges",
            repair_suggestions=[
                "Run the deployment with administrator privileges",
                "Right-click and select 'Run as Administrator'",
                "Check if the installation directory requires admin access",
            ],
            requires_admin=True,
            details={"exit_code": exit_code},
        )

    def _analyze_network(self, tool_key, exit_code, stdout, stderr, error_message) -> FailureAnalysis:
        return FailureAnalysis(
            tool_key=tool_key,
            failure_category=FailureCategory.NETWORK,
            recoverable=True,
            confidence=0.8,
            reason="Network connectivity issue detected",
            repair_suggestions=[
                "Check your internet connection",
                "Verify the download URL is accessible",
                "Try again later - the server may be temporarily unavailable",
                "Check if a firewall or proxy is blocking the connection",
            ],
            requires_network=True,
            details={"exit_code": exit_code},
        )

    def _analyze_disk(self, tool_key, exit_code, stdout, stderr, error_message) -> FailureAnalysis:
        return FailureAnalysis(
            tool_key=tool_key,
            failure_category=FailureCategory.DISK_SPACE,
            recoverable=False,
            confidence=0.9,
            reason="Insufficient disk space",
            repair_suggestions=[
                "Free up disk space before retrying",
                "Check disk usage and remove unnecessary files",
                "Consider installing to a different drive with more space",
            ],
            requires_disk_space=True,
            details={"exit_code": exit_code},
        )

    def _analyze_dependency(self, tool_key, exit_code, stdout, stderr, error_message) -> FailureAnalysis:
        # Try to extract the missing dependency name
        missing_dep = None
        combined = f"{stdout}\n{stderr}\n{error_message or ''}"
        dep_match = re.search(r"(?:requires|missing|not found|not recognized)[:\s]+([\w.-]+)", combined, re.IGNORECASE)
        if dep_match:
            missing_dep = dep_match.group(1)

        suggestions = [
            f"Ensure all prerequisites for {tool_key} are installed",
            "Check the tool's documentation for system requirements",
        ]
        if missing_dep:
            suggestions.insert(0, f"Install the missing dependency: {missing_dep}")

        return FailureAnalysis(
            tool_key=tool_key,
            failure_category=FailureCategory.DEPENDENCY,
            recoverable=True,
            confidence=0.85,
            reason=f"Missing dependency: {missing_dep or 'unknown'}",
            repair_suggestions=suggestions,
            requires_dependency=missing_dep,
            details={"exit_code": exit_code, "missing_dependency": missing_dep},
        )

    def _analyze_corruption(self, tool_key, exit_code, stdout, stderr, error_message) -> FailureAnalysis:
        return FailureAnalysis(
            tool_key=tool_key,
            failure_category=FailureCategory.CORRUPTION,
            recoverable=True,
            confidence=0.8,
            reason="Downloaded or installed file appears corrupted",
            repair_suggestions=[
                "Clear download cache and retry",
                "Check disk for errors",
                "The download may have been interrupted - retry with a stable connection",
            ],
            details={"exit_code": exit_code},
        )

    def _analyze_compatibility(self, tool_key, exit_code, stdout, stderr, error_message) -> FailureAnalysis:
        return FailureAnalysis(
            tool_key=tool_key,
            failure_category=FailureCategory.COMPATIBILITY,
            recoverable=False,
            confidence=0.85,
            reason="Tool is not compatible with this system",
            repair_suggestions=[
                "Check if the tool supports your operating system version",
                "Verify your system architecture (x64/arm64) is supported",
                "Look for an alternative version of the tool",
            ],
            details={"exit_code": exit_code},
        )

    def _analyze_timeout(self, tool_key, exit_code, stdout, stderr, error_message) -> FailureAnalysis:
        return FailureAnalysis(
            tool_key=tool_key,
            failure_category=FailureCategory.TIMEOUT,
            recoverable=True,
            confidence=0.75,
            reason="Operation timed out",
            repair_suggestions=[
                "The operation took too long and was cancelled",
                "Try again with a longer timeout setting",
                "Check if the system is under heavy load",
                "The download server may be slow - try again later",
            ],
            details={"exit_code": exit_code},
        )

    def _is_recoverable(self, category: FailureCategory) -> bool:
        """Determine if a failure category is recoverable."""
        non_recoverable = {
            FailureCategory.DISK_SPACE,
            FailureCategory.COMPATIBILITY,
        }
        return category not in non_recoverable

    def _get_suggestions(self, category: FailureCategory, tool_key: str) -> List[str]:
        """Get default repair suggestions for a failure category."""
        suggestions = {
            FailureCategory.PERMISSION: [
                "Run with administrator privileges",
                "Check file/folder permissions",
            ],
            FailureCategory.NETWORK: [
                "Check internet connection",
                "Verify download URLs are accessible",
            ],
            FailureCategory.DISK_SPACE: [
                "Free up disk space before retrying",
            ],
            FailureCategory.DEPENDENCY: [
                f"Install missing dependencies for {tool_key}",
            ],
            FailureCategory.CORRUPTION: [
                "Clear cache and retry download",
            ],
            FailureCategory.COMPATIBILITY: [
                f"Check system requirements for {tool_key}",
            ],
            FailureCategory.TIMEOUT: [
                "Increase timeout and retry",
            ],
            FailureCategory.UNKNOWN: [
                f"Review error output for {tool_key}",
                "Try manual installation",
            ],
        }
        return suggestions.get(category, ["Review error output and try again"])
