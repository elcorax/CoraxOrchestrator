"""
Corax Orchestrator - RuntimeLifecycle (DEPRECATED).

⚠️ DEPRECATED: Use CoraxRuntimeKernel instead.
This module is kept for backward compatibility and delegates to the kernel.

The kernel is the SINGLE authoritative runtime authority. All startup flows
converge through CoraxRuntimeKernel. This module wraps the kernel to provide
the old RuntimeLifecycle API for existing consumers.
"""

import warnings
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from src.runtime.kernel import CoraxRuntimeKernel, KernelResult
from src.runtime.state import StartupStateMachine, RuntimePhase, StartupState


@dataclass
class LifecycleResult:
    """Result of the complete startup lifecycle (DEPRECATED - use KernelResult)."""

    success: bool = False
    state_machine_summary: Dict[str, Any] = field(default_factory=dict)
    bootstrap_result: Optional[Dict[str, Any]] = None
    recovery_result: Optional[Dict[str, Any]] = None
    diagnostic_report: Optional[Dict[str, Any]] = None
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    total_duration_seconds: float = 0.0
    initialized_components: List[str] = field(default_factory=list)
    failed_components: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "state_machine_summary": self.state_machine_summary,
            "bootstrap_result": self.bootstrap_result,
            "recovery_result": self.recovery_result,
            "diagnostic_report": self.diagnostic_report,
            "errors": self.errors,
            "warnings": self.warnings,
            "total_duration_seconds": round(self.total_duration_seconds, 2),
            "initialized_components": self.initialized_components,
            "failed_components": self.failed_components,
        }


class RuntimeLifecycle:
    """
    RuntimeLifecycle (DEPRECATED).

    ⚠️ This class is deprecated. Use CoraxRuntimeKernel instead.
    This wrapper delegates all functionality to the kernel for backward
    compatibility with existing consumers.
    """

    def __init__(self, project_root: Optional[str] = None):
        warnings.warn(
            "RuntimeLifecycle is deprecated. Use CoraxRuntimeKernel instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        self._kernel = CoraxRuntimeKernel(project_root)

    @property
    def state_machine(self) -> StartupStateMachine:
        return self._kernel.state_machine

    @property
    def diagnostics(self) -> Any:
        return self._kernel.diagnostics

    @property
    def is_ready(self) -> bool:
        return self._kernel.is_ready

    def run(self) -> LifecycleResult:
        """Run startup lifecycle via kernel (DEPRECATED)."""
        kernel_result = self._kernel.start()
        return self._kernel_to_lifecycle(kernel_result)

    def _kernel_to_lifecycle(self, kr: KernelResult) -> LifecycleResult:
        """Convert KernelResult to LifecycleResult for backward compat."""
        return LifecycleResult(
            success=kr.success,
            state_machine_summary=kr.state_machine_summary,
            bootstrap_result=kr.bootstrap_result,
            recovery_result=kr.recovery_result,
            diagnostic_report=kr.diagnostic_report,
            errors=kr.errors,
            warnings=kr.warnings,
            total_duration_seconds=kr.total_duration_seconds,
            initialized_components=kr.initialized_components,
            failed_components=kr.failed_components,
        )
