"""
Corax Orchestrator - RuntimeLifecycle (DEPRECATED).

⚠️ DEPRECATED: Use CoraxRuntimeKernel instead.
This module is kept for backward compatibility and delegates to the kernel.

The kernel is the SINGLE authoritative runtime authority. All startup flows
converge through CoraxRuntimeKernel. This module wraps the kernel to provide
the old RuntimeLifecycle API for existing consumers.

Survivability: _MEIPASS safe, graceful degradation under frozen execution.
"""

import sys
import warnings
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path


def _is_frozen() -> bool:
    """Detect if running as a PyInstaller executable."""
    return getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS")


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
    frozen_detected: bool = False

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
            "frozen_detected": self.frozen_detected,
        }


class RuntimeLifecycle:
    """
    RuntimeLifecycle (DEPRECATED).

    ⚠️ This class is deprecated. Use CoraxRuntimeKernel instead.
    This wrapper delegates all functionality to the kernel for backward
    compatibility with existing consumers.

    Survivability: Gracefully degrades if kernel unavailable or frozen.
    """

    def __init__(self, project_root: Optional[str] = None):
        self._frozen = _is_frozen()
        self._kernel = None
        self._initialized = False

        if not self._frozen:
            warnings.warn(
                "RuntimeLifecycle is deprecated. Use CoraxRuntimeKernel instead.",
                DeprecationWarning,
                stacklevel=2,
            )
            try:
                from src.runtime.kernel import CoraxRuntimeKernel
                self._kernel = CoraxRuntimeKernel(project_root)
                self._initialized = True
            except Exception as e:
                self._kernel = None
                self._initialized = False
        else:
            # Frozen executable: kernel initialization is best-effort
            try:
                from src.runtime.kernel import CoraxRuntimeKernel
                self._kernel = CoraxRuntimeKernel(project_root)
                self._initialized = True
            except Exception:
                self._kernel = None
                self._initialized = False

    @property
    def state_machine(self) -> Any:
        if self._kernel and self._initialized:
            return self._kernel.state_machine
        return None

    @property
    def diagnostics(self) -> Any:
        if self._kernel and self._initialized:
            return self._kernel.diagnostics
        return None

    @property
    def is_ready(self) -> bool:
        return self._initialized and (self._kernel.is_ready if self._kernel else False)

    def run(self) -> LifecycleResult:
        """Run startup lifecycle via kernel (DEPRECATED)."""
        if not self._kernel or not self._initialized:
            return LifecycleResult(
                success=False,
                errors=["RuntimeLifecycle kernel not available"],
                frozen_detected=self._frozen,
            )
        try:
            kernel_result = self._kernel.start()
            return self._kernel_to_lifecycle(kernel_result)
        except Exception as e:
            return LifecycleResult(
                success=False,
                errors=[f"RuntimeLifecycle run failed: {e}"],
                frozen_detected=self._frozen,
            )

    def _kernel_to_lifecycle(self, kr: Any) -> LifecycleResult:
        """Convert KernelResult to LifecycleResult for backward compat."""
        try:
            return LifecycleResult(
                success=getattr(kr, "success", False),
                state_machine_summary=getattr(kr, "state_machine_summary", {}),
                bootstrap_result=getattr(kr, "bootstrap_result", None),
                recovery_result=getattr(kr, "recovery_result", None),
                diagnostic_report=getattr(kr, "diagnostic_report", None),
                errors=getattr(kr, "errors", []),
                warnings=getattr(kr, "warnings", []),
                total_duration_seconds=getattr(kr, "total_duration_seconds", 0.0),
                initialized_components=getattr(kr, "initialized_components", []),
                failed_components=getattr(kr, "failed_components", []),
                frozen_detected=self._frozen,
            )
        except Exception:
            return LifecycleResult(
                success=False,
                errors=["Failed to convert kernel result"],
                frozen_detected=self._frozen,
            )
