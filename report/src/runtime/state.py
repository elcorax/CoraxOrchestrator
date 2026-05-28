"""
Corax Orchestrator - Startup State Machine.

Provides deterministic startup state management with defined states,
runtime phases, startup checkpoints, and failure state transitions.
The runtime always knows where startup failed, what initialized
successfully, and what recovery actions are possible.
"""

from typing import Dict, List, Optional, Set
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum, auto


class StartupState(Enum):
    """Deterministic startup states for the runtime lifecycle."""

    # Pre-startup
    UNINITIALIZED = auto()
    BOOTSTRAPPING = auto()

    # Validation
    VALIDATING = auto()
    VALIDATION_FAILED = auto()
    VALIDATION_PASSED = auto()

    # Self-repair
    SELF_REPAIRING = auto()
    SELF_REPAIR_FAILED = auto()
    SELF_REPAIR_PASSED = auto()

    # Configuration
    LOADING_CONFIG = auto()
    CONFIG_LOAD_FAILED = auto()
    CONFIG_LOADED = auto()

    # Logging
    INIT_LOGGING = auto()
    LOGGING_FAILED = auto()
    LOGGING_READY = auto()

    # State initialization
    INIT_STATE = auto()
    STATE_INIT_FAILED = auto()
    STATE_READY = auto()

    # Execution engine
    INIT_EXECUTION = auto()
    EXECUTION_FAILED = auto()
    EXECUTION_READY = auto()

    # Deployment engine
    INIT_DEPLOYMENT = auto()
    DEPLOYMENT_FAILED = auto()
    DEPLOYMENT_READY = auto()

    # AI stack
    INIT_AI_STACK = auto()
    AI_STACK_FAILED = auto()
    AI_STACK_READY = auto()

    # Reporting
    INIT_REPORTING = auto()
    REPORTING_FAILED = auto()
    REPORTING_READY = auto()

    # Ready
    READY = auto()

    # Failure
    FATAL = auto()
    RECOVERING = auto()
    RECOVERY_FAILED = auto()
    RECOVERED = auto()


class RuntimePhase(Enum):
    """High-level runtime phases for tracking startup progress."""

    BOOTSTRAP = "bootstrap"
    VALIDATE = "validate"
    SELF_REPAIR = "self_repair"
    LOAD_CONFIG = "load_config"
    INIT_LOGGING = "init_logging"
    INIT_STATE = "init_state"
    INIT_EXECUTION = "init_execution"
    INIT_DEPLOYMENT = "init_deployment"
    INIT_AI_STACK = "init_ai_stack"
    INIT_REPORTING = "init_reporting"
    READY = "ready"
    FAILED = "failed"
    RECOVERING = "recovering"


@dataclass
class StartupCheckpoint:
    """A checkpoint in the startup lifecycle with timing and status."""

    phase: RuntimePhase
    state: StartupState
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    duration_ms: float = 0.0
    success: bool = False
    error: Optional[str] = None
    recovery_attempted: bool = False
    recovery_success: bool = False

    def to_dict(self) -> Dict:
        return {
            "phase": self.phase.value,
            "state": self.state.name,
            "timestamp": self.timestamp,
            "duration_ms": round(self.duration_ms, 2),
            "success": self.success,
            "error": self.error,
            "recovery_attempted": self.recovery_attempted,
            "recovery_success": self.recovery_success,
        }


