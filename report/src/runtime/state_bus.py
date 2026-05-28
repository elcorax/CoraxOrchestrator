"""
Corax Orchestrator - RuntimeStateBus Convergence Bus.

THE authoritative event bus connecting all runtime systems:
- Runtime kernel events → GUI, persistence, telemetry
- Deployment events → GUI, persistence, telemetry
- Recovery events → GUI, persistence, telemetry
- Health broadcasts → GUI, persistence, telemetry
- Telemetry aggregation → metrics store
- Persistence journaling → file system
- ETA/progress synchronization → GUI

Architecture:
    Systems → RuntimeStateBus → RuntimeBridge → UIStateManager → GUI Panels
                              → PersistenceJournal → data/persistence/
                              → TelemetryAggregator → metrics
                              → HealthBroadcaster → periodic health

The bus is the SINGLE write path from all runtime systems.
"""

from typing import Optional, Dict, Any, List, Callable, Set, Awaitable
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum, auto
import asyncio
import json
import time
import os
from pathlib import Path
from collections import deque
import statistics

from src.core.logging import get_logger

logger = get_logger(__name__)


# ─── Event Models ───────────────────────────────────────────────────────────

class EventPriority(Enum):
    """Priority levels for bus events."""
    LOW = 0
    NORMAL = 1
    HIGH = 2
    CRITICAL = 3


class EventType(Enum):
    """All event types flowing through the state bus."""

    # Runtime lifecycle
    KERNEL_STARTING = "kernel.starting"
    KERNEL_READY = "kernel.ready"
    KERNEL_FAILED = "kernel.failed"
    KERNEL_SHUTDOWN = "kernel.shutdown"
    PHASE_CHANGE = "phase.change"
    STATE_TRANSITION = "state.transition"

    # Deployment events
    DEPLOYMENT_STARTED = "deployment.started"
    DEPLOYMENT_PHASE = "deployment.phase"
    DEPLOYMENT_PROGRESS = "deployment.progress"
    DEPLOYMENT_TOOL_STARTED = "deployment.tool.started"
    DEPLOYMENT_TOOL_COMPLETED = "deployment.tool.completed"
    DEPLOYMENT_TOOL_FAILED = "deployment.tool.failed"
    DEPLOYMENT_COMPLETED = "deployment.completed"

    # Recovery events
    RECOVERY_STARTED = "recovery.started"
    RECOVERY_ACTIVITY = "recovery.activity"
    RECOVERY_COMPLETED = "recovery.completed"
    RECOVERY_FAILED = "recovery.failed"
    RETRY_EVENT = "retry.event"

    # Health events
    HEALTH_CHECK = "health.check"
    HEALTH_STATUS_CHANGE = "health.status_change"
    COMPONENT_STATUS = "component.status"

    # Telemetry events
    TELEMETRY_SAMPLE = "telemetry.sample"
    TELEMETRY_THROUGHPUT = "telemetry.throughput"
    TELEMETRY_FAILURE_RATE = "telemetry.failure_rate"

    # Model events
    MODEL_PROGRESS = "model.progress"
    MODEL_COMPLETED = "model.completed"
    MODEL_DOWNLOADING = "model.downloading"
    MODEL_INSTALLED = "model.installed"

    # Deployment result events
    TOOL_INSTALLED = "tool.installed"
    DEPLOYMENT_FAILED = "deployment.failed"

    # System events
    ERROR_OCCURRED = "error.occurred"
    WARNING_ISSUED = "warning.issued"
    SYSTEM_SCAN = "system.scan"

    # Persistence events
    PERSISTENCE_SAVED = "persistence.saved"
    PERSISTENCE_LOADED = "persistence.loaded"


@dataclass
class BusEvent:
    """A single event on the RuntimeStateBus."""
    event_type: EventType
    payload: Dict[str, Any] = field(default_factory=dict)
    priority: EventPriority = EventPriority.NORMAL
    source: str = "unknown"
    timestamp: float = field(default_factory=time.time)
    event_id: str = ""

    def __post_init__(self):
        if not self.event_id:
            self.event_id = f"{self.event_type.value}_{int(self.timestamp * 1000)}_{id(self)}"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "event_type": self.event_type.value,
            "payload": self.payload,
            "priority": self.priority.value,
            "source": self.source,
            "timestamp": self.timestamp,
            "event_id": self.event_id,
        }


