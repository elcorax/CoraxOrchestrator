"""
Corax Orchestrator - Centralized UI State Manager.

Provides a single source of truth for all UI state across panels,
enabling real-time synchronization between the runtime kernel,
deployment engines, and all GUI components.

This is the bridge between the async runtime and the Qt event loop.
"""

from typing import Optional, Dict, Any, List, Callable
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
import time


class UIStatePhase(Enum):
    """Operational phases visible in the UI."""
    IDLE = "idle"
    SCANNING = "scanning"
    ANALYZING = "analyzing"
    DEPLOYING = "deploying"
    INSTALLING = "installing"
    CONFIGURING = "configuring"
    PULLING_MODELS = "pulling_models"
    VERIFYING = "verifying"
    REPAIRING = "repairing"
    PAUSED = "paused"
    CANCELLED = "cancelled"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class OperationInfo:
    """Information about a single operation visible in the UI."""
    operation_id: str = ""
    tool_name: str = ""
    phase: str = ""
    status: str = "pending"
    progress_percent: float = 0.0
    elapsed_seconds: float = 0.0
    estimated_remaining_seconds: float = 0.0
    current_command: str = ""
    retry_count: int = 0
    max_retries: int = 3
    error: str = ""
    started_at: Optional[float] = None


@dataclass
class RetryQueueItem:
    """A retry queue item visible in the UI."""
    tool_name: str = ""
    retry_count: int = 0
    max_retries: int = 3
    last_error: str = ""
    next_retry_at: Optional[float] = None
    cooldown_seconds: int = 0


@dataclass
class RepairActivity:
    """A repair activity visible in the UI."""
    component: str = ""
    action: str = ""
    status: str = "pending"
    message: str = ""
    timestamp: float = 0.0