class StartupStateMachine:
    """
    Deterministic startup state machine.

    Tracks every state transition, records checkpoints, and provides
    full observability into where startup succeeded or failed.
    """

    def __init__(self):
        self._current_state: StartupState = StartupState.UNINITIALIZED
        self._previous_state: Optional[StartupState] = None
        self._checkpoints: List[StartupCheckpoint] = []
        self._phase_timers: Dict[RuntimePhase, datetime] = {}
        self._initialized_components: Set[str] = set()
        self._failed_components: Set[str] = set()
        self._recovery_actions: List[str] = []
        self._start_time: datetime = datetime.now(timezone.utc)

    @property
    def current_state(self) -> StartupState:
        return self._current_state

    @property
    def current_phase(self) -> RuntimePhase:
        """Derive the current runtime phase from state."""
        phase_map = {
            StartupState.UNINITIALIZED: RuntimePhase.BOOTSTRAP,
            StartupState.BOOTSTRAPPING: RuntimePhase.BOOTSTRAP,
            StartupState.VALIDATING: RuntimePhase.VALIDATE,
            StartupState.VALIDATION_FAILED: RuntimePhase.VALIDATE,
            StartupState.VALIDATION_PASSED: RuntimePhase.VALIDATE,
            StartupState.SELF_REPAIRING: RuntimePhase.SELF_REPAIR,
            StartupState.SELF_REPAIR_FAILED: RuntimePhase.SELF_REPAIR,
            StartupState.SELF_REPAIR_PASSED: RuntimePhase.SELF_REPAIR,
            StartupState.LOADING_CONFIG: RuntimePhase.LOAD_CONFIG,
            StartupState.CONFIG_LOAD_FAILED: RuntimePhase.LOAD_CONFIG,
            StartupState.CONFIG_LOADED: RuntimePhase.LOAD_CONFIG,
            StartupState.INIT_LOGGING: RuntimePhase.INIT_LOGGING,
            StartupState.LOGGING_FAILED: RuntimePhase.INIT_LOGGING,
            StartupState.LOGGING_READY: RuntimePhase.INIT_LOGGING,
            StartupState.INIT_STATE: RuntimePhase.INIT_STATE,
            StartupState.STATE_INIT_FAILED: RuntimePhase.INIT_STATE,
            StartupState.STATE_READY: RuntimePhase.INIT_STATE,
            StartupState.INIT_EXECUTION: RuntimePhase.INIT_EXECUTION,
            StartupState.EXECUTION_FAILED: RuntimePhase.INIT_EXECUTION,
            StartupState.EXECUTION_READY: RuntimePhase.INIT_EXECUTION,
            StartupState.INIT_DEPLOYMENT: RuntimePhase.INIT_DEPLOYMENT,
            StartupState.DEPLOYMENT_FAILED: RuntimePhase.INIT_DEPLOYMENT,
            StartupState.DEPLOYMENT_READY: RuntimePhase.INIT_DEPLOYMENT,
            StartupState.INIT_AI_STACK: RuntimePhase.INIT_AI_STACK,
            StartupState.AI_STACK_FAILED: RuntimePhase.INIT_AI_STACK,
            StartupState.AI_STACK_READY: RuntimePhase.INIT_AI_STACK,
            StartupState.INIT_REPORTING: RuntimePhase.INIT_REPORTING,
            StartupState.REPORTING_FAILED: RuntimePhase.INIT_REPORTING,
            StartupState.REPORTING_READY: RuntimePhase.INIT_REPORTING,
            StartupState.READY: RuntimePhase.READY,
            StartupState.FATAL: RuntimePhase.FAILED,
            StartupState.RECOVERING: RuntimePhase.RECOVERING,
            StartupState.RECOVERY_FAILED: RuntimePhase.FAILED,
            StartupState.RECOVERED: RuntimePhase.READY,
        }
        return phase_map.get(self._current_state, RuntimePhase.BOOTSTRAP)

    @property
    def is_running(self) -> bool:
        """Check if startup is still in progress."""
        return self._current_state not in (
            StartupState.READY,
            StartupState.FATAL,
            StartupState.RECOVERY_FAILED,
        )

    @property
    def is_ready(self) -> bool:
        """Check if runtime is fully initialized."""
        return self._current_state == StartupState.READY

    @property
    def has_failed(self) -> bool:
        """Check if startup has failed."""
        return self._current_state in (
            StartupState.FATAL,
            StartupState.RECOVERY_FAILED,
        )

    def transition_to(self, new_state: StartupState) -> None:
        """
        Transition to a new state and record a checkpoint.

        Args:
            new_state: The target state to transition to.
        """
        self._previous_state = self._current_state
        self._current_state = new_state

    def start_phase(self, phase: RuntimePhase) -> None:
        """Start timing a runtime phase."""
        self._phase_timers[phase] = datetime.now(timezone.utc)

    def end_phase(
        self,
        phase: RuntimePhase,
        state: StartupState,
        success: bool,
        error: Optional[str] = None,
    ) -> StartupCheckpoint:
        """
        End a runtime phase and record a checkpoint.

        Args:
            phase: The phase that completed.
            state: The state at phase completion.
            success: Whether the phase succeeded.
            error: Optional error message if failed.

        Returns:
            The recorded checkpoint.
        """
        start = self._phase_timers.pop(phase, self._start_time)
        duration_ms = (datetime.now(timezone.utc) - start).total_seconds() * 1000

        checkpoint = StartupCheckpoint(
            phase=phase,
            state=state,
            duration_ms=duration_ms,
            success=success,
            error=error,
        )
        self._checkpoints.append(checkpoint)
        self._current_state = state

        if success:
            self._initialized_components.add(phase.value)
        else:
            self._failed_components.add(phase.value)

        return checkpoint

    def record_recovery(self, action: str, success: bool) -> None:
        """Record a recovery action taken during startup."""
        self._recovery_actions.append(
            f"{'✅' if success else '❌'} {action}"
        )

    def mark_component_initialized(self, component: str) -> None:
        """Mark a component as successfully initialized."""
        self._initialized_components.add(component)

    def mark_component_failed(self, component: str) -> None:
        """Mark a component as failed to initialize."""
        self._failed_components.add(component)

    def get_checkpoints(self) -> List[StartupCheckpoint]:
        """Get all recorded checkpoints."""
        return list(self._checkpoints)

    def get_summary(self) -> Dict:
        """Get a summary of the startup state machine."""
        total_duration = (
            datetime.now(timezone.utc) - self._start_time
        ).total_seconds()

        return {
            "current_state": self._current_state.name,
            "current_phase": self.current_phase.value,
            "is_ready": self.is_ready,
            "has_failed": self.has_failed,
            "total_duration_seconds": round(total_duration, 2),
            "initialized_components": sorted(self._initialized_components),
            "failed_components": sorted(self._failed_components),
            "recovery_actions": self._recovery_actions,
            "checkpoints": [c.to_dict() for c in self._checkpoints],
        }

    def get_failure_point(self) -> Optional[StartupCheckpoint]:
        """Get the checkpoint where startup failed, if any."""
        for checkpoint in reversed(self._checkpoints):
            if not checkpoint.success:
                return checkpoint
        return None

    def get_recovery_suggestions(self) -> List[str]:
        """Get suggested recovery actions based on failure state."""
        suggestions = []
        failure = self.get_failure_point()
        if failure is None:
            return suggestions

        phase_suggestions = {
            RuntimePhase.BOOTSTRAP: [
                "Ensure Python 3.10+ is installed",
                "Verify virtual environment is activated",
                "Run: python -m venv .venv && .venv\\Scripts\\activate",
            ],
            RuntimePhase.VALIDATE: [
                "Check requirements.txt exists",
                "Run: pip install -r requirements.txt",
                "Verify all dependencies are installed",
            ],
            RuntimePhase.SELF_REPAIR: [
                "Run: pip install --upgrade pip",
                "Run: pip install -r requirements.txt --force-reinstall",
                "Check for conflicting package versions",
            ],
            RuntimePhase.LOAD_CONFIG: [
                "Verify config/default.yaml exists",
                "Check YAML syntax in config file",
                "Ensure config directory is accessible",
            ],
            RuntimePhase.INIT_LOGGING: [
                "Check data/logs directory permissions",
                "Verify logging configuration is valid",
            ],
            RuntimePhase.INIT_STATE: [
                "Check data/persistence directory",
                "Verify state file is not corrupted",
            ],
            RuntimePhase.INIT_EXECUTION: [
                "Check deployment/execution module imports",
                "Verify all capability modules are present",
            ],
            RuntimePhase.INIT_DEPLOYMENT: [
                "Check deployment module imports",
                "Verify installer modules are present",
            ],
            RuntimePhase.INIT_AI_STACK: [
                "Check AI stack module imports",
                "Verify AI installer modules are present",
                "Run: pip install -r requirements.txt",
            ],
            RuntimePhase.INIT_REPORTING: [
                "Check reporting module imports",
                "Verify data/reports directory exists",
            ],
        }

        return phase_suggestions.get(failure.phase, [
            "Check application logs for details",
            "Verify all dependencies are installed",
            "Try restarting the application",
        ])
