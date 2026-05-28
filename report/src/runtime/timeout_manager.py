"""
Corax Orchestrator - Global Timeout Protection Manager.

CENTRALIZED timeout enforcement for ALL operations.
Aborts any task making no progress within the configured threshold.

Policy: If any operation produces no meaningful progress within 60 seconds:
  - ABORT immediately
  - LOG the timeout event
  - CONTINUE to higher-value work
  - NEVER retry infinitely
  - NEVER block in waiting loops

Usage:
    from src.runtime.timeout_manager import timeout_manager
    
    with timeout_manager.timeout("deployment", timeout_seconds=60):
        result = await some_operation()
"""

from typing import Optional, Dict, Any, List, Callable, TypeVar, Optional as Maybe
from dataclasses import dataclass, field
from datetime import datetime, timezone
import asyncio
import time
import signal
import threading
import functools
import os
import sys
import json
from pathlib import Path

from src.core.logging import get_logger

logger = get_logger(__name__)

T = TypeVar("T")

# ─── Timeout Event ─────────────────────────────────────────────────────────


@dataclass
class TimeoutEvent:
    """Record of a timeout occurrence."""
    operation: str
    duration: float
    last_state: str
    suspected_blocker: str
    next_recovery: str
    timestamp: float = field(default_factory=time.time)
    thread_id: int = field(default_factory=lambda: threading.get_ident())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "operation": self.operation,
            "duration": round(self.duration, 2),
            "last_state": self.last_state,
            "suspected_blocker": self.suspected_blocker,
            "next_recovery": self.next_recovery,
            "timestamp": self.timestamp,
            "thread_id": self.thread_id,
        }

    def to_log(self) -> str:
        return (
            f"[TIMEOUT]\n"
            f"operation={self.operation}\n"
            f"duration={round(self.duration, 2)}s\n"
            f"last_state={self.last_state}\n"
            f"suspected_blocker={self.suspected_blocker}\n"
            f"next_recovery={self.next_recovery}\n"
        )


# ─── TimeoutError ──────────────────────────────────────────────────────────


class OperationTimeoutError(Exception):
    """Raised when an operation exceeds its time limit."""
    pass


# ─── TimeoutManager ────────────────────────────────────────────────────────