# ─── Subscriber Interface ──────────────────────────────────────────────────

class EventSubscriber:
    """Base class for state bus subscribers."""

    def __init__(self, name: str):
        self._name = name
        self._subscribed_types: Set[EventType] = set()

    @property
    def name(self) -> str:
        return self._name

    @property
    def subscribed_types(self) -> Set[EventType]:
        return self._subscribed_types

    def subscribe_to(self, *event_types: EventType) -> None:
        """Subscribe to specific event types."""
        self._subscribed_types.update(event_types)

    def subscribe_all(self) -> None:
        """Subscribe to all event types."""
        self._subscribed_types = set(EventType)

    async def on_event(self, event: BusEvent) -> None:
        """Handle an event. Override in subclasses."""
        raise NotImplementedError

    def on_event_sync(self, event: BusEvent) -> None:
        """Synchronous event handler override."""
        pass


# ─── RuntimeStateBus ────────────────────────────────────────────────────────

class RuntimeStateBus:
    """
    Central event bus for all runtime state propagation.

    All runtime systems publish events to this bus. Subscribers receive
    events based on their subscriptions. The bus provides:
    - Typed event dispatch with priority ordering
    - Async and sync subscriber support
    - Event journaling for persistence
    - Telemetry aggregation
    - Health broadcasting
    - ETA/progress synchronization
    """

    def __init__(self):
        self._subscribers: List[EventSubscriber] = []
        self._event_history: deque = deque(maxlen=1000)
        self._running = False
        self._event_queue: asyncio.Queue = asyncio.Queue()
        self._processor_task: Optional[asyncio.Task] = None

        # Telemetry
        self._telemetry: "TelemetryAggregator" = TelemetryAggregator()

        # Persistence journal
        self._journal: "PersistenceJournal" = PersistenceJournal()

        # Health broadcaster
        self._broadcaster: "HealthBroadcaster" = HealthBroadcaster()

        # ETA tracker
        self._eta_tracker: "ETATracker" = ETATracker()

        # Built-in subscribers
        self.attach(self._telemetry)
        self.attach(self._journal)
        self.attach(self._broadcaster)

    # ─── Subscriber Management ──────────────────────────────────────────

    def attach(self, subscriber: EventSubscriber) -> None:
        """Attach a subscriber to the bus."""
        if subscriber not in self._subscribers:
            self._subscribers.append(subscriber)
            logger.debug(f"Subscriber attached: {subscriber.name}")

    def detach(self, subscriber: EventSubscriber) -> None:
        """Detach a subscriber from the bus."""
        if subscriber in self._subscribers:
            self._subscribers.remove(subscriber)
            logger.debug(f"Subscriber detached: {subscriber.name}")

    # ─── Publishing ─────────────────────────────────────────────────────

    def publish(self, event: BusEvent) -> None:
        """
        Publish an event to all matching subscribers (synchronous path).

        Args:
            event: The event to publish
        """
        self._event_history.append(event)

        # Dispatch to sync subscribers
        for sub in self._subscribers:
            if event.event_type in sub.subscribed_types or not sub.subscribed_types:
                try:
                    sub.on_event_sync(event)
                except Exception as e:
                    logger.warning(
                        f"Sync subscriber {sub.name} failed on {event.event_type.value}: {e}"
                    )

        # Queue for async processing
        if self._running:
            try:
                self._event_queue.put_nowait(event)
            except asyncio.QueueFull:
                pass

    async def publish_async(self, event: BusEvent) -> None:
        """
        Publish an event asynchronously to all matching subscribers.

        Args:
            event: The event to publish
        """
        self._event_history.append(event)

        # Dispatch to all subscribers
        for sub in self._subscribers:
            if event.event_type in sub.subscribed_types or not sub.subscribed_types:
                try:
                    await sub.on_event(event)
                except Exception as e:
                    logger.warning(
                        f"Subscriber {sub.name} failed on {event.event_type.value}: {e}"
                    )

    def publish_sync(
        self,
        event_type: EventType,
        payload: Optional[Dict[str, Any]] = None,
        source: str = "unknown",
        priority: EventPriority = EventPriority.NORMAL,
    ) -> None:
        """
        Convenience method: create and publish an event synchronously.

        Args:
            event_type: Type of event
            payload: Event data
            source: Source component name
            priority: Event priority
        """
        event = BusEvent(
            event_type=event_type,
            payload=payload or {},
            source=source,
            priority=priority,
        )
        self.publish(event)

    # ─── Lifecycle ──────────────────────────────────────────────────────

    def start(self) -> None:
        """Start the bus async processor."""
        if self._running:
            return
        self._running = True
        try:
            loop = asyncio.get_running_loop()
            self._processor_task = loop.create_task(self._process_loop())
        except RuntimeError:
            # No running event loop - processor will start when loop is available
            # This is normal during synchronous initialization
            pass
        logger.info("RuntimeStateBus started")

    async def start_async(self) -> None:
        """Start the bus async processor (awaitable)."""
        if self._running:
            return
        self._running = True
        self._processor_task = asyncio.create_task(self._process_loop())
        logger.info("RuntimeStateBus started async")

    def stop(self) -> None:
        """Stop the bus."""
        self._running = False
        if self._processor_task:
            self._processor_task.cancel()
            self._processor_task = None
        logger.info("RuntimeStateBus stopped")

    async def _process_loop(self) -> None:
        """Background processor for queued events."""
        while self._running:
            try:
                event = await asyncio.wait_for(
                    self._event_queue.get(), timeout=1.0
                )
                # Forward to async subscribers (sync subscribers already handled)
                for sub in self._subscribers:
                    if event.event_type in sub.subscribed_types or not sub.subscribed_types:
                        try:
                            await sub.on_event(event)
                        except Exception as e:
                            logger.warning(
                                f"Async subscriber {sub.name} failed on "
                                f"{event.event_type.value}: {e}"
                            )
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning(f"Bus processor error: {e}")

    # ─── Queries ────────────────────────────────────────────────────────

    def get_recent_events(
        self, event_type: Optional[EventType] = None, count: int = 50
    ) -> List[BusEvent]:
        """
        Get recent events, optionally filtered by type.

        Args:
            event_type: Optional filter by event type
            count: Maximum number of events to return

        Returns:
            List of recent BusEvent objects
        """
        if event_type:
            filtered = [
                e for e in self._event_history if e.event_type == event_type
            ]
            return filtered[-count:]
        return list(self._event_history)[-count:]

    def get_telemetry(self) -> Dict[str, Any]:
        """Get current telemetry data."""
        return self._telemetry.get_summary()

    def get_health_status(self) -> Dict[str, Any]:
        """Get current health status from broadcaster."""
        return self._broadcaster.get_status()

    def get_eta(self) -> Dict[str, Any]:
        """Get current ETA estimates."""
        return self._eta_tracker.get_eta()

    def get_snapshot(self) -> Dict[str, Any]:
        """Get a complete snapshot of bus state."""
        return {
            "telemetry": self.get_telemetry(),
            "health": self.get_health_status(),
            "eta": self.get_eta(),
            "recent_events": [
                e.to_dict() for e in self.get_recent_events(count=20)
            ],
        }