class UIStateManager:
    """
    Centralized UI state manager.

    All GUI panels read from this single source of truth.
    The runtime kernel and deployment engines write to it.
    Qt timers poll it for updates.

    This eliminates fragmented state and ensures all panels
    show consistent, real-time information.
    """

    def __init__(self):
        self._phase = UIStatePhase.IDLE
        self._phase_start_time: Optional[float] = None
        self._runtime_status = "Unknown"
        self._deployment_status = "Not Started"
        self._ai_stack_status = "Not Deployed"
        self._system_health = "Unknown"

        # Active operations
        self._active_operations: Dict[str, OperationInfo] = {}
        self._operation_history: List[OperationInfo] = []

        # Queues
        self._retry_queue: List[RetryQueueItem] = []
        self._failure_queue: List[str] = []
        self._repair_activities: List[RepairActivity] = []

        # Deployment summary
        self._tools_total = 0
        self._tools_installed = 0
        self._tools_failed = 0
        self._tools_skipped = 0
        self._models_pulled: List[str] = []
        self._deployment_start_time: Optional[float] = None
        self._deployment_elapsed: float = 0.0
        self._estimated_remaining: float = 0.0

        # Callbacks for state changes
        self._on_state_change: List[Callable[[], None]] = []

        # Tool selection state (set by ToolSelectionPanel, read by DeploymentControlPanel)
        self._selected_tools: List[str] = []
        self._selected_models: List[str] = []

        # Scan results
        self._last_scan_result: Optional[Dict[str, Any]] = None

    # ─── Phase Management ─────────────────────────────────────────────────

    @property
    def phase(self) -> UIStatePhase:
        return self._phase

    @phase.setter
    def phase(self, value: UIStatePhase) -> None:
        self._phase = value
        self._phase_start_time = time.time()
        self._notify()

    def full_reset(self) -> None:
        """Reset all state to initial values for a fresh deployment."""
        self._phase = UIStatePhase.IDLE
        self._phase_start_time = None
        self._runtime_status = "Starting"
        self._deployment_status = "Not Started"
        self._ai_stack_status = "Not Deployed"
        self._system_health = "Unknown"
        self._active_operations.clear()
        self._operation_history.clear()
        self._retry_queue.clear()
        self._failure_queue.clear()
        self._repair_activities.clear()
        self._tools_total = 0
        self._tools_installed = 0
        self._tools_failed = 0
        self._tools_skipped = 0
        self._models_pulled.clear()
        self._deployment_start_time = None
        self._deployment_elapsed = 0.0
        self._estimated_remaining = 0.0
        self._last_scan_result = None
        self._notify()


    @property
    def phase_elapsed(self) -> float:
        if self._phase_start_time:
            return time.time() - self._phase_start_time
        return 0.0

    # ─── Status Properties ────────────────────────────────────────────────

    @property
    def runtime_status(self) -> str:
        return self._runtime_status

    @runtime_status.setter
    def runtime_status(self, value: str) -> None:
        self._runtime_status = value
        self._notify()

    @property
    def deployment_status(self) -> str:
        return self._deployment_status

    @deployment_status.setter
    def deployment_status(self, value: str) -> None:
        self._deployment_status = value
        self._notify()

    @property
    def ai_stack_status(self) -> str:
        return self._ai_stack_status

    @ai_stack_status.setter
    def ai_stack_status(self, value: str) -> None:
        self._ai_stack_status = value
        self._notify()

    @property
    def system_health(self) -> str:
        return self._system_health

    @system_health.setter
    def system_health(self, value: str) -> None:
        self._system_health = value
        self._notify()

    # ─── Operation Management ─────────────────────────────────────────────

    def start_operation(self, operation_id: str, tool_name: str) -> None:
        """Register a new active operation."""
        op = OperationInfo(
            operation_id=operation_id,
            tool_name=tool_name,
            status="running",
            started_at=time.time(),
        )
        self._active_operations[operation_id] = op
        self._notify()

    def update_operation(
        self,
        operation_id: str,
        progress_percent: Optional[float] = None,
        phase: Optional[str] = None,
        current_command: Optional[str] = None,
        retry_count: Optional[int] = None,
        error: Optional[str] = None,
    ) -> None:
        """Update an active operation's progress."""
        op = self._active_operations.get(operation_id)
        if not op:
            return
        if progress_percent is not None:
            op.progress_percent = progress_percent
        if phase is not None:
            op.phase = phase
        if current_command is not None:
            op.current_command = current_command
        if retry_count is not None:
            op.retry_count = retry_count
        if error is not None:
            op.error = error
        if op.started_at:
            op.elapsed_seconds = time.time() - op.started_at
        self._notify()

    def complete_operation(
        self, operation_id: str, status: str = "completed"
    ) -> None:
        """Mark an operation as complete and archive it."""
        op = self._active_operations.pop(operation_id, None)
        if op:
            op.status = status
            if op.started_at:
                op.elapsed_seconds = time.time() - op.started_at
            self._operation_history.append(op)
            if len(self._operation_history) > 100:
                self._operation_history = self._operation_history[-100:]
            self._notify()

    def get_active_operations(self) -> List[OperationInfo]:
        """Get all currently active operations with updated elapsed times."""
        now = time.time()
        for op in self._active_operations.values():
            if op.started_at:
                op.elapsed_seconds = now - op.started_at
        return list(self._active_operations.values())

    def get_operation_history(self) -> List[OperationInfo]:
        """Get completed operation history."""
        return list(self._operation_history)

    # ─── Queue Management ─────────────────────────────────────────────────

    def add_to_retry_queue(
        self,
        tool_name: str,
        retry_count: int,
        max_retries: int,
        last_error: str,
        cooldown_seconds: int = 5,
    ) -> None:
        """Add an item to the retry queue."""
        item = RetryQueueItem(
            tool_name=tool_name,
            retry_count=retry_count,
            max_retries=max_retries,
            last_error=last_error,
            next_retry_at=time.time() + cooldown_seconds,
            cooldown_seconds=cooldown_seconds,
        )
        self._retry_queue.append(item)
        self._notify()

    def remove_from_retry_queue(self, tool_name: str) -> None:
        """Remove an item from the retry queue."""
        self._retry_queue = [
            r for r in self._retry_queue if r.tool_name != tool_name
        ]
        self._notify()

    def get_retry_queue(self) -> List[RetryQueueItem]:
        """Get the current retry queue."""
        return list(self._retry_queue)

    def add_to_failure_queue(self, tool_name: str) -> None:
        """Add a tool to the failure queue."""
        if tool_name not in self._failure_queue:
            self._failure_queue.append(tool_name)
            self._notify()

    def get_failure_queue(self) -> List[str]:
        """Get the current failure queue."""
        return list(self._failure_queue)

    # ─── Repair Activity ──────────────────────────────────────────────────

    def add_repair_activity(
        self,
        component: str,
        action: str,
        status: str = "running",
        message: str = "",
    ) -> None:
        """Record a repair activity."""
        activity = RepairActivity(
            component=component,
            action=action,
            status=status,
            message=message,
            timestamp=time.time(),
        )
        self._repair_activities.insert(0, activity)
        if len(self._repair_activities) > 50:
            self._repair_activities = self._repair_activities[:50]
        self._notify()

    def get_repair_activities(self) -> List[RepairActivity]:
        """Get recent repair activities."""
        return list(self._repair_activities)

    # ─── Deployment Summary ───────────────────────────────────────────────

    def set_deployment_summary(
        self,
        total: int = 0,
        installed: int = 0,
        failed: int = 0,
        skipped: int = 0,
    ) -> None:
        """Update the deployment summary counts."""
        self._tools_total = total
        self._tools_installed = installed
        self._tools_failed = failed
        self._tools_skipped = skipped
        self._notify()

    @property
    def tools_total(self) -> int:
        return self._tools_total

    @property
    def tools_installed(self) -> int:
        return self._tools_installed

    @property
    def tools_failed(self) -> int:
        return self._tools_failed

    @property
    def tools_skipped(self) -> int:
        return self._tools_skipped

    def add_model_pulled(self, model_name: str) -> None:
        """Record a pulled model."""
        if model_name not in self._models_pulled:
            self._models_pulled.append(model_name)
            self._notify()

    @property
    def models_pulled(self) -> List[str]:
        return list(self._models_pulled)

    # ─── Deployment Timing ────────────────────────────────────────────────

    def start_deployment_timer(self) -> None:
        """Start the deployment elapsed timer."""
        self._deployment_start_time = time.time()
        self._notify()

    def update_estimated_remaining(self, seconds: float) -> None:
        """Update estimated remaining time."""
        self._estimated_remaining = seconds
        self._notify()

    @property
    def deployment_elapsed(self) -> float:
        """Get elapsed deployment time in seconds."""
        if self._deployment_start_time:
            return time.time() - self._deployment_start_time
        return self._deployment_elapsed

    @property
    def estimated_remaining(self) -> float:
        return self._estimated_remaining

    # ─── Scan Results ─────────────────────────────────────────────────────

    def set_scan_result(self, result: Dict[str, Any]) -> None:
        """Store the latest scan result."""
        self._last_scan_result = result
        self._notify()

    @property
    def last_scan_result(self) -> Optional[Dict[str, Any]]:
        return self._last_scan_result

    # ─── State Change Notifications ───────────────────────────────────────

    def on_state_change(self, callback: Callable[[], None]) -> None:
        """Register a callback for state changes."""
        self._on_state_change.append(callback)

    def _notify(self) -> None:
        """Notify all registered callbacks of state change."""
        for cb in self._on_state_change:
            try:
                cb()
            except Exception:
                pass

    # ─── Snapshot ─────────────────────────────────────────────────────────

    def get_snapshot(self) -> Dict[str, Any]:
        """Get a complete snapshot of current UI state."""
        return {
            "phase": self._phase.value,
            "phase_elapsed": self.phase_elapsed,
            "runtime_status": self._runtime_status,
            "deployment_status": self._deployment_status,
            "ai_stack_status": self._ai_stack_status,
            "system_health": self._system_health,
            "active_operations": [
                {
                    "operation_id": op.operation_id,
                    "tool_name": op.tool_name,
                    "phase": op.phase,
                    "status": op.status,
                    "progress_percent": op.progress_percent,
                    "elapsed_seconds": round(op.elapsed_seconds, 1),
                    "estimated_remaining_seconds": round(op.estimated_remaining_seconds, 1),
                    "current_command": op.current_command,
                    "retry_count": op.retry_count,
                    "max_retries": op.max_retries,
                    "error": op.error,
                }
                for op in self.get_active_operations()
            ],
            "retry_queue": [
                {
                    "tool_name": r.tool_name,
                    "retry_count": r.retry_count,
                    "max_retries": r.max_retries,
                    "last_error": r.last_error,
                    "cooldown_seconds": r.cooldown_seconds,
                }
                for r in self._retry_queue
            ],
            "failure_queue": list(self._failure_queue),
            "repair_activities": [
                {
                    "component": r.component,
                    "action": r.action,
                    "status": r.status,
                    "message": r.message,
                }
                for r in self._repair_activities[:10]
            ],
            "deployment": {
                "total": self._tools_total,
                "installed": self._tools_installed,
                "failed": self._tools_failed,
                "skipped": self._tools_skipped,
                "elapsed_seconds": round(self.deployment_elapsed, 1),
                "estimated_remaining_seconds": round(self._estimated_remaining, 1),
                "models_pulled": self._models_pulled,
            },
        }


# Global singleton instance
ui_state = UIStateManager()
