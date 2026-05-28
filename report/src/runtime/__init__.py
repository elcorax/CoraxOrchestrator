"""
Corax Orchestrator - Runtime Package.

Provides the complete runtime infrastructure:
- CoraxRuntimeKernel: Single authoritative startup lifecycle
- RuntimeBridge: Kernel ↔ GUI convergence bridge
- RuntimeStateBus: Central event bus for all runtime state propagation
- StartupStateMachine: Deterministic state tracking
- RuntimeDiagnostics: Health and crash diagnostics
- StartupRecovery: Self-healing startup recovery
- BootstrapRuntime: Environment bootstrap
"""

from src.runtime.state import (
    StartupState,
    RuntimePhase,
    StartupCheckpoint,
    StartupStateMachine,
)
from src.runtime.bootstrap import BootstrapRuntime, BootstrapResult
from src.runtime.recovery import StartupRecovery, RecoveryResult
from src.runtime.diagnostics import RuntimeDiagnostics, RuntimeDiagnosticReport
from src.runtime.kernel import CoraxRuntimeKernel, KernelResult
from src.runtime.bridge import RuntimeBridge, runtime_bridge
from src.runtime.state_bus import (
    RuntimeStateBus,
    state_bus,
    BusEvent,
    EventType,
    EventPriority,
    EventSubscriber,
    TelemetryAggregator,
    PersistenceJournal,
    HealthBroadcaster,
    ETATracker,
)

__all__ = [
    # State Machine
    "StartupState",
    "RuntimePhase",
    "StartupCheckpoint",
    "StartupStateMachine",
    # Bootstrap
    "BootstrapRuntime",
    "BootstrapResult",
    # Recovery
    "StartupRecovery",
    "RecoveryResult",
    # Diagnostics
    "RuntimeDiagnostics",
    "RuntimeDiagnosticReport",
    # Kernel
    "CoraxRuntimeKernel",
    "KernelResult",
    # Bridge
    "RuntimeBridge",
    "runtime_bridge",
    # State Bus
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