# ─── Telemetry Aggregator ──────────────────────────────────────────────────

class TelemetryAggregator(EventSubscriber):
    """
    Aggregates runtime telemetry from bus events.

    Tracks:
    - Operation throughput (tools/min)
    - Failure rates by category
    - Average operation durations
    - Phase durations
    - Component health metrics
    """

    def __init__(self):
        super().__init__("telemetry")
        self.subscribe_all()

        self._operation_durations: List[float] = []
        self._phase_durations: Dict[str, List[float]] = {}
        self._failure_counts: Dict[str, int] = {}
        self._success_counts: Dict[str, int] = {}
        self._total_events: int = 0
        self._start_time: float = time.time()
        self._tool_completions: List[float] = []
        self._component_status: Dict[str, str] = {}

    def on_event_sync(self, event: BusEvent) -> None:
        """Process events for telemetry aggregation."""
        self._total_events += 1

        if event.event_type == EventType.DEPLOYMENT_TOOL_COMPLETED:
            payload = event.payload
            duration = payload.get("duration_seconds", 0)
            if duration > 0:
                self._operation_durations.append(duration)
                self._tool_completions.append(time.time())
                tool_name = payload.get("tool_name", "unknown")
                self._success_counts[tool_name] = (
                    self._success_counts.get(tool_name, 0) + 1
                )

        elif event.event_type == EventType.DEPLOYMENT_TOOL_FAILED:
            tool_name = event.payload.get("tool_name", "unknown")
            category = event.payload.get("failure_category", "unknown")
            self._failure_counts[tool_name] = (
                self._failure_counts.get(tool_name, 0) + 1
            )
            self._failure_counts[f"cat:{category}"] = (
                self._failure_counts.get(f"cat:{category}", 0) + 1
            )

        elif event.event_type == EventType.PHASE_CHANGE:
            phase_name = event.payload.get("phase", "unknown")
            duration = event.payload.get("duration_ms", 0)
            if phase_name not in self._phase_durations:
                self._phase_durations[phase_name] = []
            self._phase_durations[phase_name].append(duration)

        elif event.event_type == EventType.COMPONENT_STATUS:
            comp = event.payload.get("component", "unknown")
            status = event.payload.get("status", "unknown")
            self._component_status[comp] = status

    async def on_event(self, event: BusEvent) -> None:
        """Async processing (mirrors sync for this aggregator)."""
        self.on_event_sync(event)

    def get_throughput(self) -> float:
        """Calculate tools per minute throughput."""
        if len(self._tool_completions) < 2:
            return 0.0
        recent = [t for t in self._tool_completions if t > time.time() - 300]
        if len(recent) < 2:
            return 0.0
        duration_minutes = (recent[-1] - recent[0]) / 60.0
        if duration_minutes <= 0:
            return 0.0
        return (len(recent) - 1) / duration_minutes

    def get_avg_operation_duration(self) -> float:
        """Get average operation duration in seconds."""
        if not self._operation_durations:
            return 0.0
        return statistics.mean(self._operation_durations[-50:])

    def get_failure_rate(self) -> float:
        """Get overall failure rate as percentage."""
        total_success = sum(self._success_counts.values())
        total_failures = sum(
            v for k, v in self._failure_counts.items() if not k.startswith("cat:")
        )
        total = total_success + total_failures
        if total == 0:
            return 0.0
        return (total_failures / total) * 100.0

    def get_summary(self) -> Dict[str, Any]:
        """Get telemetry summary."""
        uptime_seconds = time.time() - self._start_time
        total_ops = sum(self._success_counts.values()) + sum(
            v for k, v in self._failure_counts.items() if not k.startswith("cat:")
        )

        return {
            "uptime_seconds": round(uptime_seconds, 1),
            "total_events_processed": self._total_events,
            "total_operations": total_ops,
            "throughput_tools_per_min": round(self.get_throughput(), 2),
            "avg_operation_duration_seconds": round(
                self.get_avg_operation_duration(), 2
            ),
            "failure_rate_percent": round(self.get_failure_rate(), 2),
            "successful_operations": dict(self._success_counts),
            "failure_counts": {
                k: v for k, v in self._failure_counts.items()
            },
            "component_status": dict(self._component_status),
            "phase_durations": {
                k: round(statistics.mean(v), 1) if v else 0
                for k, v in self._phase_durations.items()
            },
        }


