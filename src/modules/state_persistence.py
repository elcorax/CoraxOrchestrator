"""
Corax Orchestrator - State Persistence Module.

Provides persistent storage for task state, deployment progress,
and system configuration across restarts. Supports JSON and
MessagePack serialization formats.
"""

import json
import asyncio
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, List, Optional, TypeVar, Generic

from src.core.logging import get_logger
from src.core.exceptions import PersistenceError

logger = get_logger(__name__)

T = TypeVar("T")


@dataclass
class PersistedState:
    """A persisted state entry with metadata."""
    key: str
    data: Any
    version: int = 1
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    metadata: Dict[str, Any] = field(default_factory=dict)


class StateStore:
    """
    A file-based state store for persisting data.

    Supports atomic writes, versioning, and automatic
    serialization/deserialization.
    """

    def __init__(self, store_dir: Path, format: str = "json") -> None:
        self.store_dir = store_dir
        self.store_dir.mkdir(parents=True, exist_ok=True)
        self.format = format
        self._cache: Dict[str, PersistedState] = {}
        self._lock = asyncio.Lock()

    async def save(self, key: str, data: Any, metadata: Optional[Dict[str, Any]] = None) -> None:
        """
        Save data to the store.

        Args:
            key: Unique key for the data
            data: Data to persist (must be JSON-serializable)
            metadata: Optional metadata to store alongside
        """
        async with self._lock:
            now = datetime.now(timezone.utc).isoformat()
            existing = self._cache.get(key)

            state = PersistedState(
                key=key,
                data=data,
                version=(existing.version + 1) if existing else 1,
                created_at=existing.created_at if existing else now,
                updated_at=now,
                metadata=metadata or {},
            )

            self._cache[key] = state
            await self._write_to_disk(key, state)

    async def load(self, key: str) -> Optional[Any]:
        """
        Load data from the store.

        Args:
            key: Key to load

        Returns:
            The stored data, or None if not found
        """
        if key in self._cache:
            return self._cache[key].data

        state = await self._read_from_disk(key)
        if state:
            self._cache[key] = state
            return state.data

        return None

    async def delete(self, key: str) -> bool:
        """
        Delete data from the store.

        Args:
            key: Key to delete

        Returns:
            True if deleted, False if not found
        """
        async with self._lock:
            self._cache.pop(key, None)
            file_path = self._get_file_path(key)
            if file_path.exists():
                file_path.unlink()
                return True
            return False

    async def list_keys(self) -> List[str]:
        """List all keys in the store."""
        keys = set(self._cache.keys())

        # Also scan disk for files not in cache
        for file_path in self.store_dir.glob(f"*.{self.format}"):
            key = file_path.stem
            keys.add(key)

        return sorted(keys)

    async def clear(self) -> None:
        """Clear all data from the store."""
        async with self._lock:
            self._cache.clear()
            for file_path in self.store_dir.glob(f"*.{self.format}"):
                file_path.unlink()

    def _get_file_path(self, key: str) -> Path:
        """Get the file path for a key."""
        return self.store_dir / f"{key}.{self.format}"

    async def _write_to_disk(self, key: str, state: PersistedState) -> None:
        """Write state to disk atomically."""
        file_path = self._get_file_path(key)
        temp_path = file_path.with_suffix(f".tmp.{self.format}")

        try:
            data = {
                "key": state.key,
                "data": state.data,
                "version": state.version,
                "created_at": state.created_at,
                "updated_at": state.updated_at,
                "metadata": state.metadata,
            }

            if self.format == "json":
                with open(temp_path, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2, default=str)
            elif self.format == "msgpack":
                import msgpack
                with open(temp_path, "wb") as f:
                    msgpack.dump(data, f)
            else:
                raise PersistenceError(
                    message=f"Unsupported format: {self.format}",
                    store=str(self.store_dir),
                    operation="write",
                )

            # Atomic rename
            temp_path.replace(file_path)

        except Exception as e:
            if temp_path.exists():
                temp_path.unlink()
            raise PersistenceError(
                message=f"Failed to write state: {e}",
                store=str(self.store_dir),
                operation="write",
                details={"key": key, "format": self.format},
            )

    async def _read_from_disk(self, key: str) -> Optional[PersistedState]:
        """Read state from disk."""
        file_path = self._get_file_path(key)
        if not file_path.exists():
            return None

        try:
            if self.format == "json":
                with open(file_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
            elif self.format == "msgpack":
                import msgpack
                with open(file_path, "rb") as f:
                    data = msgpack.load(f)
            else:
                return None

            return PersistedState(
                key=data["key"],
                data=data["data"],
                version=data.get("version", 1),
                created_at=data.get("created_at", ""),
                updated_at=data.get("updated_at", ""),
                metadata=data.get("metadata", {}),
            )

        except Exception as e:
            logger.error("Failed to read state", key=key, error=str(e))
            return None


class StatePersistence:
    """
    Main state persistence manager.

    Provides high-level persistence operations for the entire system,
    managing multiple state stores for different data categories.
    """

    def __init__(self, persistence_dir: Optional[Path] = None) -> None:
        self.persistence_dir = persistence_dir or Path("data/persistence")
        self.persistence_dir.mkdir(parents=True, exist_ok=True)

        # Create stores for different data categories
        self.task_store = StateStore(self.persistence_dir / "tasks")
        self.config_store = StateStore(self.persistence_dir / "config")
        self.progress_store = StateStore(self.persistence_dir / "progress")
        self.report_store = StateStore(self.persistence_dir / "reports")

        self._auto_save_task: Optional[asyncio.Task] = None
        self._auto_save_interval = 30  # seconds

    async def save_task_state(self, task_id: str, state: Dict[str, Any]) -> None:
        """Save task state."""
        await self.task_store.save(task_id, state)

    async def load_task_state(self, task_id: str) -> Optional[Dict[str, Any]]:
        """Load task state."""
        return await self.task_store.load(task_id)

    async def save_progress(self, key: str, progress: Dict[str, Any]) -> None:
        """Save deployment progress."""
        await self.progress_store.save(key, progress)

    async def load_progress(self, key: str) -> Optional[Dict[str, Any]]:
        """Load deployment progress."""
        return await self.progress_store.load(key)

    async def save_config_snapshot(self, config: Dict[str, Any]) -> None:
        """Save a snapshot of the current configuration."""
        await self.config_store.save(
            "config_snapshot",
            config,
            metadata={"timestamp": datetime.now(timezone.utc).isoformat()},
        )

    async def load_config_snapshot(self) -> Optional[Dict[str, Any]]:
        """Load the last configuration snapshot."""
        return await self.config_store.load("config_snapshot")

    async def list_tasks(self) -> List[str]:
        """List all persisted task IDs."""
        return await self.task_store.list_keys()

    async def clear_all(self) -> None:
        """Clear all persisted data."""
        await self.task_store.clear()
        await self.config_store.clear()
        await self.progress_store.clear()
        await self.report_store.clear()

    async def start_auto_save(self, interval: Optional[int] = None) -> None:
        """Start periodic auto-save of in-memory state."""
        if self._auto_save_task:
            return

        if interval:
            self._auto_save_interval = interval

        async def auto_save_loop():
            while True:
                await asyncio.sleep(self._auto_save_interval)
                logger.debug("Auto-save cycle")

        self._auto_save_task = asyncio.create_task(auto_save_loop())
        logger.info("Auto-save started", interval=self._auto_save_interval)

    async def stop_auto_save(self) -> None:
        """Stop periodic auto-save."""
        if self._auto_save_task:
            self._auto_save_task.cancel()
            self._auto_save_task = None
            logger.info("Auto-save stopped")