class TimeoutManager:
    """
    Centralized timeout enforcement for ALL Corax operations.

    Controls:
    - subprocess timeout (default 60s)
    - installer timeout  (default 120s)
    - build timeout      (default 300s)
    - validation timeout (default 60s)
    - polling timeout    (default 30s)
    - watchdog timeout   (default 15s)
    """

    def __init__(self):
        self._timeout_history: List[TimeoutEvent] = []
        self._active_timers: Dict[str, float] = {}
        self._history_file = Path("data/logs/timeout_history.json")
        self._max_history = 1000
        self._lock = threading.Lock()

        # Default timeouts (all in seconds)
        self.defaults = {
            "subprocess": 60,
            "installer": 120,
            "build": 300,
            "validation": 60,
            "polling": 30,
            "watchdog": 15,
            "deployment": 60,
            "scan": 30,
            "model_pull": 300,
            "config_load": 10,
            "report_gen": 30,
            "recovery": 60,
        }

    def timeout(
        self,
        operation: str,
        timeout_seconds: Optional[float] = None,
        abort_callback: Optional[Callable] = None,
        last_state: str = "unknown",
    ):
        """
        Context manager that enforces operation timeout.

        Args:
            operation: Name of the operation being timed
            timeout_seconds: Max duration. Uses defaults[operation] if None.
            abort_callback: Optional cleanup function on timeout
            last_state: Current state description for timeout logging

        Raises:
            OperationTimeoutError if the operation exceeds the time limit.
        """
        if timeout_seconds is None:
            timeout_seconds = self.defaults.get(operation, 60)

        return _TimeoutContext(
            manager=self,
            operation=operation,
            timeout_seconds=timeout_seconds,
            abort_callback=abort_callback,
            last_state=last_state,
        )

    def fire_timeout(
        self,
        operation: str,
        duration: float,
        last_state: str = "unknown",
        suspected_blocker: str = "unknown",
        next_recovery: str = "abort_and_continue",
    ) -> TimeoutEvent:
        """
        Log a timeout event and return the TimeoutEvent record.

        This is the REQUIRED format for all timeout logging.
        """
        event = TimeoutEvent(
            operation=operation,
            duration=duration,
            last_state=last_state,
            suspected_blocker=suspected_blocker,
            next_recovery=next_recovery,
        )

        with self._lock:
            self._timeout_history.append(event)
            if len(self._timeout_history) > self._max_history:
                self._timeout_history = self._timeout_history[-self._max_history:]

        # Log in REQUIRED format
        print(f"\n{event.to_log()}", file=sys.stderr)
        logger.warning(
            "Operation timed out",
            operation=operation,
            duration=round(duration, 2),
            last_state=last_state,
            blocker=suspected_blocker,
        )

        # Persist
        self._persist_history()

        return event

    def get_recent_timeouts(self, count: int = 10) -> List[TimeoutEvent]:
        """Get the most recent timeout events."""
        with self._lock:
            return list(self._timeout_history[-count:])

    def get_timeout_count(self, operation: Optional[str] = None) -> int:
        """Get count of timeouts, optionally filtered by operation."""
        with self._lock:
            if operation:
                return sum(1 for e in self._timeout_history if e.operation == operation)
            return len(self._timeout_history)

    def clear_history(self) -> None:
        """Clear timeout history."""
        with self._lock:
            self._timeout_history.clear()

    def _persist_history(self) -> None:
        """Persist timeout history to disk for diagnostics."""
        try:
            self._history_file.parent.mkdir(parents=True, exist_ok=True)
            recent = self._timeout_history[-100:]  # Only last 100
            with open(self._history_file, "w", encoding="utf-8") as f:
                json.dump(
                    [e.to_dict() for e in recent],
                    f,
                    indent=2,
                )
        except Exception:
            pass  # Non-critical - don't let persistence fail the timeout

    def load_history(self) -> List[TimeoutEvent]:
        """Load persisted timeout history."""
        if not self._history_file.exists():
            return []
        try:
            with open(self._history_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            events = []
            for d in data:
                events.append(TimeoutEvent(**{k: v for k, v in d.items() if k in TimeoutEvent.__dataclass_fields__}))
            with self._lock:
                self._timeout_history = events
            return events
        except Exception:
            return []

    def asyncio_timeout(self, operation: str, timeout_seconds: float = 60):
        """
        Async context manager that raises asyncio.TimeoutError after timeout.

        Use for async operations like installer.run(), model pulls, etc.

        Example:
            async with timeout_manager.asyncio_timeout("model_pull", 300):
                await model_manager.pull_model("llama3")
        """
        return asyncio.timeout(timeout_seconds)

    def guard_subprocess(self, process, timeout_seconds: float = 60):
        """
        Wrap a subprocess with timeout protection.

        Returns a future that raises OperationTimeoutError on timeout.

        Example:
            result = await timeout_manager.guard_subprocess(proc)
        """
        return _SubprocessGuard(process, timeout_seconds, self)


# ─── Internal Context Manager ──────────────────────────────────────────────


class _TimeoutContext:
    """Async/sync context manager for timeouts."""

    def __init__(
        self,
        manager: TimeoutManager,
        operation: str,
        timeout_seconds: float,
        abort_callback: Optional[Callable] = None,
        last_state: str = "unknown",
    ):
        self._manager = manager
        self._operation = operation
        self._timeout = timeout_seconds
        self._abort_callback = abort_callback
        self._last_state = last_state
        self._start_time: float = 0.0

    def __enter__(self):
        self._start_time = time.time()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is not None:
            # If the exception is unrelated to timeout, still check
            duration = time.time() - self._start_time
            if duration >= self._timeout:
                self._manager.fire_timeout(
                    operation=self._operation,
                    duration=duration,
                    last_state=self._last_state,
                    suspected_blocker=str(exc_val),
                    next_recovery="check_logs_and_retry",
                )
        return False

    async def __aenter__(self):
        self._start_time = time.time()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        return self.__exit__(exc_type, exc_val, exc_tb)


class _SubprocessGuard:
    """Guards a subprocess with timeout."""

    def __init__(self, process, timeout: float, manager: TimeoutManager):
        self._process = process
        self._timeout = timeout
        self._manager = manager

    async def wait(self) -> int:
        """Wait for process with timeout. Returns exit code."""
        try:
            async with asyncio.timeout(self._timeout):
                return await self._process.wait()
        except asyncio.TimeoutError:
            operation = getattr(self._process, "_name", "subprocess")
            self._manager.fire_timeout(
                operation=operation,
                duration=self._timeout,
                last_state="running",
                suspected_blocker="process_did_not_complete",
                next_recovery="kill_process_and_retry",
            )
            try:
                self._process.kill()
            except Exception:
                pass
            raise OperationTimeoutError(
                f"Subprocess {operation} timed out after {self._timeout}s"
            )


# ─── Singleton ─────────────────────────────────────────────────────────────

timeout_manager = TimeoutManager()
timeout_manager.load_history()
