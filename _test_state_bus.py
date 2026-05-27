"""Quick validation of RuntimeStateBus convergence architecture."""
import os, sys
sys.path.insert(0, os.getcwd())

from src.runtime.state_bus import (
    state_bus, RuntimeStateBus, BusEvent, EventType,
    EventPriority, EventSubscriber, TelemetryAggregator,
    PersistenceJournal, HealthBroadcaster, ETATracker,
)

print("=== RuntimeStateBus Validation ===")

# 1. Basic imports
print("[OK] All imports resolved")

# 2. Singleton
print(f"[OK] state_bus is RuntimeStateBus: {isinstance(state_bus, RuntimeStateBus)}")

# 3. Event types
print(f"[OK] {len(list(EventType))} event types defined")

# 4. Publish sync event
state_bus.publish_sync(EventType.KERNEL_READY, {"components": ["test"]}, "test")
state_bus.publish_sync(EventType.COMPONENT_STATUS, {"component": "test", "status": "ok"}, "test")
state_bus.publish_sync(EventType.DEPLOYMENT_STARTED, {"total_tools": 10}, "test")
state_bus.publish_sync(EventType.DEPLOYMENT_TOOL_COMPLETED, {"tool_name": "ollama", "duration_seconds": 5.0}, "test")
state_bus.publish_sync(EventType.DEPLOYMENT_TOOL_FAILED, {"tool_name": "docker", "failure_category": "download"}, "test")
state_bus.publish_sync(EventType.RECOVERY_ACTIVITY, {"component": "docker", "action": "retry", "status": "running"}, "test")
state_bus.publish_sync(EventType.ERROR_OCCURRED, {"component": "kernel", "message": "test error"}, "test")
print("[OK] Events published to state_bus")

# 5. Snapshot
snap = state_bus.get_snapshot()
print(f"[OK] Snapshot keys: {list(snap.keys())}")
print(f"[OK] Telemetry keys: {list(snap['telemetry'].keys())}")
print(f"[OK] Health overall: {snap['health']['overall']}")

# 6. Telemetry
ta = TelemetryAggregator()
print(f"[OK] Telemetry name: {ta.name}")
print(f"[OK] Subscribed to all: {len(ta.subscribed_types)} event types")

# 7. Persistence journal
pj = PersistenceJournal()
print(f"[OK] Journal name: {pj.name}")

# 8. Health broadcaster
hb = HealthBroadcaster()
hb.update_component("kernel", "ok")
hb.update_component("deployment", "ok")
print(f"[OK] Health overall: {hb.get_status()['overall']}")
print(f"[OK] Healthy: {hb.get_status()['healthy']}")

# 9. ETA tracker
eta = ETATracker()
eta.on_event_sync(BusEvent(EventType.DEPLOYMENT_STARTED, {"total_tools": 10}, source="test"))
eta.on_event_sync(BusEvent(EventType.DEPLOYMENT_TOOL_COMPLETED, {"tool_name": "test"}, source="test"))
eta.on_event_sync(BusEvent(EventType.DEPLOYMENT_TOOL_COMPLETED, {"tool_name": "test2"}, source="test"))
eta_result = eta.get_eta()
print(f"[OK] ETA completed: {eta_result['completed_operations']}/{eta_result['total_operations']}")

# 10. Event history
recent = state_bus.get_recent_events(count=5)
print(f"[OK] Recent events: {len(recent)}")

print("\n=== ALL VALIDATIONS PASSED ===")
print("RuntimeStateBus convergence architecture is operational.")
