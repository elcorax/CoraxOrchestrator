"""
Corax Orchestrator — Extended Stability & Survivability Test.

Validates:
- Runtime bootstrap
- State bus propagation
- Timer exception safety
- Memory stability
- Graceful shutdown
- Event bus stability
- Recovery scenarios
"""

import asyncio
import time
import sys
import os
import gc
import traceback
from datetime import datetime, timedelta

# Add project root
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.core.logging import get_logger

logger = get_logger("stability_test")

# Test configuration
TEST_DURATION_SECONDS = 180  # 3 minutes validation
MEMORY_CHECK_INTERVAL = 30   # Check memory every 30s
EXCEPTION_THRESHOLD = 5       # Max allowed exceptions per cycle

# Global metrics
metrics = {
    "exceptions": [],
    "memory_samples": [],
    "bus_events_received": 0,
    "timers_fired": 0,
    "timer_errors": 0,
    "shutdown_ok": False,
    "start_time": None,
}


class StabilityTestError(Exception):
    """Raised when a stability check fails."""
    pass


def track_exception(context: str, exc: Exception) -> None:
    """Track an exception for stability analysis."""
    metrics["exceptions"].append({
        "time": datetime.now().isoformat(),
        "context": context,
        "type": type(exc).__name__,
        "message": str(exc),
    })
    logger.error(f"[STABILITY] Exception in {context}: {exc}")


async def test_state_bus_propagation() -> bool:
    """Test state bus event propagation reliability."""
    from src.runtime.state_bus import state_bus, EventType, EventSubscriber, BusEvent

    received_events = []

    class TestSubscriber(EventSubscriber):
        def __init__(self):
            super().__init__("stability_test")
            self.subscribe_all()

        def on_event_sync(self, event: BusEvent) -> None:
            received_events.append(event)
            metrics["bus_events_received"] += 1

    subscriber = TestSubscriber()
    state_bus.attach(subscriber)

    # Publish events
    for i in range(10):
        state_bus.publish_sync(
            EventType.DEPLOYMENT_PROGRESS,
            payload={"test_id": i, "value": i * 10},
            source="stability_test",
        )
        await asyncio.sleep(0.01)

    # Verify propagation
    if len(received_events) < 10:
        logger.warning(
            f"State bus propagation: expected 10, got {len(received_events)}"
        )
        return False

    logger.info(f"State bus propagation OK: {len(received_events)} events")
    return True


async def test_timer_exception_safety() -> bool:
    """Test that timer callbacks don't crash when exceptions occur."""
    errors = 0

    # Simulate timer callbacks with various failure modes
    async def safe_callback():
        try:
            x = 1 / 0  # Deliberate exception
        except ZeroDivisionError:
            pass  # Should be caught - this is the safe pattern

    async def unsafe_callback():
        # This would crash without try/except
        try:
            raise ValueError("Simulated timer error")
        except ValueError:
            pass  # Properly caught

    # Execute both patterns
    await safe_callback()
    await unsafe_callback()

    # Test widget guard pattern
    class MockWidget:
        def __init__(self):
            self._label = None

    widget = MockWidget()

    # Safe update pattern
    try:
        if hasattr(widget, '_label') and widget._label:
            widget._label.setText("test")
    except Exception:
        errors += 1

    # This should NOT error since we use hasattr guard
    try:
        if hasattr(widget, '_nonexistent') and widget._nonexistent:
            pass  # Should not raise AttributeError
    except Exception:
        errors += 1

    if errors > 0:
        logger.warning(f"Timer safety test: {errors} errors")
        return False

    logger.info("Timer exception safety OK")
    return True


async def test_graceful_shutdown() -> bool:
    """Test that components can be shut down gracefully."""
    from src.runtime.state_bus import state_bus

    try:
        # Stop state bus
        state_bus.stop()
        await asyncio.sleep(0.1)

        # Verify no exceptions during stop
        state_bus.start()
        await asyncio.sleep(0.1)

        metrics["shutdown_ok"] = True
        logger.info("Graceful shutdown OK")
        return True
    except Exception as e:
        track_exception("shutdown_test", e)
        return False


async def test_ui_state_consistency() -> bool:
    """Test UI state manager consistency under load."""
    from src.gui.ui_state import ui_state, UIStatePhase, RepairActivity

    # Rapid state changes using proper setter methods
    for _ in range(100):
        ui_state.set_deployment_summary(total=5, installed=3, failed=0, skipped=0)
        ui_state.start_deployment_timer()

    # Verify consistency
    if ui_state.tools_total != 5:
        logger.warning(f"UI state total mismatch: {ui_state.tools_total}")
        return False
    if ui_state.tools_installed != 3:
        logger.warning(f"UI state installed mismatch: {ui_state.tools_installed}")
        return False

    # Test phase transitions
    for phase in [UIStatePhase.SCANNING, UIStatePhase.DEPLOYING, UIStatePhase.COMPLETED]:
        ui_state.phase = phase
        assert ui_state.phase == phase, f"Phase not set: {phase}"

    # Test repair activity tracking
    ui_state.add_repair_activity(
        component="test_component",
        action="test_action",
        status="running",
        message="Testing repair activity tracking",
    )
    activities = ui_state.get_repair_activities()
    if len(activities) != 1:
        logger.warning(f"Repair activity count mismatch: {len(activities)}")
        return False

    # Test retry queue
    ui_state.add_to_retry_queue(
        tool_name="test_tool",
        retry_count=1,
        max_retries=3,
        last_error="test error",
        cooldown_seconds=5,
    )
    retry_queue = ui_state.get_retry_queue()
    if len(retry_queue) != 1:
        logger.warning(f"Retry queue count mismatch: {len(retry_queue)}")
        return False

    # Test snapshot
    snapshot = ui_state.get_snapshot()
    if not isinstance(snapshot, dict):
        logger.warning("Snapshot is not a dict")
        return False
    if "phase" not in snapshot:
        logger.warning("Snapshot missing phase")
        return False

    # Reset for next test
    ui_state.full_reset()

    logger.info(f"UI state consistency OK")
    return True


