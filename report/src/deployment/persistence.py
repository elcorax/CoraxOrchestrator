"""
Corax Orchestrator - Deployment Persistence Layer.

Provides persistent storage for deployment state, repair history,
operation records, and checkpoint management across reboots.

Key capabilities:
- Repair history persistence & retrieval
- Deployment checkpoint save/load/resume
- Operation record persistence
- Automatic cleanup of old records
"""

from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
from pathlib import Path
import json
import os
import time
import threading

from src.core.logging import get_logger

logger = get_logger(__name__)

# Global persistence directory
_PERSISTENCE_DIR = Path("data/persistence")
_REPAIR_HISTORY_FILE = _PERSISTENCE_DIR / "repair_history.json"
_MAX_REPAIR_HISTORY = 200
_lock = threading.Lock()


def _ensure_dir() -> None:
    """Ensure the persistence directory exists."""
    _PERSISTENCE_DIR.mkdir(parents=True, exist_ok=True)


def save_repair_history(entry: Dict[str, Any]) -> None:
    """
    Save a repair activity to persistent history.

    Args:
        entry: Repair activity dict with keys:
            - timestamp: ISO timestamp
            - component: Component name
            - action: Action taken
            - status: Result status
            - message: Description
    """
    _ensure_dir()
    with _lock:
        try:
            history = []
            if _REPAIR_HISTORY_FILE.exists():
                with open(_REPAIR_HISTORY_FILE, "r", encoding="utf-8") as f:
                    history = json.load(f)

            if "timestamp" not in entry:
                entry["timestamp"] = datetime.now(timezone.utc).isoformat()

            history.insert(0, entry)

            # Trim to max
            if len(history) > _MAX_REPAIR_HISTORY:
                history = history[:_MAX_REPAIR_HISTORY]

            with open(_REPAIR_HISTORY_FILE, "w", encoding="utf-8") as f:
                json.dump(history, f, indent=2, default=str)

            logger.debug("Repair history saved", component=entry.get("component", "unknown"))
        except Exception as e:
            logger.warning("Failed to save repair history", error=str(e))


def get_repair_history(max_count: int = 100) -> List[Dict[str, Any]]:
    """
    Get persisted repair history.

    Args:
        max_count: Maximum entries to return

    Returns:
        List of repair activity dicts, newest first
    """
    _ensure_dir()
    with _lock:
        try:
            if not _REPAIR_HISTORY_FILE.exists():
                return []
            with open(_REPAIR_HISTORY_FILE, "r", encoding="utf-8") as f:
                history = json.load(f)
            return history[:max_count]
        except Exception as e:
            logger.warning("Failed to load repair history", error=str(e))
            return []


def save_deployment_checkpoint(state: Dict[str, Any]) -> Optional[str]:
    """
    Save a deployment checkpoint for reboot recovery.

    Args:
        state: Checkpoint state dict

    Returns:
        Path to saved checkpoint file, or None on failure
    """
    _ensure_dir()
    try:
        checkpoint_id = int(time.time())
        filename = f"deploy_checkpoint_{checkpoint_id}.json"
        path = _PERSISTENCE_DIR / filename

        state["_checkpoint_id"] = checkpoint_id
        state["_saved_at"] = datetime.now(timezone.utc).isoformat()

        with open(path, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2, default=str)

        logger.info("Deployment checkpoint saved", path=str(path))
        return str(path)
    except Exception as e:
        logger.warning("Failed to save checkpoint", error=str(e))
        return None


def load_latest_checkpoint() -> Optional[Dict[str, Any]]:
    """
    Load the latest deployment checkpoint.

    Returns:
        Checkpoint state dict, or None if no valid checkpoint exists
    """
    _ensure_dir()
    try:
        checkpoints = sorted(
            _PERSISTENCE_DIR.glob("deploy_checkpoint_*.json"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        if not checkpoints:
            return None

        latest = checkpoints[0]
        with open(latest, "r", encoding="utf-8") as f:
            state = json.load(f)

        # Check if stale (> 24 hours old)
        checkpoint_time = latest.stat().st_mtime
        if time.time() - checkpoint_time > 86400:
            logger.info("Checkpoint is too old (>24h), starting fresh")
            return None

        logger.info("Checkpoint loaded", path=str(latest))
        return state
    except Exception as e:
        logger.warning("Failed to load checkpoint", error=str(e))
        return None


def clear_checkpoints() -> None:
    """Clear all deployment checkpoints after successful completion."""
    _ensure_dir()
    try:
        for f in _PERSISTENCE_DIR.glob("deploy_checkpoint_*.json"):
            f.unlink(missing_ok=True)
        logger.info("All deployment checkpoints cleared")
    except Exception as e:
        logger.warning("Failed to clear checkpoints", error=str(e))


def save_operation_record(record: Dict[str, Any]) -> None:
    """
    Save a single operation record to persistent storage.

    Args:
        record: Operation record dict
    """
    _ensure_dir()
    try:
        op_id = record.get("op_id", f"OP-{int(time.time())}")
        filename = f"operation_{op_id}.json"
        path = _PERSISTENCE_DIR / filename

        with open(path, "w", encoding="utf-8") as f:
            json.dump(record, f, indent=2, default=str)
    except Exception as e:
        logger.warning("Failed to save operation record", error=str(e))


def get_operation_history(max_count: int = 50) -> List[Dict[str, Any]]:
    """
    Get persisted operation records.

    Args:
        max_count: Maximum entries to return

    Returns:
        List of operation record dicts, newest first
    """
    _ensure_dir()
    try:
        records = []
        for f in sorted(
            _PERSISTENCE_DIR.glob("operation_*.json"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )[:max_count]:
            try:
                with open(f, "r", encoding="utf-8") as fh:
                    records.append(json.load(fh))
            except Exception:
                continue
        return records
    except Exception as e:
        logger.warning("Failed to load operation history", error=str(e))
        return []


def list_persisted_sessions() -> List[Dict[str, Any]]:
    """
    List all persisted deployment sessions.

    Returns:
        List of session summary dicts
    """
    _ensure_dir()
    sessions = []
    try:
        for f in sorted(
            _PERSISTENCE_DIR.glob("deployment_state_*.json"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        ):
            try:
                with open(f, "r", encoding="utf-8") as fh:
                    state = json.load(fh)
                    sessions.append({
                        "file": f.name,
                        "timestamp": state.get("_saved_at", ""),
                        "deployment_id": state.get("deployment_id", ""),
                        "status": state.get("status", "unknown"),
                        "tools_total": state.get("tools_total", 0),
                        "tools_installed": state.get("tools_installed", 0),
                        "tools_failed": state.get("tools_failed", 0),
                    })
            except Exception:
                continue
    except Exception as e:
        logger.warning("Failed to list persisted sessions", error=str(e))

    return sessions


def cleanup_old_records(max_age_hours: int = 168) -> int:
    """
    Delete records older than max_age_hours.

    Args:
        max_age_hours: Maximum age in hours (default 7 days)

    Returns:
        Number of records cleaned up
    """
    _ensure_dir()
    cutoff = time.time() - (max_age_hours * 3600)
    count = 0

    try:
        for f in _PERSISTENCE_DIR.glob("*.json"):
            try:
                if f.stat().st_mtime < cutoff:
                    f.unlink()
                    count += 1
            except Exception:
                continue
        if count > 0:
            logger.info("Cleaned up old persistence records", count=count)
    except Exception as e:
        logger.warning("Failed to clean up old records", error=str(e))

    return count
