"""
Corax Orchestrator - Runtime Recovery.

Provides crash recovery and restart support for the agent runtime.
Manages recovery points, state snapshots, and automatic restart
after failures or system restarts.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Set
from pathlib import Path
import json
import asyncio
from uuid import uuid4

from src.core.logging import get_logger
from src.core.exceptions import PersistenceError

logger = get_logger(__name__)


@dataclass
class RecoveryPoint:
    """
    A snapshot of runtime state for recovery purposes.

    Recovery points capture enough state to resume execution
    after a crash or restart.
    """
    point_id: str
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    session_id: Optional[str] = None
    workflow_id: Optional[str] = None
    current_step: Optional[str] = None
    lifecycle_state: str = "created"
    mode: str = "safe"
    variables: Dict[str, Any] = field(default_factory=dict)
    context: Dict[str, Any] = field(default_factory=dict)
    pending_actions: List[Dict[str, Any]] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "point_id": self.point_id,
            "timestamp": self.timestamp,
            "session_id": self.session_id,
            "workflow_id": self.workflow_id,
            "current_step": self.current_step,
            "lifecycle_state": self.lifecycle_state,
            "mode": self.mode,
            "variables": self.variables,
            "context": self.context,
            "pending_actions": self.pending_actions,
            "metadata": self.metadata,
        }


class RuntimeRecovery:
    """
    Manages runtime recovery and restart support.

    Features:
    - Automatic recovery point creation at configurable intervals
    - Crash detection on startup
    - State restoration from last recovery point
    - Recovery point pruning (keep last N)
    - Manual checkpoint creation
    - Recovery point integrity validation
    """

    def __init__(
        self,
        recovery_dir: Optional[Path] = None,
        auto_save_interval: int = 30,
        max_recovery_points: int = 10,
    ) -> None:
        self.recovery_dir = recovery_dir or Path("data/persistence/recovery")
        self.recovery_dir.mkdir(parents=True, exist_ok=True)
        self.auto_save_interval = auto_save_interval
        self.max_recovery_points = max_recovery_points
        self._current_point: Optional[RecoveryPoint] = None
        self._auto_save_task: Optional[asyncio.Task] = None
        self._running: bool = False
        self._lock = asyncio.Lock()

    async def start_auto_save(self) -> None:
        """Start the automatic recovery point saving loop."""
        if self._running:
            return
        self._running = True
        self._auto_save_task = asyncio.create_task(self._auto_save_loop())
        logger.info("Auto-save started", interval=self.auto_save_interval)

    async def stop_auto_save(self) -> None:
        """Stop the automatic recovery point saving loop."""
        self._running = False
        if self._auto_save_task:
            self._auto_save_task.cancel()
            try:
                await self._auto_save_task
            except asyncio.CancelledError:
                pass
        logger.info("Auto-save stopped")

    async def save_recovery_point(
        self,
        session_id: Optional[str] = None,
        workflow_id: Optional[str] = None,
        current_step: Optional[str] = None,
        lifecycle_state: str = "idle",
        mode: str = "safe",
        variables: Optional[Dict[str, Any]] = None,
        context: Optional[Dict[str, Any]] = None,
        pending_actions: Optional[List[Dict[str, Any]]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> RecoveryPoint:
        """
        Create and persist a recovery point.

        Args:
            session_id: Current session ID
            workflow_id: Current workflow ID
            current_step: Current step being executed
            lifecycle_state: Current lifecycle state
            mode: Current agent mode
            variables: Workflow variables
            context: Execution context
            pending_actions: Actions waiting for approval
            metadata: Additional metadata

        Returns:
            The created RecoveryPoint
        """
        point = RecoveryPoint(
            point_id=str(uuid4()),
            session_id=session_id,
            workflow_id=workflow_id,
            current_step=current_step,
            lifecycle_state=lifecycle_state,
            mode=mode,
            variables=variables or {},
            context=context or {},
            pending_actions=pending_actions or [],
            metadata=metadata or {},
        )

        async with self._lock:
            self._current_point = point
            await self._persist_recovery_point(point)
            await self._prune_old_points()

        logger.debug(
            "Recovery point saved",
            point_id=point.point_id,
            state=lifecycle_state,
        )

        return point

    async def load_latest_recovery_point(self) -> Optional[RecoveryPoint]:
        """
        Load the most recent recovery point.

        Returns:
            The latest RecoveryPoint, or None if none exist
        """
        points = self.list_recovery_points()
        if not points:
            return None

        latest = points[-1]
        point = await self._load_recovery_point(latest)
        if point:
            self._current_point = point
        return point

    def list_recovery_points(self) -> List[str]:
        """List all available recovery point IDs, ordered by time."""
        files = sorted(
            self.recovery_dir.glob("recovery_*.json"),
            key=lambda f: f.stat().st_mtime,
        )
        return [f.stem.replace("recovery_", "") for f in files]

    async def delete_recovery_point(self, point_id: str) -> bool:
        """Delete a specific recovery point."""
        point_path = self.recovery_dir / f"recovery_{point_id}.json"
        if point_path.exists():
            point_path.unlink()
            logger.info("Recovery point deleted", point_id=point_id)
            return True
        return False

    async def clear_all_recovery_points(self) -> int:
        """Delete all recovery points."""
        count = 0
        for f in self.recovery_dir.glob("recovery_*.json"):
            f.unlink()
            count += 1
        self._current_point = None
        logger.info("All recovery points cleared", count=count)
        return count

    def has_recovery_point(self) -> bool:
        """Check if any recovery points exist."""
        return len(self.list_recovery_points()) > 0

    def get_current_recovery_point(self) -> Optional[RecoveryPoint]:
        """Get the current in-memory recovery point."""
        return self._current_point

    def get_recovery_info(self) -> Dict[str, Any]:
        """Get recovery system information."""
        points = self.list_recovery_points()
        return {
            "has_recovery_point": len(points) > 0,
            "recovery_point_count": len(points),
            "auto_save_running": self._running,
            "auto_save_interval": self.auto_save_interval,
            "max_recovery_points": self.max_recovery_points,
            "recovery_dir": str(self.recovery_dir),
            "latest_point_id": points[-1] if points else None,
        }

    async def _auto_save_loop(self) -> None:
        """Periodically save recovery points."""
        while self._running:
            try:
                await asyncio.sleep(self.auto_save_interval)
                if self._current_point:
                    async with self._lock:
                        await self._persist_recovery_point(self._current_point)
                        await self._prune_old_points()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Auto-save error", error=str(e))

    async def _persist_recovery_point(self, point: RecoveryPoint) -> None:
        """Persist a recovery point to disk."""
        point_path = self.recovery_dir / f"recovery_{point.point_id}.json"
        temp_path = point_path.with_suffix(".tmp.json")

        try:
            with open(temp_path, "w", encoding="utf-8") as f:
                json.dump(point.to_dict(), f, indent=2, default=str)
            temp_path.replace(point_path)
        except Exception as e:
            if temp_path.exists():
                temp_path.unlink()
            raise PersistenceError(
                message=f"Failed to persist recovery point: {e}",
                store=str(self.recovery_dir),
                operation="write",
            )

    async def _load_recovery_point(self, point_id: str) -> Optional[RecoveryPoint]:
        """Load a recovery point from disk."""
        point_path = self.recovery_dir / f"recovery_{point_id}.json"
        if not point_path.exists():
            return None

        try:
            with open(point_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            return RecoveryPoint(
                point_id=data["point_id"],
                timestamp=data.get("timestamp", ""),
                session_id=data.get("session_id"),
                workflow_id=data.get("workflow_id"),
                current_step=data.get("current_step"),
                lifecycle_state=data.get("lifecycle_state", "created"),
                mode=data.get("mode", "safe"),
                variables=data.get("variables", {}),
                context=data.get("context", {}),
                pending_actions=data.get("pending_actions", []),
                metadata=data.get("metadata", {}),
            )
        except Exception as e:
            logger.error(
                "Failed to load recovery point",
                point_id=point_id,
                error=str(e),
            )
            return None

    async def _prune_old_points(self) -> None:
        """Remove old recovery points beyond the maximum."""
        points = sorted(
            self.recovery_dir.glob("recovery_*.json"),
            key=lambda f: f.stat().st_mtime,
        )
        while len(points) > self.max_recovery_points:
            oldest = points.pop(0)
            oldest.unlink()
            logger.debug("Pruned old recovery point", path=str(oldest))
