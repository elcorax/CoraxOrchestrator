"""
Corax Orchestrator - Runtime Bridge.

THE authoritative bridge between the CoraxRuntimeKernel and all GUI panels.
Provides real-time state push, progress synchronization, operation visibility,
retry/repair visibility, and deployment state persistence.

Architecture:
    Kernel -> RuntimeBridge -> UIStateManager -> All GUI Panels
    DeploymentEngine -> RuntimeBridge -> UIStateManager -> All GUI Panels
    RecoveryEngine -> RuntimeBridge -> UIStateManager -> All GUI Panels
    RuntimeStateBus -> RuntimeBridge -> UIStateManager -> All GUI Panels

Now integrated with RuntimeStateBus for event-driven convergence.
"""

from typing import Optional, Dict, Any, List, Callable
from datetime import datetime, timezone
import asyncio
import json
import os
import time
from pathlib import Path

from src.core.logging import get_logger
from src.runtime.state_bus import (
    state_bus,
    BusEvent,
    EventType,
    EventSubscriber,
    EventPriority,
)


logger = get_logger(__name__)


class BridgeSubscriber(EventSubscriber):
    """
    Subscribes to RuntimeStateBus events and propagates them
    to UIStateManager for real-time GUI updates.

    This is the SINGLE bridge between event-driven runtime
    and the Qt-based UIStateManager that all panels read from.
    """

    def __init__(self, bridge: "RuntimeBridge"):
        super().__init__("bridge_subscriber")
        self._bridge = bridge
        self._lazy_ui_state = None

    def _get_ui(self):
        if self._lazy_ui_state is None:
            from src.gui.ui_state import ui_state
            self._lazy_ui_state = ui_state
        return self._lazy_ui_state

    def subscribe_to_all(self) -> None:
        """Subscribe to all event types for full UI propagation."""
        self.subscribe_to(
            EventType.KERNEL_READY,
            EventType.KERNEL_STARTING,
            EventType.KERNEL_FAILED,
            EventType.KERNEL_SHUTDOWN,
            EventType.DEPLOYMENT_STARTED,
            EventType.DEPLOYMENT_PHASE,
            EventType.DEPLOYMENT_PROGRESS,
            EventType.DEPLOYMENT_TOOL_STARTED,
            EventType.DEPLOYMENT_TOOL_COMPLETED,
            EventType.DEPLOYMENT_TOOL_FAILED,
            EventType.DEPLOYMENT_COMPLETED,
            EventType.RECOVERY_STARTED,
            EventType.RECOVERY_ACTIVITY,
            EventType.RECOVERY_COMPLETED,
            EventType.RECOVERY_FAILED,
            EventType.HEALTH_STATUS_CHANGE,
            EventType.COMPONENT_STATUS,
            EventType.ERROR_OCCURRED,
            EventType.WARNING_ISSUED,
            EventType.MODEL_PROGRESS,
            EventType.MODEL_COMPLETED,
            EventType.PHASE_CHANGE,
            EventType.STATE_TRANSITION,
        )

    def on_event_sync(self, event: BusEvent) -> None:
        """Propagate bus events to UIStateManager."""
        ui = self._get_ui()

        if event.event_type == EventType.KERNEL_READY:
            ui.runtime_status = "Ready"
            ui.system_health = "OK"

        elif event.event_type == EventType.KERNEL_STARTING:
            ui.runtime_status = "Starting"

        elif event.event_type == EventType.KERNEL_FAILED:
            ui.runtime_status = "Failed"
            ui.system_health = "Degraded"

        elif event.event_type == EventType.KERNEL_SHUTDOWN:
            ui.runtime_status = "Shutdown"

        elif event.event_type == EventType.DEPLOYMENT_STARTED:
            ui.phase = self._get_phase().DEPLOYING
            ui.deployment_status = "Running"
            total = event.payload.get("total_tools", 0)
            ui.set_deployment_summary(total=total, installed=0, failed=0, skipped=0)
            ui.start_deployment_timer()

        elif event.event_type == EventType.DEPLOYMENT_PHASE:
            phase_name = event.payload.get("phase_name", "")
            phase_num = event.payload.get("phase_number", 0)
            total = event.payload.get("total_phases", 0)
            ui.deployment_status = f"Phase {phase_num}/{total}: {phase_name}"

        elif event.event_type == EventType.DEPLOYMENT_PROGRESS:
            pct = event.payload.get("progress_percent", 0)
            tool = event.payload.get("tool_name", "")
            if tool:
                ui.start_operation(f"deploy_{tool}", tool)
                ui.update_operation(
                    f"deploy_{tool}",
                    progress_percent=pct,
                    phase=event.payload.get("current_step", ""),
                    current_command=event.payload.get("command", ""),
                    retry_count=event.payload.get("retry_count", 0),
                )

        elif event.event_type == EventType.DEPLOYMENT_TOOL_COMPLETED:
            tool = event.payload.get("tool_name", "")
            ui.complete_operation(f"deploy_{tool}", "completed")
            ui.add_repair_activity(tool, "deploy", "completed", f"{tool} deployed successfully")

        elif event.event_type == EventType.DEPLOYMENT_TOOL_FAILED:
            tool = event.payload.get("tool_name", "")
            ui.complete_operation(f"deploy_{tool}", "failed")
            ui.add_to_failure_queue(tool)
            ui.add_repair_activity(tool, "deploy", "failed",
                                   event.payload.get("error", "Deployment failed"))

        elif event.event_type == EventType.DEPLOYMENT_COMPLETED:
            ui.deployment_status = "Completed"
            ui.phase = self._get_phase().COMPLETED

        elif event.event_type == EventType.RECOVERY_STARTED:
            ui.system_health = "Repairing"
            ui.phase = self._get_phase().REPAIRING

        elif event.event_type == EventType.RECOVERY_ACTIVITY:
            ui.add_repair_activity(
                component=event.payload.get("component", "system"),
                action=event.payload.get("action", "repair"),
                status=event.payload.get("status", "running"),
                message=event.payload.get("message", ""),
            )

        elif event.event_type == EventType.RECOVERY_COMPLETED:
            ui.system_health = "OK"

        elif event.event_type == EventType.RECOVERY_FAILED:
            ui.system_health = "Degraded"

        elif event.event_type == EventType.HEALTH_STATUS_CHANGE:
            comp = event.payload.get("component", "system")
            status = event.payload.get("status", "unknown")
            if comp == "system":
                ui.system_health = status

        elif event.event_type == EventType.COMPONENT_STATUS:
            pass  # Handled by health broadcaster

        elif event.event_type == EventType.ERROR_OCCURRED:
            comp = event.payload.get("component", "system")
            ui.add_repair_activity(
                component=comp, action="error",
                status="failed", message=event.payload.get("message", "Unknown error")
            )

        elif event.event_type == EventType.MODEL_PROGRESS:
            model = event.payload.get("model_name", "")
            pct = event.payload.get("progress_percent", 0)
            op_id = f"model_{model}"
            ui.start_operation(op_id, f"model:{model}")
            ui.update_operation(op_id, progress_percent=pct, phase="Downloading model")

        elif event.event_type == EventType.MODEL_COMPLETED:
            model = event.payload.get("model_name", "")
            ui.complete_operation(f"model_{model}", "completed")
            ui.add_model_pulled(model)

        elif event.event_type == EventType.PHASE_CHANGE:
            phase_str = event.payload.get("phase", "")
            ui.phase = self._phase_from_string(phase_str) or ui.phase

        # Always update deployment summary from any deployment event
        if "tool_name" in event.payload and event.event_type.value.startswith("deployment"):
            br = self._bridge
            ui.set_deployment_summary(
                total=ui.tools_total,
                installed=ui.tools_installed + (1 if event.event_type == EventType.DEPLOYMENT_TOOL_COMPLETED else 0),
                failed=ui.tools_failed + (1 if event.event_type == EventType.DEPLOYMENT_TOOL_FAILED else 0),
                skipped=ui.tools_skipped,
            )

    async def on_event(self, event: BusEvent) -> None:
        """Async handler mirrors sync."""
        self.on_event_sync(event)

    def _get_phase(self):
        from src.gui.ui_state import UIStatePhase
        return UIStatePhase

    def _phase_from_string(self, phase_str: str):
        mapping = {
            "idle": self._get_phase().IDLE,
            "deploying": self._get_phase().DEPLOYING,
            "pulling": self._get_phase().PULLING_MODELS,
            "verifying": self._get_phase().VERIFYING,
            "repairing": self._get_phase().REPAIRING,
            "completed": self._get_phase().COMPLETED,
            "failed": self._get_phase().FAILED,
            "paused": self._get_phase().PAUSED,
            "cancelled": self._get_phase().CANCELLED,
        }
        return mapping.get(phase_str.lower())