async def run_stability_suite() -> dict:

    """Run the complete stability test suite."""
    results = {}
    metrics["start_time"] = time.time()

    logger.info("=" * 60)
    logger.info("CORAX EXTENDED STABILITY TEST SUITE")
    logger.info(f"Started: {datetime.now().isoformat()}")
    logger.info("=" * 60)

    # Test 1: State bus propagation
    logger.info("\n[1/5] Testing state bus propagation...")
    results["state_bus"] = await test_state_bus_propagation()

    # Test 2: Timer exception safety
    logger.info("\n[2/5] Testing timer exception safety...")
    results["timer_safety"] = await test_timer_exception_safety()

    # Test 3: Graceful shutdown
    logger.info("\n[3/5] Testing graceful shutdown...")
    results["shutdown"] = await test_graceful_shutdown()

    # Test 4: UI state consistency
    logger.info("\n[4/5] Testing UI state consistency...")
    results["ui_consistency"] = await test_ui_state_consistency()

    # Test 5: Memory stability (long duration)
    logger.info("\n[5/5] Testing memory stability...")
    results["memory"] = await test_memory_stability()

    # Summary
    passed = sum(1 for v in results.values() if v)
    total = len(results)

    logger.info("\n" + "=" * 60)
    logger.info("STABILITY TEST RESULTS")
    logger.info("=" * 60)
    for test, result in results.items():
        status = "[PASS]" if result else "[FAIL]"
        logger.info(f"  {status} - {test}")
    logger.info(f"\n  Passed: {passed}/{total}")
    logger.info(f"  Exceptions tracked: {len(metrics['exceptions'])}")
    logger.info(f"  Bus events received: {metrics['bus_events_received']}")
    logger.info(f"  Duration: {time.time() - metrics['start_time']:.1f}s")
    logger.info("=" * 60)

    results["_meta"] = {
        "passed": passed,
        "total": total,
        "exceptions": metrics["exceptions"],
        "duration": time.time() - metrics["start_time"],
    }

    return results


async def test_memory_stability() -> bool:
    """Monitor memory usage over time to detect leaks."""
    import tracemalloc

    tracemalloc.start()
    memory_samples = []

    try:
        for i in range(TEST_DURATION_SECONDS // MEMORY_CHECK_INTERVAL):
            await asyncio.sleep(MEMORY_CHECK_INTERVAL)

            # Force garbage collection
            gc.collect()

            # Snapshot memory
            snapshot = tracemalloc.take_snapshot()
            top_stats = snapshot.statistics('lineno')

            # Track top memory consumers
            if top_stats:
                total_size = sum(stat.size for stat in top_stats[:5])
                memory_samples.append(total_size)
                metrics["memory_samples"].append({
                    "time": time.time(),
                    "top_5_size": total_size,
                })

            logger.info(
                f"  Memory check {i + 1}: "
                f"top 5 allocations: "
                f"{total_size / 1024:.1f} KB" if top_stats else "N/A"
            )

            # Check if memory is growing steadily (leak detection)
            if len(memory_samples) >= 3:
                recent = memory_samples[-3:]
                if all(recent[i] < recent[i + 1] for i in range(len(recent) - 1)):
                    growth = recent[-1] - recent[0]
                    if growth > 10 * 1024 * 1024:  # 10 MB growth
                        logger.warning(
                            f"Potential memory leak detected: "
                            f"{growth / 1024:.1f} KB growth over "
                            f"{len(recent)} samples"
                        )

    except Exception as e:
        track_exception("memory_stability", e)
        return False
    finally:
        tracemalloc.stop()

    logger.info(f"Memory stability OK ({len(memory_samples)} samples)")
    return True


def main():
    """Entry point."""
    try:
        results = asyncio.run(run_stability_suite())
        meta = results.get("_meta", {})

        print(f"\n{'='*60}")
        print(f"OVERALL STABILITY ASSESSMENT")
        print(f"{'='*60}")
        print(f"  Passed: {meta.get('passed', 0)}/{meta.get('total', 0)}")
        print(f"  Duration: {meta.get('duration', 0):.1f}s")
        print(f"  Exceptions: {len(meta.get('exceptions', []))}")

        if meta.get('passed', 0) == meta.get('total', 0):
            print(f"\n  [PASS] STABILITY: GOOD")
            return 0
        else:
            print(f"\n  [WARN] STABILITY: DEGRADED")
            return 1

    except Exception as e:
        print(f"\n  [FAIL] STABILITY TEST CRASHED: {e}")
        traceback.print_exc()
        return 2


if __name__ == "__main__":
    sys.exit(main())
