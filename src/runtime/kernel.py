"""
Corax Orchestrator - CoraxRuntimeKernel.

SINGLE authoritative runtime kernel that consolidates ALL startup flows
into one lifecycle, one state machine, and one runtime authority.

Eliminates fragmented startup behavior. All initialization converges into:

    BOOTSTRAP → VALIDATE_ENVIRONMENT → VALIDATE_RUNTIME → REPAIR_RUNTIME
    → LOAD_CONFIG → INIT_LOGGING → INIT_STATE → INIT_EXECUTION
    → INIT_DEPLOYMENT → INIT_AI_STACK → INIT_REPORTING → READY

The kernel owns:
- startup lifecycle (deterministic ordering)
- configuration loading
- runtime validation
- dependency validation
- self-healing initialization
- diagnostics initialization
- execution engine startup
- deployment engine startup
- AI stack initialization
- reporting startup
- graceful shutdown
"""

from typing import Any, Dict, List, Optional, Set, Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
import os
import platform
import signal
import sys
import traceback
from pathlib import Path

from src.runtime.state import (
    StartupState,
    RuntimePhase,
    StartupCheckpoint,
    StartupStateMachine,
)
from src.runtime.bootstrap import BootstrapRuntime, BootstrapResult
from src.runtime.recovery import StartupRecovery, RecoveryResult
from src.runtime.diagnostics import RuntimeDiagnostics, RuntimeDiagnosticReport
from src.runtime.bridge import runtime_bridge
from src.runtime.state_bus import state_bus, EventType, EventPriority


@dataclass
class KernelResult:

    """Result of the complete kernel startup lifecycle."""

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
    shutdown_clean: bool = False
    restart_count: int = 0

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
            "shutdown_clean": self.shutdown_clean,
            "restart_count": self.restart_count,
        }


