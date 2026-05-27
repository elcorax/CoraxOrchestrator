"""
Corax Orchestrator - Process Capability.

Provides process management for the autonomous agent including
process tracking, monitoring, and lifecycle management.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, Any, List, Optional, Callable
import asyncio
import os
import signal
import time
from uuid import uuid4

from src.agent.execution.capabilities.base import (
    CapabilityBase,
    CapabilityResult,
    CapabilityError,
    ExecutionContext,
)
from src.core.logging import get_logger

logger = get_logger(__name__)


class ProcessEvent(Enum):
    """Events that can occur during process lifecycle."""
    STARTED = "started"
    COMPLETED = "completed"
    FAILED = "failed"
    TIMEOUT = "timeout"
    KILLED = "killed"
    OUTPUT = "output"
    ERROR = "error"


@dataclass
class ProcessInfo:
    """
    Information about a tracked process.

    Tracks the complete lifecycle of a process from creation
    to termination, including output and resource usage.
    """
    process_id: str
    command: str
    args: List[str]
    pid: Optional[int] = None
    status: str = "pending"  # pending, running, completed, failed, killed, timed_out
    exit_code: Optional[int] = None
    stdout: str = ""
    stderr: str = ""
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    duration_ms: Optional[float] = None
    timeout_seconds: Optional[int] = None
    max_retries: int = 0
    retry_count: int = 0
    working_directory: Optional[str] = None
    environment: Dict[str, str] = field(default_factory=dict)
    events: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "process_id": self.process_id,
            "command": self.command,
            "args": self.args,
            "pid": self.pid,
            "status": self.status,
            "exit_code": self.exit_code,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "duration_ms": self.duration_ms,
            "retry_count": self.retry_count,
        }


@dataclass
class ProcessFilter:
    """Filter criteria for process queries."""
    status: Optional[str] = None
    command_contains: Optional[str] = None
    pid: Optional[int] = None
    created_after: Optional[str] = None
    created_before: Optional[str] = None


class ProcessCapability(CapabilityBase):
    """
    Process management capability.

    Provides:
    - Process creation and tracking
    - Process lifecycle monitoring
    - stdout/stderr capture
    - Timeout enforcement
    - Automatic retry on failure
    - Process listing and filtering
    - Event callbacks for process lifecycle
    """

    def __init__(self) -> None:
        super().__init__()
        self._processes: Dict[str, ProcessInfo] = {}
        self._subprocesses: Dict[str, asyncio.subprocess.Process] = {}
        self._event_callbacks: Dict[ProcessEvent, List[Callable]] = {}

    @property
    def name(self) -> str:
        return "process"

    @property
    def version(self) -> str:
        return "1.0.0"

    @property
    def description(self) -> str:
        return (
            "Process management for tracking and controlling system "
            "processes. Supports creation, monitoring, timeout, and "
            "automatic retry."
        )

    async def initialize(self, context: ExecutionContext) -> None:
        """Initialize the process capability."""
        self._context = context
        self._initialized = True
        logger.info("Process capability initialized")

    async def shutdown(self) -> None:
        """Shutdown and kill all tracked processes."""
        for pid, proc in self._subprocesses.items():
            if proc.returncode is None:
                try:
                    proc.kill()
                    await asyncio.wait_for(proc.wait(), timeout=5)
                except Exception:
                    pass
        self._processes.clear()
        self._subprocesses.clear()
        self._initialized = False
        logger.info("Process capability shut down")

    async def health_check(self) -> Dict[str, Any]:
        """Check process capability health."""
        return {
            "healthy": self._initialized,
            "tracked_processes": len(self._processes),
            "running_processes": sum(
                1 for p in self._processes.values()
                if p.status == "running"
            ),
            "initialized": self._initialized,
        }

    async def get_capabilities(self) -> List[Dict[str, Any]]:
        """List process operations."""
        return [
            {
                "name": "run_process",
                "description": "Run a process and wait for completion",
                "parameters": ["command", "args", "timeout", "working_directory"],
            },
            {
                "name": "start_process",
                "description": "Start a process in the background",
                "parameters": ["command", "args", "working_directory"],
            },
            {
                "name": "wait_process",
                "description": "Wait for a background process to complete",
                "parameters": ["process_id", "timeout"],
            },
            {
                "name": "kill_process",
                "description": "Kill a running process",
                "parameters": ["process_id"],
            },
            {
                "name": "list_processes",
                "description": "List tracked processes",
                "parameters": ["status", "command_contains"],
            },
            {
                "name": "get_process_info",
                "description": "Get information about a process",
                "parameters": ["process_id"],
            },
            {
                "name": "is_process_running",
                "description": "Check if a process is still running",
                "parameters": ["process_id"],
            },
        ]

    # --- Process Execution ---

    async def run_process(
        self,
        command: str,
        args: Optional[List[str]] = None,
        timeout: Optional[int] = None,
        working_directory: Optional[str] = None,
        env: Optional[Dict[str, str]] = None,
        max_retries: int = 0,
    ) -> CapabilityResult:
        """
        Run a process and wait for it to complete.

        Args:
            command: The command to run
            args: Command arguments
            timeout: Timeout in seconds
            working_directory: Working directory
            env: Environment variables
            max_retries: Number of retries on failure

        Returns:
            CapabilityResult with process output
        """
        if not self._initialized:
            return CapabilityResult(
                success=False,
                capability=self.name,
                error="Process capability not initialized",
            )

        process_id = f"proc_{uuid4().hex[:8]}"
        args = args or []
        timeout = timeout or (self._context.timeout_seconds if self._context else 300)

        process_info = ProcessInfo(
            process_id=process_id,
            command=command,
            args=args,
            timeout_seconds=timeout,
            max_retries=max_retries,
            working_directory=working_directory,
            environment=env or {},
        )

        self._processes[process_id] = process_info
        start_time = time.time()

        for attempt in range(max_retries + 1):
            if attempt > 0:
                logger.info(
                    "Retrying process",
                    process_id=process_id,
                    attempt=attempt,
                    max_retries=max_retries,
                )
                process_info.retry_count = attempt
                await asyncio.sleep(2 ** attempt)  # Exponential backoff

            try:
                proc = await asyncio.create_subprocess_exec(
                    command,
                    *args,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    cwd=working_directory,
                    env={**os.environ, **(env or {})},
                )

                process_info.pid = proc.pid
                process_info.status = "running"
                process_info.started_at = datetime.now(timezone.utc).isoformat()
                self._subprocesses[process_id] = proc
                self._emit_event(ProcessEvent.STARTED, process_info)

                try:
                    stdout, stderr = await asyncio.wait_for(
                        proc.communicate(), timeout=timeout
                    )

                    process_info.stdout = stdout.decode("utf-8", errors="replace")
                    process_info.stderr = stderr.decode("utf-8", errors="replace")
                    process_info.exit_code = proc.returncode
                    process_info.completed_at = datetime.now(timezone.utc).isoformat()
                    process_info.duration_ms = (time.time() - start_time) * 1000

                    if proc.returncode == 0:
                        process_info.status = "completed"
                        self._emit_event(ProcessEvent.COMPLETED, process_info)
                        return CapabilityResult(
                            success=True,
                            capability=self.name,
                            data={
                                "process_id": process_id,
                                "stdout": process_info.stdout,
                                "stderr": process_info.stderr,
                                "exit_code": proc.returncode,
                                "duration_ms": process_info.duration_ms,
                            },
                            duration_ms=process_info.duration_ms,
                        )
                    else:
                        process_info.status = "failed"
                        self._emit_event(ProcessEvent.FAILED, process_info)
                        if attempt < max_retries:
                            continue
                        return CapabilityResult(
                            success=False,
                            capability=self.name,
                            error=f"Process exited with code {proc.returncode}",
                            data={
                                "process_id": process_id,
                                "stdout": process_info.stdout,
                                "stderr": process_info.stderr,
                                "exit_code": proc.returncode,
                            },
                            duration_ms=process_info.duration_ms,
                        )

                except asyncio.TimeoutError:
                    proc.kill()
                    await proc.wait()
                    process_info.status = "timed_out"
                    process_info.completed_at = datetime.now(timezone.utc).isoformat()
                    process_info.duration_ms = (time.time() - start_time) * 1000
                    self._emit_event(ProcessEvent.TIMEOUT, process_info)

                    if attempt < max_retries:
                        continue
                    return CapabilityResult(
                        success=False,
                        capability=self.name,
                        error=f"Process timed out after {timeout}s",
                        data={"process_id": process_id},
                    )

            except FileNotFoundError:
                process_info.status = "failed"
                process_info.completed_at = datetime.now(timezone.utc).isoformat()
                return CapabilityResult(
                    success=False,
                    capability=self.name,
                    error=f"Command not found: {command}",
                    data={"process_id": process_id},
                )
            except Exception as e:
                process_info.status = "failed"
                process_info.completed_at = datetime.now(timezone.utc).isoformat()
                self._emit_event(ProcessEvent.FAILED, process_info)
                if attempt < max_retries:
                    continue
                return CapabilityResult(
                    success=False,
                    capability=self.name,
                    error=str(e),
                    data={"process_id": process_id},
                )

        return CapabilityResult(
            success=False,
            capability=self.name,
            error="All retry attempts exhausted",
            data={"process_id": process_id},
        )

    async def start_process(
        self,
        command: str,
        args: Optional[List[str]] = None,
        working_directory: Optional[str] = None,
        env: Optional[Dict[str, str]] = None,
    ) -> CapabilityResult:
        """
        Start a process in the background.

        Args:
            command: The command to run
            args: Command arguments
            working_directory: Working directory
            env: Environment variables

        Returns:
            CapabilityResult with process_id for later tracking
        """
        process_id = f"proc_{uuid4().hex[:8]}"
        args = args or []

        try:
            proc = await asyncio.create_subprocess_exec(
                command,
                *args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=working_directory,
                env={**os.environ, **(env or {})},
            )

            process_info = ProcessInfo(
                process_id=process_id,
                command=command,
                args=args,
                pid=proc.pid,
                status="running",
                started_at=datetime.now(timezone.utc).isoformat(),
                working_directory=working_directory,
                environment=env or {},
            )

            self._processes[process_id] = process_info
            self._subprocesses[process_id] = proc
            self._emit_event(ProcessEvent.STARTED, process_info)

            # Start background output collection
            asyncio.create_task(self._collect_output(process_id, proc))

            logger.info(
                "Background process started",
                process_id=process_id,
                command=command,
                pid=proc.pid,
            )

            return CapabilityResult(
                success=True,
                capability=self.name,
                data={
                    "process_id": process_id,
                    "pid": proc.pid,
                    "command": command,
                },
            )

        except Exception as e:
            return CapabilityResult(
                success=False,
                capability=self.name,
                error=str(e),
            )

    async def wait_process(
        self,
        process_id: str,
        timeout: Optional[int] = None,
    ) -> CapabilityResult:
        """
        Wait for a background process to complete.

        Args:
            process_id: The process to wait for
            timeout: Maximum time to wait

        Returns:
            CapabilityResult with process output
        """
        process_info = self._processes.get(process_id)
        if not process_info:
            return CapabilityResult(
                success=False,
                capability=self.name,
                error=f"Process '{process_id}' not found",
            )

        proc = self._subprocesses.get(process_id)
        if not proc:
            return CapabilityResult(
                success=False,
                capability=self.name,
                error=f"Subprocess for '{process_id}' not found",
            )

        try:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=timeout
            )

            process_info.stdout = stdout.decode("utf-8", errors="replace")
            process_info.stderr = stderr.decode("utf-8", errors="replace")
            process_info.exit_code = proc.returncode
            process_info.completed_at = datetime.now(timezone.utc).isoformat()
            process_info.status = "completed" if proc.returncode == 0 else "failed"

            self._emit_event(
                ProcessEvent.COMPLETED if proc.returncode == 0 else ProcessEvent.FAILED,
                process_info,
            )

            return CapabilityResult(
                success=proc.returncode == 0,
                capability=self.name,
                data={
                    "process_id": process_id,
                    "stdout": process_info.stdout,
                    "stderr": process_info.stderr,
                    "exit_code": proc.returncode,
                },
            )

        except asyncio.TimeoutError:
            return CapabilityResult(
                success=False,
                capability=self.name,
                error=f"Wait timed out after {timeout}s",
                data={"process_id": process_id},
            )

    async def kill_process(self, process_id: str) -> CapabilityResult:
        """
        Kill a running process.

        Args:
            process_id: The process to kill

        Returns:
            CapabilityResult
        """
        proc = self._subprocesses.get(process_id)
        if not proc or proc.returncode is not None:
            return CapabilityResult(
                success=False,
                capability=self.name,
                error=f"Process '{process_id}' not running",
            )

        try:
            proc.kill()
            await asyncio.wait_for(proc.wait(), timeout=5)

            process_info = self._processes.get(process_id)
            if process_info:
                process_info.status = "killed"
                process_info.completed_at = datetime.now(timezone.utc).isoformat()
                self._emit_event(ProcessEvent.KILLED, process_info)

            return CapabilityResult(
                success=True,
                capability=self.name,
                data={"process_id": process_id},
            )

        except Exception as e:
            return CapabilityResult(
                success=False,
                capability=self.name,
                error=str(e),
            )

    # --- Process Queries ---

    async def list_processes(
        self,
        filter: Optional[ProcessFilter] = None,
    ) -> List[Dict[str, Any]]:
        """List tracked processes, optionally filtered."""
        results = []
        for process_info in self._processes.values():
            if filter:
                if filter.status and process_info.status != filter.status:
                    continue
                if filter.command_contains and filter.command_contains not in process_info.command:
                    continue
            results.append(process_info.to_dict())
        return results

    async def get_process_info(self, process_id: str) -> Optional[Dict[str, Any]]:
        """Get information about a specific process."""
        process_info = self._processes.get(process_id)
        return process_info.to_dict() if process_info else None

    async def is_process_running(self, process_id: str) -> bool:
        """Check if a process is still running."""
        process_info = self._processes.get(process_id)
        if not process_info:
            return False
        return process_info.status == "running"

    # --- Event Callbacks ---

    def on_event(
        self,
        event: ProcessEvent,
        callback: Callable[[ProcessInfo], None],
    ) -> None:
        """Register a callback for a process event."""
        if event not in self._event_callbacks:
            self._event_callbacks[event] = []
        self._event_callbacks[event].append(callback)

    # --- Internal Methods ---

    async def _collect_output(
        self,
        process_id: str,
        proc: asyncio.subprocess.Process,
    ) -> None:
        """Collect output from a background process."""
        try:
            stdout, stderr = await proc.communicate()
            process_info = self._processes.get(process_id)
            if process_info:
                process_info.stdout = stdout.decode("utf-8", errors="replace")
                process_info.stderr = stderr.decode("utf-8", errors="replace")
                process_info.exit_code = proc.returncode
                process_info.completed_at = datetime.now(timezone.utc).isoformat()
                process_info.status = "completed" if proc.returncode == 0 else "failed"
                self._emit_event(
                    ProcessEvent.COMPLETED if proc.returncode == 0 else ProcessEvent.FAILED,
                    process_info,
                )
        except Exception as e:
            logger.error("Output collection error", process_id=process_id, error=str(e))

    def _emit_event(self, event: ProcessEvent, process_info: ProcessInfo) -> None:
        """Emit a process event to registered callbacks."""
        process_info.events.append({
            "event": event.value,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        callbacks = self._event_callbacks.get(event, [])
        for callback in callbacks:
            try:
                callback(process_info)
            except Exception as e:
                logger.error("Event callback error", error=str(e))