# ─── Persistence Journal ───────────────────────────────────────────────────

class PersistenceJournal(EventSubscriber):
    """
    Journals all bus events to persistent storage.

    Maintains:
    - Full event journal (data/persistence/event_journal.jsonl)
    - Per-type event indices
    - Automatic pruning of old entries (>7 days)
    """

    def __init__(self, persistence_dir: Optional[Path] = None):
        super().__init__("persistence_journal")
        self.subscribe_all()
        self._persistence_dir = persistence_dir or Path("data/persistence")
        self._persistence_dir.mkdir(parents=True, exist_ok=True)
        self._journal_path = self._persistence_dir / "event_journal.jsonl"
        self._error_journal_path = self._persistence_dir / "error_journal.jsonl"
        self._recovery_journal_path = self._persistence_dir / "recovery_journal.jsonl"
        self._event_count: int = 0
        self._last_prune_time: float = time.time()
        self._max_journal_entries = 10000

    def on_event_sync(self, event: BusEvent) -> None:
        """Journal events to file."""
        self._event_count += 1

        try:
            # Journal all events
            with open(self._journal_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(event.to_dict()) + "\n")

            # Journal errors separately
            if event.event_type == EventType.ERROR_OCCURRED:
                with open(self._error_journal_path, "a", encoding="utf-8") as f:
                    f.write(json.dumps(event.to_dict()) + "\n")

            # Journal recovery events separately
            if event.event_type in (
                EventType.RECOVERY_ACTIVITY,
                EventType.RECOVERY_STARTED,
                EventType.RECOVERY_COMPLETED,
                EventType.RECOVERY_FAILED,
            ):
                with open(self._recovery_journal_path, "a", encoding="utf-8") as f:
                    f.write(json.dumps(event.to_dict()) + "\n")

            # Prune old entries every 100 events
            if self._event_count % 100 == 0:
                self._prune_old_entries()

        except Exception as e:
            logger.warning(f"Journal write failed: {e}")

    async def on_event(self, event: BusEvent) -> None:
        """Async handling mirrors sync."""
        self.on_event_sync(event)

    def _prune_old_entries(self) -> None:
        """Prune journal entries older than 7 days."""
        now = time.time()
        if now - self._last_prune_time < 3600:  # Once per hour max
            return
        self._last_prune_time = now

        cutoff = now - (7 * 86400)
        for journal_path in [
            self._journal_path,
            self._error_journal_path,
            self._recovery_journal_path,
        ]:
            if not journal_path.exists():
                continue
            try:
                # Count lines first
                with open(journal_path, "r", encoding="utf-8") as f:
                    lines = f.readlines()

                if len(lines) > self._max_journal_entries:
                    # Keep only the last N entries
                    with open(journal_path, "w", encoding="utf-8") as f:
                        f.writelines(lines[-self._max_journal_entries:])
            except Exception as e:
                logger.warning(f"Journal prune failed for {journal_path}: {e}")

    def get_recent_errors(self, count: int = 50) -> List[Dict[str, Any]]:
        """Get recent error events from journal."""
        return self._read_journal(self._error_journal_path, count)

    def get_recent_recoveries(self, count: int = 50) -> List[Dict[str, Any]]:
        """Get recent recovery events from journal."""
        return self._read_journal(self._recovery_journal_path, count)

    def get_event_count(self) -> int:
        """Get total event count."""
        return self._event_count

    def _read_journal(self, path: Path, count: int) -> List[Dict[str, Any]]:
        """Read last N entries from a journal file."""
        if not path.exists():
            return []
        try:
            with open(path, "r", encoding="utf-8") as f:
                lines = f.readlines()
            entries = []
            for line in lines[-count:]:
                try:
                    entries.append(json.loads(line.strip()))
                except (json.JSONDecodeError, ValueError):
                    continue
            return entries
        except Exception as e:
            logger.warning(f"Journal read failed for {path}: {e}")
            return []