class CoraxRuntimeKernel:
    """
    SINGLE authoritative runtime kernel for Corax Orchestrator.

    Owns the complete startup lifecycle with deterministic phase ordering,
    state tracking, self-healing, comprehensive diagnostics, and graceful
    shutdown. All initialization flows converge through this kernel.

    Startup flow:
        BOOTSTRAP → VALIDATE_ENVIRONMENT → VALIDATE_RUNTIME → REPAIR_RUNTIME
        → LOAD_CONFIG → INIT_LOGGING → INIT_STATE → INIT_EXECUTION
        → INIT_DEPLOYMENT → INIT_AI_STACK → INIT_REPORTING → READY

    Usage:
        kernel = CoraxRuntimeKernel()
        result = kernel.start()
        if result.success:
            # Runtime is ready
            kernel.execution_engine  # Access initialized components
            kernel.deployment_engine
            kernel.ai_stack_deployer
        kernel.shutdown()  # Graceful shutdown
    """

    def __init__(self, project_root: Optional[str] = None):
        self._project_root = Path(project_root or os.getcwd())
        self._state_machine = StartupStateMachine()
        self._bootstrap = BootstrapRuntime(str(self._project_root))
        self._recovery = StartupRecovery(str(self._project_root))
        self._diagnostics = RuntimeDiagnostics(str(self._project_root))
        self._start_time = datetime.now(timezone.utc)
        self._shutdown_hooks: List[Callable[[], None]] = []
        self._shutdown_initiated = False
        self._restart_count = 0

        # M41: Phase attempt tracking to bound retries
        self._phase_attempts: Dict[str, int] = {}

        # Bridge connection
        runtime_bridge.bind_kernel(self)

        # Initialized components (populated during startup)
        self._config: Any = None
        self._logger: Any = None
        self._execution_engine: Any = None
        self._deployment_engine: Any = None
        self._ai_stack_deployer: Any = None
        self._reporting: Any = None

        # Register signal handlers for graceful shutdown
        self._register_signal_handlers()

    # ─── Public Properties ───────────────────────────────────────────────

    @property
    def state_machine(self) -> StartupStateMachine:
        """Get the startup state machine."""
        return self._state_machine

    @property
    def diagnostics(self) -> RuntimeDiagnostics:
        """Get the runtime diagnostics system."""
        return self._diagnostics

    @property
    def is_ready(self) -> bool:
        """Check if the kernel has completed startup."""
        return self._state_machine.is_ready

    @property
    def is_running(self) -> bool:
        """Check if the kernel is still starting up."""
        return self._state_machine.is_running

    @property
    def has_failed(self) -> bool:
        """Check if the kernel startup has failed."""
        return self._state_machine.has_failed

    @property
    def config(self) -> Any:
        """Get the loaded configuration."""
        return self._config

    @property
    def execution_engine(self) -> Any:
        """Get the initialized execution engine."""
        return self._execution_engine

    @property
    def deployment_engine(self) -> Any:
        """Get the initialized deployment engine."""
        return self._deployment_engine

    @property
    def ai_stack_deployer(self) -> Any:
        """Get the initialized AI stack deployer."""
        return self._ai_stack_deployer

    @property
    def reporting(self) -> Any:
        """Get the initialized reporting engine."""
        return self._reporting

    @property
    def project_root(self) -> Path:
        """Get the project root path."""
        return self._project_root

    @property
    def bridge(self) -> Any:
        """Get the runtime bridge."""
        return runtime_bridge

    @property
    def restart_count(self) -> int:
        """Get the number of restarts (startup cycles)."""
        return self._restart_count

    # ─── Public API ──────────────────────────────────────────────────────

    def start(self) -> KernelResult:
        """
        Start the complete runtime kernel lifecycle.

        Runs all startup phases in deterministic order with self-healing
        and comprehensive diagnostics. Pushes live state to the GUI bridge.

        Survivability (M41):
        - Startup state validation guards prevent re-entry
        - Bounded bootstrap retry (max 3 attempts per phase)
        - Stale startup-state cleanup before initialization
        - Interrupted startup recovery via lock detection
        - Deterministic sequencing with no recovery loops

        Returns:
            KernelResult with full startup diagnostics.
        """
        result = KernelResult()
        runtime_bridge.push_health_status("runtime", "Starting")

        # ── M41: Startup state validation guards ───────────────────────
        # Prevent re-entering startup if already initialized
        if self._state_machine.is_ready:
            result.warnings.append("Startup already completed, skipping re-entry")
            result.success = True
            return result

        # Prevent startup if currently shutting down
        if self._shutdown_initiated:
            result.errors.append("Cannot start: shutdown already initiated")
            return result

        # Start RuntimeStateBus for event-driven convergence
        try:
            import asyncio
            state_bus.start()
        except Exception:
            pass

        # ── M41: Lock file survivability check ────────────────────
        # Validate no stale startup lock before proceeding
        stale_lock = self._bootstrap.detect_interrupted_shutdown()
        if stale_lock:
            result.warnings.append(
                "Stale startup lock detected and cleared before initialization"
            )
            self._diagnostics.record_recovery("Stale startup lock cleared pre-init")

        try:
            # ── M41: Safe bootstrap retry behavior ─────────────────────
            # Track max attempts per phase to prevent infinite recovery loops

            # Phase 1: Bootstrap (with startup-state hardening)
            self._run_bootstrap_phase(result)

            # Phase 2: Validate environment
            if self._state_machine.is_running:
                self._run_validate_environment_phase(result)

            # Phase 3: Validate runtime
            if self._state_machine.is_running:
                self._run_validate_runtime_phase(result)

            # Phase 4: Repair runtime (if validation failed, bounded retry)
            if self._state_machine.has_failed:
                self._run_repair_runtime_phase(result)

            # Phase 5: Load config (survivable: can continue without config)
            if self._state_machine.is_running:
                self._run_load_config_phase(result)

            # Phase 6: Init logging
            if self._state_machine.is_running:
                self._run_init_logging_phase(result)

            # Phase 7: Init state
            if self._state_machine.is_running:
                self._run_init_state_phase(result)

            # Phase 8: Init execution engine
            if self._state_machine.is_running:
                self._run_init_execution_phase(result)

            # Phase 9: Init deployment engine
            if self._state_machine.is_running:
                self._run_init_deployment_phase(result)

            # Phase 10: Init AI stack
            if self._state_machine.is_running:
                self._run_init_ai_stack_phase(result)

            # Phase 11: Init reporting
            if self._state_machine.is_running:
                self._run_init_reporting_phase(result)

            # Phase 12: Ready
            if self._state_machine.is_running:
                self._finalize_ready(result)

            # ── M41: Partial initialization fallback ───────────────────
            # If not all components initialized but kernel is running,
            # still mark as partially successful (degraded startup)
            if not result.success and not self._state_machine.has_failed:
                initialized = self._state_machine.get_summary().get("initialized_components", [])
                if initialized:
                    result.warnings.append(
                        f"Partial startup: {len(initialized)} components initialized"
                    )
                    result.success = True  # Degraded but operational

        except Exception as e:
            self._state_machine.transition_to(StartupState.FATAL)
            error_msg = f"Unhandled kernel exception: {e}"
            result.errors.append(error_msg)
            self._diagnostics.record_error("kernel", error_msg)
            self._diagnostics.capture_crash()

        # Finalize
        total_duration = (
            datetime.now(timezone.utc) - self._start_time
        ).total_seconds()
        result.total_duration_seconds = total_duration
        result.state_machine_summary = self._state_machine.get_summary()
        sm_summary = self._state_machine.get_summary()
        result.initialized_components = sorted(
            sm_summary.get("initialized_components", [])
        )
        result.failed_components = sorted(
            sm_summary.get("failed_components", [])
        )

        # Push kernel state to the GUI bridge
        runtime_bridge.push_kernel_state(result)

        # Save diagnostics
        report = self._diagnostics.finalize(result.success)
        result.diagnostic_report = report.to_dict()
        self._diagnostics.save_report()

        # Start the bridge background sync loop
        if result.success:
            try:
                import asyncio
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    asyncio.ensure_future(runtime_bridge.start_bridge_loop())
            except RuntimeError:
                pass

        return result

    def shutdown(self) -> KernelResult:
        """
        Graceful shutdown of the runtime kernel.

        Runs shutdown hooks in reverse initialization order, ensuring
        clean teardown of all initialized components.
        """
        if self._shutdown_initiated:
            return KernelResult(success=True, shutdown_clean=True)

        self._shutdown_initiated = True
        result = KernelResult()
        result.success = True

        # Stop the bridge
        runtime_bridge.stop_bridge()

        # Stop RuntimeStateBus (with bounded cleanup)
        try:
            state_bus.stop()
        except Exception:
            pass

        try:
            # Run shutdown hooks in reverse order
            for hook in reversed(self._shutdown_hooks):
                try:
                    hook()
                except Exception as e:
                    result.warnings.append(f"Shutdown hook failed: {e}")

            result.shutdown_clean = True
        except Exception as e:
            result.errors.append(f"Shutdown failed: {e}")
            result.shutdown_clean = False

        return result

    def register_shutdown_hook(self, hook: Callable[[], None]) -> None:
        """Register a shutdown hook to be called during graceful shutdown."""
        self._shutdown_hooks.append(hook)

    def get_failure_point(self) -> Optional[StartupCheckpoint]:
        """Get the checkpoint where startup failed, if any."""
        return self._state_machine.get_failure_point()

    def get_recovery_suggestions(self) -> List[str]:
        """Get suggested recovery actions based on failure state."""
        return self._state_machine.get_recovery_suggestions()

    # ─── Phase Implementations ───────────────────────────────────────────

    def _run_bootstrap_phase(self, result: KernelResult) -> None:
        """Phase 1: Bootstrap runtime environment with startup-state hardening."""
        self._state_machine.transition_to(StartupState.BOOTSTRAPPING)
        self._state_machine.start_phase(RuntimePhase.BOOTSTRAP)
        self._diagnostics.start_phase("bootstrap")

        # ── M41: Bounded retry guard ───────────────────────────────────
        phase_name = "bootstrap"
        self._phase_attempts[phase_name] = self._phase_attempts.get(phase_name, 0)
        if self._phase_attempts[phase_name] >= 3:
            self._diagnostics.record_recovery(
                "Bootstrap retry exhausted, skipping bootstrap phase"
            )
            result.warnings.append("Bootstrap retry exhausted (max 3)")
            return
        self._phase_attempts[phase_name] += 1

        # ── Startup-state consistency hardening (M41) ──────────────────
        # 1. Detect corrupted startup-state from previous interrupted run
        corrupted_state = self._bootstrap.get_previous_init_phase()
        if corrupted_state:
            self._diagnostics.record_recovery(
                f"Detected corrupted startup state from phase: {corrupted_state}"
            )
            result.warnings.append(
                f"Previous startup interrupted during '{corrupted_state}' phase; "
                f"stale state discarded"
            )

        # 2. Detect interrupted shutdown from previous run
        interrupted = self._bootstrap.detect_interrupted_shutdown()
        if interrupted:
            self._diagnostics.record_recovery(
                "Interrupted shutdown detected, cleaning stale state"
            )
            result.warnings.append("Previous run was interrupted; stale state cleaned")

        # 3. Clean stale temp, lock, partial-init marker, persistence state files
        self._bootstrap.cleanup_stale_temp()

        # 4. Create startup lock for THIS run
        self._bootstrap.create_startup_lock()

        # 5. Create startup state marker for consistency tracking
        self._bootstrap.create_startup_state_marker("bootstrap")

        # 6. Register shutdown hook to remove lock and marker on clean exit
        self.register_shutdown_hook(
            lambda: self._bootstrap.remove_startup_lock()
        )
        self.register_shutdown_hook(
            lambda: self._bootstrap.remove_startup_state_marker()
        )

        # ── Run bootstrap validation ───────────────────────────────────
        bootstrap_result = self._bootstrap.run()
        result.bootstrap_result = bootstrap_result.to_dict()

        if bootstrap_result.success:
            self._state_machine.end_phase(
                RuntimePhase.BOOTSTRAP,
                StartupState.BOOTSTRAPPING,
                success=True,
            )
            self._diagnostics.end_phase("bootstrap", "success")
            for repair in bootstrap_result.repairs_made:
                result.warnings.append(f"Bootstrap repair: {repair}")
                self._diagnostics.record_recovery(repair)
        else:
            error_msg = "Bootstrap failed"
            self._state_machine.end_phase(
                RuntimePhase.BOOTSTRAP,
                StartupState.VALIDATION_FAILED,
                success=False,
                error=error_msg,
            )
            result.errors.append(error_msg)
            self._diagnostics.end_phase(
                "bootstrap", "failed", errors=[error_msg]
            )
            self._diagnostics.record_recovery(
                "Bootstrap failed, attempting self-repair"
            )

    def _run_validate_environment_phase(
        self, result: KernelResult
    ) -> None:
        """Phase 2: Validate runtime environment."""
        self._state_machine.transition_to(StartupState.VALIDATING)
        self._state_machine.start_phase(RuntimePhase.VALIDATE)
        self._diagnostics.start_phase("validate_environment")

        validation = self._bootstrap.validate_environment()

        if validation["success"]:
            self._state_machine.end_phase(
                RuntimePhase.VALIDATE,
                StartupState.VALIDATION_PASSED,
                success=True,
            )
            self._state_machine.mark_component_initialized("environment")
            self._diagnostics.end_phase("validate_environment", "success")
        else:
            errors = validation.get("errors", [])
            self._state_machine.end_phase(
                RuntimePhase.VALIDATE,
                StartupState.VALIDATION_FAILED,
                success=False,
                error="; ".join(errors) if errors else "Environment validation failed",
            )
            result.errors.extend(errors)
            self._diagnostics.end_phase(
                "validate_environment", "failed", errors=errors
            )

    def _run_validate_runtime_phase(self, result: KernelResult) -> None:
        """Phase 3: Validate runtime dependencies and modules."""
        self._state_machine.start_phase(RuntimePhase.VALIDATE)
        self._diagnostics.start_phase("validate_runtime")

        src_dir = self._project_root / "src"
        main_py = src_dir / "main.py"
        runtime_dir = src_dir / "runtime"

        structure_ok = all([
            src_dir.exists(),
            main_py.exists(),
            runtime_dir.exists(),
        ])

        if structure_ok:
            self._state_machine.mark_component_initialized("runtime_structure")
            self._diagnostics.end_phase("validate_runtime", "success")
        else:
            missing = []
            if not src_dir.exists():
                missing.append("src/")
            if not main_py.exists():
                missing.append("src/main.py")
            if not runtime_dir.exists():
                missing.append("src/runtime/")

            error_msg = f"Missing project structure: {', '.join(missing)}"
            result.errors.append(error_msg)
            self._diagnostics.end_phase(
                "validate_runtime", "failed", errors=[error_msg]
            )

    def _run_repair_runtime_phase(self, result: KernelResult) -> None:
        """Phase 4: Repair runtime issues."""
        runtime_bridge.push_recovery_activity(
            "kernel", "self_repair", "running",
            "Attempting runtime self-repair"
        )
        self._state_machine.transition_to(StartupState.SELF_REPAIRING)
        self._state_machine.start_phase(RuntimePhase.SELF_REPAIR)
        self._diagnostics.start_phase("repair_runtime")

        # ── M41: Bounded repair retry guard ────────────────────────────
        phase_name = "repair"
        self._phase_attempts[phase_name] = self._phase_attempts.get(phase_name, 0)
        if self._phase_attempts[phase_name] >= 2:
            result.warnings.append("Repair retry exhausted (max 2), proceeding degraded")
            self._state_machine.end_phase(
                RuntimePhase.SELF_REPAIR,
                StartupState.SELF_REPAIR_FAILED,
                success=False,
                error="Repair retries exhausted",
            )
            runtime_bridge.push_recovery_activity(
                "kernel", "self_repair", "exhausted",
                "Repair retries exhausted, proceeding degraded"
            )
            return
        self._phase_attempts[phase_name] += 1

        recovery_result = self._recovery.repair_all()
        result.recovery_result = recovery_result.to_dict()

        if recovery_result.success:
            self._state_machine.end_phase(
                RuntimePhase.SELF_REPAIR,
                StartupState.SELF_REPAIR_PASSED,
                success=True,
            )
            self._state_machine.mark_component_initialized("self_repair")
            self._diagnostics.end_phase("repair_runtime", "success")
            runtime_bridge.push_recovery_activity(
                "kernel", "self_repair", "completed",
                "Runtime self-repair succeeded"
            )
        else:
            self._state_machine.end_phase(
                RuntimePhase.SELF_REPAIR,
                StartupState.SELF_REPAIR_FAILED,
                success=False,
                error="Self-repair could not resolve all issues",
            )
            result.errors.extend(recovery_result.errors)
            self._diagnostics.end_phase(
                "repair_runtime", "failed", errors=recovery_result.errors
            )
            runtime_bridge.push_recovery_activity(
                "kernel", "self_repair", "failed",
                "Self-repair could not resolve all issues"
            )

    def _run_load_config_phase(self, result: KernelResult) -> None:
        """Phase 5: Load configuration."""
        self._state_machine.transition_to(StartupState.LOADING_CONFIG)
        self._state_machine.start_phase(RuntimePhase.LOAD_CONFIG)
        self._diagnostics.start_phase("load_config")

        # Update startup state marker
        self._bootstrap.create_startup_state_marker("load_config")

        try:
            sys.path.insert(0, str(self._project_root))

            # Survivability: validate config module import
            from src.core.config import load_config

            config_path = self._project_root / "config" / "corax.yaml"
            self._config = load_config(
                config_path if config_path.exists() else None
            )
            self._state_machine.end_phase(
                RuntimePhase.LOAD_CONFIG,
                StartupState.CONFIG_LOADED,
                success=True,
            )
            self._state_machine.mark_component_initialized("config")
            self._diagnostics.end_phase("load_config", "success")
        except Exception as e:
            error_msg = f"Config load failed: {e}"
            self._state_machine.end_phase(
                RuntimePhase.LOAD_CONFIG,
                StartupState.CONFIG_LOAD_FAILED,
                success=False,
                error=error_msg,
            )
            result.warnings.append(error_msg)
            self._diagnostics.end_phase(
                "load_config", "failed", errors=[error_msg]
            )

    def _run_init_logging_phase(self, result: KernelResult) -> None:
        """Phase 6: Initialize logging system."""
        self._state_machine.transition_to(StartupState.INIT_LOGGING)
        self._state_machine.start_phase(RuntimePhase.INIT_LOGGING)
        self._diagnostics.start_phase("init_logging")

        # Update startup state marker
        self._bootstrap.create_startup_state_marker("init_logging")

        try:
            sys.path.insert(0, str(self._project_root))
            from src.core.logging import setup_logging

            self._logger = setup_logging()
            self._state_machine.end_phase(
                RuntimePhase.INIT_LOGGING,
                StartupState.LOGGING_READY,
                success=True,
            )
            self._state_machine.mark_component_initialized("logging")
            self._diagnostics.end_phase("init_logging", "success")
        except Exception as e:
            error_msg = f"Logging init failed: {e}"
            self._state_machine.end_phase(
                RuntimePhase.INIT_LOGGING,
                StartupState.LOGGING_FAILED,
                success=False,
                error=error_msg,
            )
            result.warnings.append(error_msg)
            self._diagnostics.end_phase(
                "init_logging", "failed", errors=[error_msg]
            )

    def _run_init_state_phase(self, result: KernelResult) -> None:
        """Phase 7: Initialize runtime state."""
        self._state_machine.transition_to(StartupState.INIT_STATE)
        self._state_machine.start_phase(RuntimePhase.INIT_STATE)
        self._diagnostics.start_phase("init_state")

        # Update startup state marker
        self._bootstrap.create_startup_state_marker("init_state")

        try:
            dirs = [
                self._project_root / "data",
                self._project_root / "data" / "logs",
                self._project_root / "data" / "models",
                self._project_root / "data" / "persistence",
                self._project_root / "data" / "reports",
            ]
            for d in dirs:
                d.mkdir(parents=True, exist_ok=True)

            self._state_machine.end_phase(
                RuntimePhase.INIT_STATE,
                StartupState.STATE_READY,
                success=True,
            )
            self._state_machine.mark_component_initialized("state")
            self._diagnostics.end_phase("init_state", "success")
        except Exception as e:
            error_msg = f"State init failed: {e}"
            self._state_machine.end_phase(
                RuntimePhase.INIT_STATE,
                StartupState.STATE_INIT_FAILED,
                success=False,
                error=error_msg,
            )
            result.warnings.append(error_msg)
            self._diagnostics.end_phase(
                "init_state", "failed", errors=[error_msg]
            )

    def _run_init_execution_phase(self, result: KernelResult) -> None:
        """Phase 8: Initialize execution engine."""
        self._state_machine.transition_to(StartupState.INIT_EXECUTION)
        self._state_machine.start_phase(RuntimePhase.INIT_EXECUTION)
        self._diagnostics.start_phase("init_execution")

        # Update startup state marker
        self._bootstrap.create_startup_state_marker("init_execution")

        try:
            sys.path.insert(0, str(self._project_root))
            from src.deployment.execution.executor import DeploymentExecutor

            self._execution_engine = DeploymentExecutor()
            runtime_bridge.bind_deployment_orchestrator(self._execution_engine)
            self._state_machine.end_phase(
                RuntimePhase.INIT_EXECUTION,
                StartupState.EXECUTION_READY,
                success=True,
            )
            self._state_machine.mark_component_initialized("execution")
            self._diagnostics.end_phase("init_execution", "success")
        except Exception as e:
            error_msg = f"Execution engine init failed: {e}"
            self._state_machine.end_phase(
                RuntimePhase.INIT_EXECUTION,
                StartupState.EXECUTION_FAILED,
                success=False,
                error=error_msg,
            )
            result.warnings.append(error_msg)
            self._diagnostics.end_phase(
                "init_execution", "failed", errors=[error_msg]
            )

    def _run_init_deployment_phase(self, result: KernelResult) -> None:
        """Phase 9: Initialize deployment engine."""
        self._state_machine.transition_to(StartupState.INIT_DEPLOYMENT)
        self._state_machine.start_phase(RuntimePhase.INIT_DEPLOYMENT)
        self._diagnostics.start_phase("init_deployment")

        # Update startup state marker
        self._bootstrap.create_startup_state_marker("init_deployment")

        try:
            sys.path.insert(0, str(self._project_root))
            from src.deployment.orchestrator import DeploymentOrchestrator
            from src.deployment.autonomous import autonomous_deployer

            self._deployment_engine = DeploymentOrchestrator()
            runtime_bridge.bind_deployment_orchestrator(self._deployment_engine)

            # Wire orchestrator to autonomous deployer
            autonomous_deployer.set_orchestrator(self._deployment_engine)
            import logging as _logging
            _logging.getLogger(__name__).info(
                "Deployment orchestrator wired to autonomous deployer"
            )

            self._state_machine.end_phase(
                RuntimePhase.INIT_DEPLOYMENT,
                StartupState.DEPLOYMENT_READY,
                success=True,
            )
            self._state_machine.mark_component_initialized("deployment")
            self._diagnostics.end_phase("init_deployment", "success")
        except Exception as e:
            error_msg = f"Deployment engine init failed: {e}"
            self._state_machine.end_phase(
                RuntimePhase.INIT_DEPLOYMENT,
                StartupState.DEPLOYMENT_FAILED,
                success=False,
                error=error_msg,
            )
            result.warnings.append(error_msg)
            self._diagnostics.end_phase(
                "init_deployment", "failed", errors=[error_msg]
            )

    def _run_init_ai_stack_phase(self, result: KernelResult) -> None:
        """Phase 10: Initialize AI stack deployer."""
        self._state_machine.transition_to(StartupState.INIT_AI_STACK)
        self._state_machine.start_phase(RuntimePhase.INIT_AI_STACK)
        self._diagnostics.start_phase("init_ai_stack")

        # Update startup state marker
        self._bootstrap.create_startup_state_marker("init_ai_stack")

        try:
            sys.path.insert(0, str(self._project_root))
            from src.deployment.ai_stack import AIStackDeployer

            self._ai_stack_deployer = AIStackDeployer()
            self._state_machine.end_phase(
                RuntimePhase.INIT_AI_STACK,
                StartupState.AI_STACK_READY,
                success=True,
            )
            self._state_machine.mark_component_initialized("ai_stack")
            self._diagnostics.end_phase("init_ai_stack", "success")
        except Exception as e:
            error_msg = f"AI stack init failed: {e}"
            self._state_machine.end_phase(
                RuntimePhase.INIT_AI_STACK,
                StartupState.AI_STACK_FAILED,
                success=False,
                error=error_msg,
            )
            result.warnings.append(error_msg)
            self._diagnostics.end_phase(
                "init_ai_stack", "failed", errors=[error_msg]
            )

    def _run_init_reporting_phase(self, result: KernelResult) -> None:
        """Phase 11: Initialize reporting system."""
        self._state_machine.transition_to(StartupState.INIT_REPORTING)
        self._state_machine.start_phase(RuntimePhase.INIT_REPORTING)
        self._diagnostics.start_phase("init_reporting")

        # Update startup state marker
        self._bootstrap.create_startup_state_marker("init_reporting")

        try:
            sys.path.insert(0, str(self._project_root))
            from src.modules.reporting import ReportingEngine

            self._reporting = ReportingEngine()
            self._state_machine.end_phase(
                RuntimePhase.INIT_REPORTING,
                StartupState.REPORTING_READY,
                success=True,
            )
            self._state_machine.mark_component_initialized("reporting")
            self._diagnostics.end_phase("init_reporting", "success")
        except Exception as e:
            error_msg = f"Reporting init failed: {e}"
            self._state_machine.end_phase(
                RuntimePhase.INIT_REPORTING,
                StartupState.REPORTING_FAILED,
                success=False,
                error=error_msg,
            )
            result.warnings.append(error_msg)
            self._diagnostics.end_phase(
                "init_reporting", "failed", errors=[error_msg]
            )

    def _finalize_ready(self, result: KernelResult) -> None:
        """Finalize: Mark runtime as ready with cleanup."""
        self._state_machine.transition_to(StartupState.READY)
        self._state_machine.end_phase(
            RuntimePhase.READY,
            StartupState.READY,
            success=True,
        )
        self._state_machine.mark_component_initialized("ready")
        result.success = True

        # Remove startup state marker on clean completion
        self._bootstrap.remove_startup_state_marker()

    # ─── Signal Handling ─────────────────────────────────────────────────

    def _register_signal_handlers(self) -> None:
        """Register signal handlers for graceful shutdown."""
        try:
            signal.signal(signal.SIGINT, self._handle_signal)
            signal.signal(signal.SIGTERM, self._handle_signal)
        except (ValueError, AttributeError):
            pass

    def _handle_signal(self, signum: int, frame: Any) -> None:
        """Handle OS signals for graceful shutdown."""
        try:
            signal_name = signal.Signals(signum).name
        except (ValueError, AttributeError):
            signal_name = f"signal_{signum}"
        self._diagnostics.record_warning(
            f"Received signal {signal_name}, initiating shutdown"
        )
        self.shutdown()