class RuntimeBridge:
    """
    Bridges the runtime kernel, deployment engine, and recovery engine
    with the centralized UI state manager.
    """

    def __init__(self, kernel: Any = None):
        self._kernel = kernel
        self._deployment_orchestrator: Any = None
        self._task_orchestrator: Any = None
        self._recovery_engine: Any = None
        self._running = False
        self._bridge_task: Optional[asyncio.Task] = None

        # Persistence
        self._persistence_dir = Path("data/persistence")
        self._persistence_dir.mkdir(parents=True, exist_ok=True)

        # Timing
        self._operation_start_times: Dict[str, float] = {}
        self._phase_start_time: Optional[float] = None
        self._deployment_start_time: Optional[float] = None
        self._operation_durations: List[float] = []

        # UI callbacks
        self._ui_callbacks: List[Callable[[], None]] = []

        # Snapshot cache
        self._snapshot_cache: Dict[str, Any] = {
            "deployment": {},
            "health": {},
            "kernel_state": {},
            "recovery_activities": [],
            "retry_queue": [],
        }

        # Lazy-loaded modules
        self._lazy_ui_state = None
        self._lazy_UIStatePhase = None

        # Attach BridgeSubscriber to RuntimeStateBus for event→UI propagation
        self._bus_subscriber = BridgeSubscriber(self)
        self._bus_subscriber.subscribe_to_all()
        state_bus.attach(self._bus_subscriber)


    # --- Lazy Import Helpers (avoid circular imports) -------------------

    def _get_ui(self):
        """Lazy import ui_state to avoid circular import."""
        if self._lazy_ui_state is None:
            from src.gui.ui_state import ui_state
            self._lazy_ui_state = ui_state
        return self._lazy_ui_state

    def _get_phase(self):
        """Lazy import UIStatePhase to avoid circular import."""
        if self._lazy_UIStatePhase is None:
            from src.gui.ui_state import UIStatePhase
            self._lazy_UIStatePhase = UIStatePhase
        return self._lazy_UIStatePhase

    # --- Initialization -------------------------------------------------

    def bind_kernel(self, kernel: Any) -> None:
        self._kernel = kernel
        logger.info("Runtime bridge bound to kernel")

    def bind_deployment_orchestrator(self, orchestrator: Any) -> None:
        self._deployment_orchestrator = orchestrator
        logger.info("Runtime bridge bound to deployment orchestrator")

    def bind_task_orchestrator(self, orchestrator: Any) -> None:
        self._task_orchestrator = orchestrator
        logger.info("Runtime bridge bound to task orchestrator")

    def bind_recovery_engine(self, engine: Any) -> None:
        self._recovery_engine = engine
        logger.info("Runtime bridge bound to recovery engine")

    # --- Kernel State Push ----------------------------------------------

    def push_kernel_state(self, kernel_result: Any) -> None:
        if not kernel_result:
            return

        ui = self._get_ui()
        phase = self._get_phase()

        if kernel_result.success:
            ui.runtime_status = "Ready"
            ui.system_health = "OK"
            ui.phase = phase.IDLE
            state_bus.publish_sync(
                EventType.KERNEL_READY,
                payload={
                    "components": kernel_result.initialized_components,
                    "duration": kernel_result.total_duration_seconds,
                },
                source="bridge",
                priority=EventPriority.HIGH,
            )
        else:
            ui.runtime_status = "Startup Failed"
            ui.system_health = "Degraded"
            for error in kernel_result.errors:
                ui.add_repair_activity(component="kernel", action="startup", status="failed", message=error[:200])
            for warning in kernel_result.warnings:
                ui.add_repair_activity(component="kernel", action="startup", status="completed", message=f"Warning: {warning[:200]}")
            state_bus.publish_sync(
                EventType.KERNEL_FAILED,
                payload={"errors": kernel_result.errors, "warnings": kernel_result.warnings},
                source="bridge",
                priority=EventPriority.HIGH,
            )

        for comp in kernel_result.initialized_components:
            ui.add_repair_activity(component=comp, action="initialized", status="completed", message="Component initialized successfully")
        for comp in kernel_result.failed_components:
            ui.add_repair_activity(component=comp, action="initialized", status="failed", message=f"Component {comp} failed to initialize")

        logger.info("Kernel state pushed to UI", success=kernel_result.success, components=len(kernel_result.initialized_components))

    # --- Deployment Progress Sync ---------------------------------------

    def push_deployment_phase(self, phase_name: str, phase_number: int, total_phases: int) -> None:
        ui = self._get_ui()
        phase = self._get_phase()
        ui.phase = phase.DEPLOYING
        ui.deployment_status = f"Phase {phase_number}/{total_phases}: {phase_name}"
        self._phase_start_time = time.time()
        logger.debug("Deployment phase pushed", phase=phase_name, num=phase_number)

    def push_deployment_progress(self, tool_name: str, progress_percent: float, current_step: str = "", command: str = "", retry_count: int = 0, max_retries: int = 3) -> None:
        ui = self._get_ui()
        op_id = f"deploy_{tool_name}"
        if op_id not in self._operation_start_times:
            self._operation_start_times[op_id] = time.time()
            ui.start_operation(op_id, tool_name)
        ui.update_operation(operation_id=op_id, progress_percent=progress_percent, phase=current_step, current_command=command, retry_count=retry_count)
        if progress_percent > 0 and progress_percent < 100:
            elapsed = time.time() - self._operation_start_times[op_id]
            estimated_total = elapsed / (progress_percent / 100.0)
            ui.update_estimated_remaining(estimated_total - elapsed)

    def complete_tool_deployment(self, tool_name: str, status: str = "completed", error: Optional[str] = None) -> None:
        ui = self._get_ui()
        op_id = f"deploy_{tool_name}"
        ui.complete_operation(op_id, status)
        if op_id in self._operation_start_times:
            duration = time.time() - self._operation_start_times[op_id]
            self._operation_durations.append(duration)
            del self._operation_start_times[op_id]
        if status == "completed":
            ui.add_repair_activity(component=tool_name, action="deploy", status="completed", message="Tool deployed successfully")
        elif status == "failed":
            ui.add_to_failure_queue(tool_name)
            ui.add_repair_activity(component=tool_name, action="deploy", status="failed", message=error or "Deployment failed")
        logger.info("Tool deployment complete", tool=tool_name, status=status)

    def update_deployment_summary(self, total: int, installed: int, failed: int = 0, skipped: int = 0) -> None:
        ui = self._get_ui()
        ui.set_deployment_summary(total=total, installed=installed, failed=failed, skipped=skipped)

    # --- Recovery/Repair Visibility -------------------------------------

    def push_recovery_activity(self, component: str, action: str, status: str = "running", message: str = "") -> None:
        ui = self._get_ui()
        phase = self._get_phase()
        ui.add_repair_activity(component=component, action=action, status=status, message=message)
        if status == "running":
            ui.phase = phase.REPAIRING
            ui.system_health = "Repairing"
        logger.debug("Recovery activity pushed", component=component, action=action, status=status)

    def push_retry_event(self, tool_name: str, retry_count: int, max_retries: int, last_error: str, cooldown_seconds: int = 5) -> None:
        ui = self._get_ui()
        ui.add_to_retry_queue(tool_name=tool_name, retry_count=retry_count, max_retries=max_retries, last_error=last_error[:200] if last_error else "", cooldown_seconds=cooldown_seconds)
        logger.info("Retry event pushed to UI", tool=tool_name, retry=retry_count, max=max_retries)

    def remove_retry(self, tool_name: str) -> None:
        ui = self._get_ui()
        ui.remove_from_retry_queue(tool_name)

    # --- Model Progress -------------------------------------------------

    def push_model_progress(self, model_name: str, progress_percent: float, status: str = "pulling") -> None:
        ui = self._get_ui()
        phase = self._get_phase()
        op_id = f"model_{model_name}"
        if status == "pulling" and op_id not in self._operation_start_times:
            self._operation_start_times[op_id] = time.time()
            ui.start_operation(op_id, f"model:{model_name}")
            ui.phase = phase.PULLING_MODELS
        if status == "pulling":
            ui.update_operation(operation_id=op_id, progress_percent=progress_percent, phase="Downloading model", current_command=f"ollama pull {model_name}")
        elif status == "completed":
            ui.complete_operation(op_id, "completed")
            ui.add_model_pulled(model_name)
            if op_id in self._operation_start_times:
                del self._operation_start_times[op_id]
        elif status == "failed":
            ui.complete_operation(op_id, "failed")
            if op_id in self._operation_start_times:
                del self._operation_start_times[op_id]

    # --- Health Status --------------------------------------------------

    def push_health_status(self, component: str, status: str) -> None:
        ui = self._get_ui()
        if component == "system":
            ui.system_health = status
        elif component == "runtime":
            ui.runtime_status = status
        elif component == "ai_stack":
            ui.ai_stack_status = status

    def push_diagnostic_result(self, report: Dict[str, Any]) -> None:
        ui = self._get_ui()
        ui.set_scan_result(report)

    # --- Deployment Timing ----------------------------------------------

    def start_deployment_timer(self) -> None:
        ui = self._get_ui()
        self._deployment_start_time = time.time()
        ui.start_deployment_timer()
        self._operation_start_times.clear()
        self._operation_durations.clear()

    def get_throughput(self) -> float:
        if not self._operation_durations:
            return 0.0
        total_time = sum(self._operation_durations) / 60.0
        if total_time <= 0:
            return 0.0
        return len(self._operation_durations) / total_time

    def get_estimated_remaining(self, total_tools: int, completed_tools: int) -> float:
        if completed_tools <= 0:
            return 0.0
        elapsed = time.time() - self._deployment_start_time if self._deployment_start_time else 0
        if elapsed <= 0:
            return 0.0
        avg_time_per_tool = elapsed / completed_tools
        remaining_tools = total_tools - completed_tools
        return avg_time_per_tool * remaining_tools

    # --- State Persistence ----------------------------------------------

    def save_deployment_state(self, state: Dict[str, Any]) -> str:
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        filename = f"deployment_state_{timestamp}.json"
        filepath = self._persistence_dir / filename
        state["_saved_at"] = datetime.now(timezone.utc).isoformat()
        state["_bridge_version"] = "1.0.0"
        try:
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(state, f, indent=2, default=str)
            logger.info("Deployment state saved", path=str(filepath))
            return str(filepath)
        except Exception as e:
            logger.warning("Failed to save deployment state", error=str(e))
            return ""

    def load_deployment_history(self, max_count: int = 50) -> List[Dict[str, Any]]:
        history = []
        try:
            state_files = sorted(self._persistence_dir.glob("deployment_state_*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
            for state_file in state_files[:max_count]:
                try:
                    with open(state_file, "r", encoding="utf-8") as f:
                        state = json.load(f)
                        state["_file"] = str(state_file.name)
                        history.append(state)
                except Exception:
                    continue
        except Exception as e:
            logger.warning("Failed to load deployment history", error=str(e))
        return history

    def load_deployment_state(self, state_file: str) -> Optional[Dict[str, Any]]:
        filepath = self._persistence_dir / state_file
        if not filepath.exists():
            return None
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.warning("Failed to load deployment state", error=str(e))
            return None

    def get_persisted_sessions(self) -> List[Dict[str, Any]]:
        sessions = []
        try:
            for state_file in sorted(self._persistence_dir.glob("deployment_state_*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
                try:
                    with open(state_file, "r", encoding="utf-8") as f:
                        state = json.load(f)
                    sessions.append({"file": state_file.name, "timestamp": state.get("_saved_at", ""), "status": state.get("status", "unknown"), "tools_total": state.get("tools_total", 0), "tools_installed": state.get("tools_installed", 0), "tools_failed": state.get("tools_failed", 0)})
                except Exception:
                    continue
        except Exception as e:
            logger.warning("Failed to list persisted sessions", error=str(e))
        return sessions

    # --- UI Callback Registration ---------------------------------------

    def register_ui_callback(self, callback: Callable[[], None]) -> None:
        self._ui_callbacks.append(callback)

    def get_snapshot(self) -> Dict[str, Any]:
        return dict(self._snapshot_cache)

    def _notify_ui(self) -> None:
        try:
            ui = self._get_ui()
            self._snapshot_cache["deployment"] = {"total": ui.tools_total, "installed": ui.tools_installed, "failed": ui.tools_failed, "skipped": ui.tools_skipped}
            self._snapshot_cache["kernel_state"] = {"success": ui.runtime_status == "Ready", "status": ui.runtime_status}
            self._snapshot_cache["health"] = {"system": {"status": ui.system_health}, "runtime": {"status": ui.runtime_status}, "ai_stack": {"status": ui.ai_stack_status}}
            self._snapshot_cache["recovery_activities"] = ui.get_repair_activities()
            self._snapshot_cache["retry_queue"] = [{"tool_name": item.tool_name, "retry_count": item.retry_count, "max_retries": item.max_retries, "last_error": item.last_error, "cooldown_seconds": item.cooldown_seconds} for item in ui.get_retry_queue()]
        except Exception:
            pass
        for cb in self._ui_callbacks:
            try:
                cb()
            except Exception:
                pass

    # --- Bridge Lifecycle -----------------------------------------------

    async def start_bridge_loop(self) -> None:
        if self._running:
            return
        self._running = True
        self._bridge_task = asyncio.create_task(self._bridge_loop())
        logger.info("Runtime bridge loop started")

    async def _bridge_loop(self) -> None:
        while self._running:
            try:
                await self._sync_kernel_state()
                await asyncio.sleep(1)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning("Bridge loop error", error=str(e))
                await asyncio.sleep(5)

    async def _sync_kernel_state(self) -> None:
        if not self._kernel:
            return
        try:
            ui = self._get_ui()
            if hasattr(self._kernel, "is_ready") and self._kernel.is_ready:
                ui.runtime_status = "Ready"
            elif hasattr(self._kernel, "has_failed") and self._kernel.has_failed:
                ui.runtime_status = "Failed"
            elif hasattr(self._kernel, "is_running") and self._kernel.is_running:
                ui.runtime_status = "Starting"
        except Exception:
            pass

    def stop_bridge(self) -> None:
        self._running = False
        if self._bridge_task:
            self._bridge_task.cancel()
            self._bridge_task = None
        logger.info("Runtime bridge stopped")

    def reset(self) -> None:
        self._operation_start_times.clear()
        self._operation_durations.clear()
        self._phase_start_time = None
        self._deployment_start_time = None


# Global singleton
runtime_bridge = RuntimeBridge()