# ─── Health Broadcaster ────────────────────────────────────────────────────

class HealthBroadcaster(EventSubscriber):
    """
    Monitors component health and broadcasts status changes.

    Tracks health status of all registered components and emits
    health check events at configurable intervals.
    """

    def __init__(self):
        super().__init__("health_broadcaster")
        self.subscribe_to(
            EventType.COMPONENT_STATUS,
            EventType.HEALTH_STATUS_CHANGE,
            EventType.ERROR_OCCURRED,
            EventType.KERNEL_READY,
            EventType.KERNEL_FAILED,
        )

        self._component_health: Dict[str, str] = {}
        self._last_health_event: Dict[str, float] = {}
        self._error_count: int = 0
        self._last_error_time: float = 0
        self._overall_status: str = "unknown"

    def update_component(self, component: str, status: str) -> None:
        """
        Update a component's health status.

        Args:
            component: Component name
            status: "ok", "degraded", "failed", "starting", "unknown"
        """
        old_status = self._component_health.get(component)
        self._component_health[component] = status

        if old_status != status:
            self._last_health_event[component] = time.time()

        # Derive overall status
        self._derive_overall_status()

    def _derive_overall_status(self) -> None:
        """Derive overall health from component statuses."""
        if not self._component_health:
            self._overall_status = "unknown"
            return

        statuses = set(self._component_health.values())
        if "failed" in statuses:
            self._overall_status = "degraded"
        elif "starting" in statuses:
            self._overall_status = "starting"
        elif "degraded" in statuses:
            self._overall_status = "degraded"
        elif statuses == {"ok"} or statuses == {"ok", "ready"}:
            self._overall_status = "ok"
        else:
            self._overall_status = "unknown"

    def on_event_sync(self, event: BusEvent) -> None:
        """Process health-related events."""
        if event.event_type == EventType.COMPONENT_STATUS:
            comp = event.payload.get("component", "unknown")
            status = event.payload.get("status", "unknown")
            self.update_component(comp, status)

        elif event.event_type == EventType.ERROR_OCCURRED:
            self._error_count += 1
            self._last_error_time = time.time()
            comp = event.payload.get("component", "system")
            self.update_component(comp, "degraded")

        elif event.event_type == EventType.KERNEL_READY:
            self.update_component("kernel", "ok")

        elif event.event_type == EventType.KERNEL_FAILED:
            self.update_component("kernel", "failed")

    async def on_event(self, event: BusEvent) -> None:
        """Async processing mirrors sync."""
        self.on_event_sync(event)

    def get_status(self) -> Dict[str, Any]:
        """Get current health status of all components."""
        return {
            "overall": self._overall_status,
            "components": dict(self._component_health),
            "error_count": self._error_count,
            "last_error_time": self._last_error_time,
            "healthy": self._overall_status == "ok",
        }


