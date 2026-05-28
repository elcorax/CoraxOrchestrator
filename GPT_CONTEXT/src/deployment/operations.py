"""
Corax Orchestrator - Operation Tracking System.

Provides comprehensive operation tracking across the entire deployment
architecture. Every deployment action receives a unique operation ID
with parent-child relationships for full traceability.

Operation ID Format:
  DEP-{NNNNNN}  - Deployment session
  OP-{NNNNNN}   - Individual operation
  REC-{NNNNNN}  - Recovery action
  RETRY-{NNNNN} - Retry attempt
  CHK-{NNNNNN}  - Validation check
  ENV-{NNNNNN}  - Environment modification
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, Any, List, Optional, Callable, Awaitable
import asyncio
import time
import os
import json
from pathlib import Path

from src.core.logging import get_logger

logger = get_logger(__name__)

# Global counter for ID generation
_id_counters: Dict[str, int] = {}


def _generate_id(prefix: str) -> str:
    """Generate a unique operation ID with the given prefix."""
    global _id_counters
    _id_counters[prefix] = _id_counters.get(prefix, 0) + 1
    return f"{prefix}-{_id_counters[prefix]:06d}"


class OperationType(Enum):
    """Types of tracked operations."""
    DEPLOYMENT = "deployment"
    INSTALLER = "installer"
    COMMAND = "command"
    RETRY = "retry"
    RECOVERY = "recovery"
    ENV_MODIFICATION = "env_modification"
    PATH_CHANGE = "path_change"
    SERVICE_OP = "service_operation"
    MODEL_DOWNLOAD = "model_download"
    VALIDATION = "validation"
    PERMISSION = "permission"
    DOWNLOAD = "download"
    CONFIGURATION = "configuration"
    VERIFICATION = "verification"
    REPORTING = "reporting"


class OperationStatus(Enum):
    """Status of a tracked operation."""
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    SKIPPED = "skipped"
    CANCELLED = "cancelled"
    RETRYING = "retrying"


class FailureCategory(Enum):
    """Classification of operation failures."""
    TEMPORARY = "temporary"
    PERMISSION = "permission"
    NETWORK = "network"
    COMPATIBILITY = "compatibility"
    DISK_SPACE = "disk_space"
    DEPENDENCY = "dependency"
    TIMEOUT = "timeout"
    CORRUPTION = "corruption"
    UNKNOWN = "unknown"


@dataclass
class OperationRecord:
    """
    Complete record of a tracked operation.

    Attributes:
        op_id: Unique operation identifier
        op_type: Type of operation
        parent_op_id: Parent operation ID for nesting
        session_id: Deployment session ID
        name: Human-readable operation name
        tool_key: Associated tool key (if applicable)
        status: Current operation status
        started_at: Start timestamp
        completed_at: Completion timestamp
        duration_ms: Execution duration
        error: Error message if failed
        failure_category: Classification of failure
        retry_of: Operation ID this is a retry of
        retry_attempt: Retry attempt number
        details: Additional operation details
        result_data: Operation result data
        child_op_ids: Child operation IDs
    """
    op_id: str
    op_type: OperationType
    parent_op_id: Optional[str] = None
    session_id: Optional[str] = None
    name: str = ""
    tool_key: Optional[str] = None
    status: OperationStatus = OperationStatus.PENDING
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    duration_ms: float = 0.0
    error: Optional[str] = None
    failure_category: Optional[FailureCategory] = None
    retry_of: Optional[str] = None
    retry_attempt: int = 0
    details: Dict[str, Any] = field(default_factory=dict)
    result_data: Dict[str, Any] = field(default_factory=dict)
    child_op_ids: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "op_id": self.op_id,
            "op_type": self.op_type.value,
            "parent_op_id": self.parent_op_id,
            "session_id": self.session_id,
            "name": self.name,
            "tool_key": self.tool_key,
            "status": self.status.value,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "duration_ms": self.duration_ms,
            "error": self.error,
            "failure_category": self.failure_category.value if self.failure_category else None,
            "retry_of": self.retry_of,
            "retry_attempt": self.retry_attempt,
            "details": self.details,
            "result_data": self.result_data,
            "child_op_ids": self.child_op_ids,
        }


class OperationTracker:
    """
    Tracks all deployment operations with full traceability.

    Provides operation ID generation, parent-child relationships,
    timing, failure classification, and export for reporting.
    """

    def __init__(self) -> None:
        self._records: Dict[str, OperationRecord] = {}
        self._session_id: Optional[str] = None
        self._current_op_stack: List[str] = []

    def start_session(self) -> str:
        """Start a new deployment session."""
        self._session_id = _generate_id("DEP")
        self._records.clear()
        self._current_op_stack = []
        logger.info("Operation session started", session_id=self._session_id)
        return self._session_id

    def get_session_id(self) -> Optional[str]:
        """Get the current session ID."""
        return self._session_id

    def start_operation(
        self,
        op_type: OperationType,
        name: str,
        tool_key: Optional[str] = None,
        parent_op_id: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Start tracking a new operation.

        Args:
            op_type: Type of operation
            name: Human-readable name
            tool_key: Associated tool key
            parent_op_id: Parent operation ID (auto-detected from stack if None)
            details: Additional details

        Returns:
            Operation ID
        """
        op_id = _generate_id("OP")
        parent = parent_op_id or (self._current_op_stack[-1] if self._current_op_stack else None)

        record = OperationRecord(
            op_id=op_id,
            op_type=op_type,
            parent_op_id=parent,
            session_id=self._session_id,
            name=name,
            tool_key=tool_key,
            status=OperationStatus.RUNNING,
            started_at=datetime.now(timezone.utc).isoformat(),
            details=details or {},
        )

        self._records[op_id] = record

        # Link to parent
        if parent and parent in self._records:
            self._records[parent].child_op_ids.append(op_id)

        self._current_op_stack.append(op_id)
        logger.debug("Operation started", op_id=op_id, name=name, type=op_type.value)
        return op_id

    def finish_operation(
        self,
        op_id: str,
        status: OperationStatus,
        error: Optional[str] = None,
        failure_category: Optional[FailureCategory] = None,
        result_data: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Mark an operation as completed.

        Args:
            op_id: Operation ID to finish
            status: Final status
            error: Error message if failed
            failure_category: Failure classification
            result_data: Result data
        """
        record = self._records.get(op_id)
        if not record:
            logger.warning("Operation not found for finish", op_id=op_id)
            return

        record.status = status
        record.completed_at = datetime.now(timezone.utc).isoformat()
        record.error = error
        record.failure_category = failure_category
        if result_data:
            record.result_data = result_data

        # Calculate duration
        if record.started_at:
            try:
                start = datetime.fromisoformat(record.started_at)
                end = datetime.fromisoformat(record.completed_at)
                record.duration_ms = (end - start).total_seconds() * 1000
            except Exception:
                pass

        # Pop from stack if on top
        if self._current_op_stack and self._current_op_stack[-1] == op_id:
            self._current_op_stack.pop()

        logger.debug(
            "Operation finished",
            op_id=op_id,
            status=status.value,
            duration_ms=round(record.duration_ms, 1),
        )

    def fail_operation(
        self,
        op_id: str,
        error: str,
        failure_category: FailureCategory = FailureCategory.UNKNOWN,
        result_data: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Mark an operation as failed."""
        self.finish_operation(
            op_id=op_id,
            status=OperationStatus.FAILED,
            error=error,
            failure_category=failure_category,
            result_data=result_data,
        )

    def start_retry(
        self,
        original_op_id: str,
        attempt: int,
    ) -> str:
        """
        Start a retry operation linked to the original.

        Args:
            original_op_id: Original failed operation ID
            attempt: Retry attempt number

        Returns:
            Retry operation ID
        """
        original = self._records.get(original_op_id)
        retry_id = _generate_id("RETRY")

        record = OperationRecord(
            op_id=retry_id,
            op_type=OperationType.RETRY,
            parent_op_id=original_op_id,
            session_id=self._session_id,
            name=f"Retry {original.name if original else 'operation'} (attempt {attempt})",
            tool_key=original.tool_key if original else None,
            status=OperationStatus.RUNNING,
            started_at=datetime.now(timezone.utc).isoformat(),
            retry_of=original_op_id,
            retry_attempt=attempt,
            details={"original_status": original.status.value if original else "unknown"},
        )

        self._records[retry_id] = record
        self._current_op_stack.append(retry_id)
        return retry_id

    def start_recovery(
        self,
        name: str,
        tool_key: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Start a recovery operation."""
        rec_id = _generate_id("REC")
        parent = self._current_op_stack[-1] if self._current_op_stack else None

        record = OperationRecord(
            op_id=rec_id,
            op_type=OperationType.RECOVERY,
            parent_op_id=parent,
            session_id=self._session_id,
            name=name,
            tool_key=tool_key,
            status=OperationStatus.RUNNING,
            started_at=datetime.now(timezone.utc).isoformat(),
            details=details or {},
        )

        self._records[rec_id] = record
        if parent and parent in self._records:
            self._records[parent].child_op_ids.append(rec_id)

        self._current_op_stack.append(rec_id)
        return rec_id

    def start_validation(
        self,
        name: str,
        tool_key: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Start a validation/check operation."""
        chk_id = _generate_id("CHK")
        parent = self._current_op_stack[-1] if self._current_op_stack else None

        record = OperationRecord(
            op_id=chk_id,
            op_type=OperationType.VALIDATION,
            parent_op_id=parent,
            session_id=self._session_id,
            name=name,
            tool_key=tool_key,
            status=OperationStatus.RUNNING,
            started_at=datetime.now(timezone.utc).isoformat(),
            details=details or {},
        )

        self._records[chk_id] = record
        if parent and parent in self._records:
            self._records[parent].child_op_ids.append(chk_id)

        self._current_op_stack.append(chk_id)
        return chk_id

    def start_env_modification(
        self,
        name: str,
        tool_key: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Start an environment modification operation."""
        env_id = _generate_id("ENV")
        parent = self._current_op_stack[-1] if self._current_op_stack else None

        record = OperationRecord(
            op_id=env_id,
            op_type=OperationType.ENV_MODIFICATION,
            parent_op_id=parent,
            session_id=self._session_id,
            name=name,
            tool_key=tool_key,
            status=OperationStatus.RUNNING,
            started_at=datetime.now(timezone.utc).isoformat(),
            details=details or {},
        )

        self._records[env_id] = record
        if parent and parent in self._records:
            self._records[parent].child_op_ids.append(env_id)

        self._current_op_stack.append(env_id)
        return env_id

    def get_operation(self, op_id: str) -> Optional[OperationRecord]:
        """Get an operation record by ID."""
        return self._records.get(op_id)

    def get_operations_by_session(self, session_id: str) -> List[OperationRecord]:
        """Get all operations for a session."""
        return [r for r in self._records.values() if r.session_id == session_id]

    def get_operations_by_tool(self, tool_key: str) -> List[OperationRecord]:
        """Get all operations for a specific tool."""
        return [r for r in self._records.values() if r.tool_key == tool_key]

    def get_failed_operations(self) -> List[OperationRecord]:
        """Get all failed operations."""
        return [r for r in self._records.values() if r.status == OperationStatus.FAILED]

    def get_retry_chain(self, op_id: str) -> List[OperationRecord]:
        """Get the retry chain for an operation."""
        chain = []
        current = self._records.get(op_id)
        while current:
            chain.append(current)
            if current.retry_of and current.retry_of in self._records:
                current = self._records[current.retry_of]
            else:
                break
        return chain

    def get_operation_tree(self, parent_op_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get operations as a tree structure."""
        if parent_op_id:
            roots = [self._records.get(parent_op_id)] if parent_op_id in self._records else []
        else:
            roots = [r for r in self._records.values() if r.parent_op_id is None]

        def build_tree(record: OperationRecord) -> Dict[str, Any]:
            children = [
                build_tree(self._records[cid])
                for cid in record.child_op_ids
                if cid in self._records
            ]
            return {
                "op_id": record.op_id,
                "name": record.name,
                "type": record.op_type.value,
                "status": record.status.value,
                "duration_ms": record.duration_ms,
                "error": record.error,
                "children": children,
            }

        return [build_tree(r) for r in roots if r]

    def get_summary(self) -> Dict[str, Any]:
        """Get a summary of all tracked operations."""
        total = len(self._records)
        succeeded = sum(1 for r in self._records.values() if r.status == OperationStatus.SUCCEEDED)
        failed = sum(1 for r in self._records.values() if r.status == OperationStatus.FAILED)
        skipped = sum(1 for r in self._records.values() if r.status == OperationStatus.SKIPPED)
        running = sum(1 for r in self._records.values() if r.status == OperationStatus.RUNNING)

        failures_by_category: Dict[str, int] = {}
        for r in self._records.values():
            if r.failure_category:
                key = r.failure_category.value
                failures_by_category[key] = failures_by_category.get(key, 0) + 1

        return {
            "session_id": self._session_id,
            "total_operations": total,
            "succeeded": succeeded,
            "failed": failed,
            "skipped": skipped,
            "running": running,
            "failures_by_category": failures_by_category,
            "retry_count": sum(1 for r in self._records.values() if r.op_type == OperationType.RETRY),
            "recovery_count": sum(1 for r in self._records.values() if r.op_type == OperationType.RECOVERY),
        }

    def export_all(self) -> List[Dict[str, Any]]:
        """Export all operation records as dictionaries."""
        return [r.to_dict() for r in self._records.values()]

    def save_to_file(self, path: str) -> None:
        """Save all operation records to a JSON file."""
        os.makedirs(os.path.dirname(path), exist_ok=True)
        data = {
            "session_id": self._session_id,
            "summary": self.get_summary(),
            "operations": self.export_all(),
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, default=str)
        logger.info("Operation records saved", path=path, count=len(self._records))

    def load_from_file(self, path: str) -> None:
        """Load operation records from a JSON file."""
        if not os.path.exists(path):
            return
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        self._session_id = data.get("session_id")
        for op_data in data.get("operations", []):
            op_type = OperationType(op_data["op_type"])
            status = OperationStatus(op_data["status"])
            failure_category = (
                FailureCategory(op_data["failure_category"])
                if op_data.get("failure_category")
                else None
            )
            record = OperationRecord(
                op_id=op_data["op_id"],
                op_type=op_type,
                parent_op_id=op_data.get("parent_op_id"),
                session_id=op_data.get("session_id"),
                name=op_data.get("name", ""),
                tool_key=op_data.get("tool_key"),
                status=status,
                started_at=op_data.get("started_at"),
                completed_at=op_data.get("completed_at"),
                duration_ms=op_data.get("duration_ms", 0.0),
                error=op_data.get("error"),
                failure_category=failure_category,
                retry_of=op_data.get("retry_of"),
                retry_attempt=op_data.get("retry_attempt", 0),
                details=op_data.get("details", {}),
                result_data=op_data.get("result_data", {}),
                child_op_ids=op_data.get("child_op_ids", []),
            )
            self._records[record.op_id] = record
        logger.info("Operation records loaded", path=path, count=len(self._records))