# ─── ETA Tracker ──────────────────────────────────────────────────────────

class ETATracker(EventSubscriber):
    """
    Tracks deployment progress and calculates ETA estimates.

    Uses moving average of operation durations to predict
    remaining time for deployment operations.
    """

    def __init__(self):
        super().__init__("eta_tracker")
        self.subscribe_to(
            EventType.DEPLOYMENT_TOOL_COMPLETED,
            EventType.DEPLOYMENT_TOOL_FAILED,
            EventType.DEPLOYMENT_STARTED,
            EventType.DEPLOYMENT_COMPLETED,
            EventType.DEPLOYMENT_PROGRESS,
        )

        self._deployment_start_time: Optional[float] = None
        self._completed_operations: List[float] = []
        self._failed_operations: int = 0
        self._total_operations: int = 0
        self._progress_percent: float = 0.0

    def on_event_sync(self, event: BusEvent) -> None:
        """Process events for ETA calculation."""
        if event.event_type == EventType.DEPLOYMENT_STARTED:
            self._deployment_start_time = time.time()
            self._completed_operations.clear()
            self._failed_operations = 0
            self._total_operations = event.payload.get("total_tools", 0)
            self._progress_percent = 0.0

        elif event.event_type == EventType.DEPLOYMENT_TOOL_COMPLETED:
            self._completed_operations.append(time.time())
            self._progress_percent = (
                len(self._completed_operations) / max(self._total_operations, 1)
            ) * 100.0

        elif event.event_type == EventType.DEPLOYMENT_TOOL_FAILED:
            self._failed_operations += 1
            self._completed_operations.append(time.time())
            self._progress_percent = (
                len(self._completed_operations) / max(self._total_operations, 1)
            ) * 100.0

        elif event.event_type == EventType.DEPLOYMENT_PROGRESS:
            self._progress_percent = event.payload.get(
                "progress_percent", self._progress_percent
            )

        elif event.event_type == EventType.DEPLOYMENT_COMPLETED:
            self._progress_percent = 100.0

    async def on_event(self, event: BusEvent) -> None:
        """Async processing mirrors sync."""
        self.on_event_sync(event)

    def get_eta(self) -> Dict[str, Any]:
        """Get ETA estimates."""
        elapsed = 0.0
        if self._deployment_start_time:
            elapsed = time.time() - self._deployment_start_time

        remaining = 0.0
        if self._progress_percent > 0 and self._progress_percent < 100:
            remaining = (elapsed / (self._progress_percent / 100.0)) - elapsed

        return {
            "elapsed_seconds": round(elapsed, 1),
            "estimated_remaining_seconds": round(max(remaining, 0), 1),
            "progress_percent": round(self._progress_percent, 1),
            "total_operations": self._total_operations,
            "completed_operations": len(self._completed_operations),
            "failed_operations": self._failed_operations,
        }


# ─── Global Singleton ─────────────────────────────────────────────────────

state_bus = RuntimeStateBus()
"""Global singleton RuntimeStateBus instance."""

__all__ = [
    "RuntimeStateBus",
    "state_bus",
    "BusEvent",
    "EventType",
    "EventPriority",
    "EventSubscriber",
    "TelemetryAggregator",
    "PersistenceJournal",
    "HealthBroadcaster",
    "ETATracker",
]
