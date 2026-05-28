"""
Corax Orchestrator - Terminal Capability.

Provides persistent terminal session management for the autonomous agent.
Supports PowerShell, CMD, and Bash with command streaming, output capture,
and interactive command handling.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, Any, List, Optional, AsyncIterator, Tuple
from pathlib import Path
import asyncio
import os
import time
import json
from uuid import uuid4

from src.agent.execution.capabilities.base import (
    CapabilityBase,
    CapabilityResult,
    CapabilityError,
    ExecutionContext,
)
from src.core.logging import get_logger

logger = get_logger(__name__)


class ShellType(Enum):
    """Supported shell types."""
    POWERSHELL = "powershell"
    CMD = "cmd"
    BASH = "bash"
    ZSH = "zsh"
    UNKNOWN = "unknown"


@dataclass
class TerminalConfig:
    """Configuration for a terminal session."""
    shell_type: ShellType = ShellType.POWERSHELL
    working_directory: Optional[str] = None
    environment: Dict[str, str] = field(default_factory=dict)
    timeout_seconds: int = 300
    max_output_size: int = 10 * 1024 * 1024  # 10MB
    encoding: str = "utf-8"
    persist_history: bool = True
    max_history_entries: int = 1000


@dataclass
class TerminalSession:
    """
    Represents a persistent terminal session.

    Each session maintains its own subprocess, working directory,
    environment, and command history.
    """
    session_id: str
    shell_type: ShellType
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    last_active: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    working_directory: str = field(default_factory=os.getcwd)
    is_alive: bool = True
    command_count: int = 0
    config: TerminalConfig = field(default_factory=TerminalConfig)

    # Internal state
    _process: Optional[asyncio.subprocess.Process] = None
    _stdin: Optional[asyncio.StreamWriter] = None
    _stdout_task: Optional[asyncio.Task] = None
    _stderr_task: Optional[asyncio.Task] = None
    _output_buffer: List[str] = field(default_factory=list)
    _error_buffer: List[str] = field(default_factory=list)
    _history: List[Dict[str, Any]] = field(default_factory=list)
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "shell_type": self.shell_type.value,
            "created_at": self.created_at,
            "last_active": self.last_active,
            "working_directory": self.working_directory,
            "is_alive": self.is_alive,
            "command_count": self.command_count,
        }


class TerminalCapability(CapabilityBase):
    """
    Terminal session management capability.

    Provides:
    - Persistent terminal sessions (PowerShell, CMD, Bash)
    - Command execution with streaming output
    - stdout/stderr capture
    - Interactive command handling
    - Timeout management
    - Process tracking
    - Command history with persistence
    - Cross-platform shell support
    """

    def __init__(self) -> None:
        super().__init__()
        self._sessions: Dict[str, TerminalSession] = {}
        self._history_dir: Optional[Path] = None

    @property
    def name(self) -> str:
        return "terminal"

    @property
    def version(self) -> str:
        return "1.0.0"

    @property
    def description(self) -> str:
        return (
            "Persistent terminal session management with support for "
            "PowerShell, CMD, and Bash. Provides command execution, "
            "streaming output, and interactive command handling."
        )

    async def initialize(self, context: ExecutionContext) -> None:
        """Initialize the terminal capability."""
        self._context = context
        self._history_dir = Path("data/persistence/terminal_history")
        self._history_dir.mkdir(parents=True, exist_ok=True)
        self._initialized = True
        logger.info("Terminal capability initialized")

    async def shutdown(self) -> None:
        """Shutdown all terminal sessions."""
        for session_id in list(self._sessions.keys()):
            await self.close_session(session_id)
        self._initialized = False
        logger.info("Terminal capability shut down")

    async def health_check(self) -> Dict[str, Any]:
        """Check terminal capability health."""
        alive_count = sum(
            1 for s in self._sessions.values() if s.is_alive
        )
        return {
            "healthy": self._initialized,
            "active_sessions": len(self._sessions),
            "alive_sessions": alive_count,
            "initialized": self._initialized,
        }

    async def get_capabilities(self) -> List[Dict[str, Any]]:
        """List terminal operations."""
        return [
            {
                "name": "create_session",
                "description": "Create a new terminal session",
                "parameters": ["shell_type", "working_directory"],
            },
            {
                "name": "execute_command",
                "description": "Execute a command in a terminal session",
                "parameters": ["session_id", "command", "timeout"],
            },
            {
                "name": "execute_command_stream",
                "description": "Execute a command with streaming output",
                "parameters": ["session_id", "command"],
            },
            {
                "name": "send_input",
                "description": "Send input to an interactive command",
                "parameters": ["session_id", "input_text"],
            },
            {
                "name": "close_session",
                "description": "Close a terminal session",
                "parameters": ["session_id"],
            },
            {
                "name": "list_sessions",
                "description": "List all active terminal sessions",
                "parameters": [],
            },
            {
                "name": "get_session_info",
                "description": "Get information about a session",
                "parameters": ["session_id"],
            },
            {
                "name": "get_command_history",
                "description": "Get command history for a session",
                "parameters": ["session_id", "limit"],
            },
            {
                "name": "detect_shell",
                "description": "Detect available shells on the system",
                "parameters": [],
            },
        ]

    # --- Session Management ---

    async def create_session(
        self,
        shell_type: Optional[ShellType] = None,
        working_directory: Optional[str] = None,
        config: Optional[TerminalConfig] = None,
    ) -> TerminalSession:
        """
        Create a new persistent terminal session.

        Args:
            shell_type: Type of shell to use (auto-detect if None)
            working_directory: Initial working directory
            config: Terminal configuration

        Returns:
            The created TerminalSession

        Raises:
            CapabilityError: If session creation fails
        """
        if not self._initialized:
            raise CapabilityError(
                "Terminal capability not initialized",
                capability=self.name,
            )

        # Auto-detect shell if not specified
        if shell_type is None:
            shell_type = self._detect_default_shell()

        # Resolve working directory
        if working_directory is None:
            working_directory = os.getcwd()

        # Create configuration
        session_config = config or TerminalConfig(
            shell_type=shell_type,
            working_directory=working_directory,
        )

        # Create session
        session = TerminalSession(
            session_id=f"term_{uuid4().hex[:8]}",
            shell_type=shell_type,
            working_directory=working_directory,
            config=session_config,
        )

        # Start the shell process
        try:
            await self._start_shell_process(session)
        except Exception as e:
            raise CapabilityError(
                f"Failed to start shell process: {e}",
                capability=self.name,
                recoverable=True,
                details={"shell_type": shell_type.value},
            )

        self._sessions[session.session_id] = session
        logger.info(
            "Terminal session created",
            session_id=session.session_id,
            shell=shell_type.value,
        )

        return session

    async def close_session(self, session_id: str) -> CapabilityResult:
        """
        Close a terminal session.

        Args:
            session_id: The session to close

        Returns:
            CapabilityResult indicating success
        """
        session = self._sessions.get(session_id)
        if not session:
            return CapabilityResult(
                success=False,
                capability=self.name,
                error=f"Session '{session_id}' not found",
            )

        try:
            # Save history if configured
            if session.config.persist_history:
                await self._persist_history(session)

            # Kill the process
            if session._process and session._process.returncode is None:
                session._process.kill()
                try:
                    await asyncio.wait_for(session._process.wait(), timeout=5)
                except asyncio.TimeoutError:
                    pass

            # Cancel reader tasks
            if session._stdout_task:
                session._stdout_task.cancel()
            if session._stderr_task:
                session._stderr_task.cancel()

            session.is_alive = False
            del self._sessions[session_id]

            logger.info("Terminal session closed", session_id=session_id)

            return CapabilityResult(
                success=True,
                capability=self.name,
                data={"session_id": session_id},
            )

        except Exception as e:
            return CapabilityResult(
                success=False,
                capability=self.name,
                error=str(e),
            )

    async def list_sessions(self) -> List[Dict[str, Any]]:
        """List all active terminal sessions."""
        return [
            session.to_dict() for session in self._sessions.values()
        ]

    async def get_session_info(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Get information about a specific session."""
        session = self._sessions.get(session_id)
        return session.to_dict() if session else None

    # --- Command Execution ---

    async def execute_command(
        self,
        session_id: str,
        command: str,
        timeout: Optional[int] = None,
    ) -> CapabilityResult:
        """
        Execute a command in a terminal session.

        Args:
            session_id: The terminal session to use
            command: The command to execute
            timeout: Timeout in seconds (uses session default if None)

        Returns:
            CapabilityResult with stdout, stderr, and exit code
        """
        session = self._sessions.get(session_id)
        if not session:
            return CapabilityResult(
                success=False,
                capability=self.name,
                error=f"Session '{session_id}' not found",
            )

        if not session.is_alive:
            return CapabilityResult(
                success=False,
                capability=self.name,
                error=f"Session '{session_id}' is no longer alive",
            )

        timeout = timeout or session.config.timeout_seconds
        start_time = time.time()

        try:
            # Clear buffers
            session._output_buffer.clear()
            session._error_buffer.clear()

            # Send command
            async with session._lock:
                command_line = self._format_command(session, command)
                session._stdin.write(command_line.encode(session.config.encoding))
                await session._stdin.drain()

            # Wait for command to complete
            await asyncio.sleep(0.5)  # Give shell time to start processing

            # Wait for output with timeout
            await self._wait_for_output(session, timeout, start_time)

            # Collect output
            stdout = "".join(session._output_buffer)
            stderr = "".join(session._error_buffer)

            # Determine exit code (best effort)
            exit_code = await self._get_exit_code(session)

            duration_ms = (time.time() - start_time) * 1000

            # Record history
            session.command_count += 1
            self._record_history(session, command, exit_code, duration_ms)

            logger.info(
                "Command executed",
                session_id=session_id,
                command=command[:100],
                exit_code=exit_code,
                duration_ms=f"{duration_ms:.0f}",
            )

            return CapabilityResult(
                success=exit_code == 0,
                capability=self.name,
                data={
                    "stdout": stdout,
                    "stderr": stderr,
                    "exit_code": exit_code,
                    "command": command,
                    "session_id": session_id,
                },
                duration_ms=duration_ms,
            )

        except asyncio.TimeoutError:
            return CapabilityResult(
                success=False,
                capability=self.name,
                error=f"Command timed out after {timeout}s",
                data={"command": command, "session_id": session_id},
            )
        except Exception as e:
            return CapabilityResult(
                success=False,
                capability=self.name,
                error=str(e),
                data={"command": command, "session_id": session_id},
            )

    async def execute_command_stream(
        self,
        session_id: str,
        command: str,
    ) -> AsyncIterator[Dict[str, Any]]:
        """
        Execute a command with streaming output.

        Args:
            session_id: The terminal session to use
            command: The command to execute

        Yields:
            Dicts with 'type' ('stdout', 'stderr', 'exit') and 'data'
        """
        session = self._sessions.get(session_id)
        if not session:
            yield {"type": "error", "data": f"Session '{session_id}' not found"}
            return

        if not session.is_alive:
            yield {"type": "error", "data": f"Session '{session_id}' is no longer alive"}
            return

        try:
            # Clear buffers
            session._output_buffer.clear()
            session._error_buffer.clear()

            # Send command
            async with session._lock:
                command_line = self._format_command(session, command)
                session._stdin.write(command_line.encode(session.config.encoding))
                await session._stdin.drain()

            # Stream output
            start_time = time.time()
            output_complete = False

            while not output_complete:
                await asyncio.sleep(0.1)

                # Yield stdout
                while session._output_buffer:
                    line = session._output_buffer.pop(0)
                    yield {"type": "stdout", "data": line}

                # Yield stderr
                while session._error_buffer:
                    line = session._error_buffer.pop(0)
                    yield {"type": "stderr", "data": line}

                # Check timeout
                if time.time() - start_time > session.config.timeout_seconds:
                    yield {"type": "error", "data": "Command timed out"}
                    break

                # Check if command completed
                if self._is_command_complete(session):
                    output_complete = True

            # Get final exit code
            exit_code = await self._get_exit_code(session)
            yield {"type": "exit", "data": exit_code}

        except Exception as e:
            yield {"type": "error", "data": str(e)}

    async def send_input(
        self,
        session_id: str,
        input_text: str,
    ) -> CapabilityResult:
        """
        Send input to an interactive command.

        Args:
            session_id: The terminal session
            input_text: Text to send

        Returns:
            CapabilityResult
        """
        session = self._sessions.get(session_id)
        if not session:
            return CapabilityResult(
                success=False,
                capability=self.name,
                error=f"Session '{session_id}' not found",
            )

        try:
            async with session._lock:
                session._stdin.write(
                    (input_text + "\n").encode(session.config.encoding)
                )
                await session._stdin.drain()

            return CapabilityResult(
                success=True,
                capability=self.name,
                data={"session_id": session_id, "input": input_text},
            )

        except Exception as e:
            return CapabilityResult(
                success=False,
                capability=self.name,
                error=str(e),
            )

    # --- History Management ---

    async def get_command_history(
        self,
        session_id: str,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """Get command history for a session."""
        session = self._sessions.get(session_id)
        if not session:
            return []
        return session._history[-limit:]

    async def get_all_history(
        self,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """Get command history across all sessions."""
        all_history = []
        for session in self._sessions.values():
            all_history.extend(session._history)
        # Sort by timestamp descending
        all_history.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
        return all_history[:limit]

    # --- Shell Detection ---

    async def detect_shell(self) -> Dict[str, Any]:
        """
        Detect available shells on the system.

        Returns:
            Dict with available shells and their paths
        """
        shells = {}

        # Check PowerShell
        if os.name == "nt":
            ps_paths = [
                "powershell.exe",
                "pwsh.exe",
                r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe",
            ]
            for ps in ps_paths:
                if self._command_exists(ps):
                    shells["powershell"] = ps
                    break

            # Check CMD
            cmd_paths = ["cmd.exe", r"C:\Windows\System32\cmd.exe"]
            for cmd in cmd_paths:
                if self._command_exists(cmd):
                    shells["cmd"] = cmd
                    break
        else:
            # Check Bash
            bash_paths = ["/bin/bash", "/usr/bin/bash", "/usr/local/bin/bash"]
            for bash in bash_paths:
                if os.path.exists(bash):
                    shells["bash"] = bash
                    break

            # Check Zsh
            zsh_paths = ["/bin/zsh", "/usr/bin/zsh"]
            for zsh in zsh_paths:
                if os.path.exists(zsh):
                    shells["zsh"] = zsh
                    break

        return {
            "available_shells": shells,
            "default": self._detect_default_shell().value,
        }

    # --- Internal Methods ---

    async def _start_shell_process(self, session: TerminalSession) -> None:
        """Start the shell subprocess for a session."""
        shell_cmd = self._get_shell_command(session.shell_type)

        # Build environment
        env = os.environ.copy()
        env.update(session.config.environment)

        # Start process
        session._process = await asyncio.create_subprocess_exec(
            *shell_cmd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=session.working_directory,
            env=env,
        )

        # Get stdin writer
        session._stdin = session._process.stdin

        # Start reader tasks
        session._stdout_task = asyncio.create_task(
            self._read_stream(session, session._process.stdout, session._output_buffer)
        )
        session._stderr_task = asyncio.create_task(
            self._read_stream(session, session._process.stderr, session._error_buffer)
        )

        # Wait for shell to be ready
        await asyncio.sleep(0.5)

    def _get_shell_command(self, shell_type: ShellType) -> List[str]:
        """Get the command to start a shell process."""
        if shell_type == ShellType.POWERSHELL:
            return ["powershell.exe", "-NoLogo", "-NoProfile", "-Command", "-"]
        elif shell_type == ShellType.CMD:
            return ["cmd.exe", "/Q"]
        elif shell_type in (ShellType.BASH, ShellType.ZSH):
            shell = "/bin/bash" if shell_type == ShellType.BASH else "/bin/zsh"
            return [shell, "--noediting", "-i"]
        else:
            return ["powershell.exe", "-NoLogo", "-NoProfile", "-Command", "-"]

    def _format_command(self, session: TerminalSession, command: str) -> str:
        """Format a command for the shell type."""
        if session.shell_type == ShellType.POWERSHELL:
            return f"{command}\r\n$LASTEXITCODE\r\n"
        elif session.shell_type == ShellType.CMD:
            return f"{command}\r\n"
        else:
            return f"{command}\n"

    async def _read_stream(
        self,
        session: TerminalSession,
        stream: asyncio.StreamReader,
        buffer: List[str],
    ) -> None:
        """Read from a stream and buffer the output."""
        try:
            while True:
                line = await stream.readline()
                if not line:
                    break
                try:
                    decoded = line.decode(session.config.encoding, errors="replace")
                    buffer.append(decoded)
                    # Enforce max output size
                    total = sum(len(s) for s in buffer)
                    if total > session.config.max_output_size:
                        buffer.pop(0)
                except Exception:
                    pass
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error("Stream read error", error=str(e))

    async def _wait_for_output(
        self,
        session: TerminalSession,
        timeout: int,
        start_time: float,
    ) -> None:
        """Wait for command output with timeout."""
        while time.time() - start_time < timeout:
            # Check if process is still running
            if session._process and session._process.returncode is not None:
                break
            await asyncio.sleep(0.1)

        if time.time() - start_time >= timeout:
            raise asyncio.TimeoutError()

    async def _get_exit_code(self, session: TerminalSession) -> int:
        """Get the exit code from the last command."""
        if session._process and session._process.returncode is not None:
            return session._process.returncode
        return 0

    def _is_command_complete(self, session: TerminalSession) -> bool:
        """Check if the current command has completed."""
        # Simple heuristic: check if process exited
        if session._process and session._process.returncode is not None:
            return True
        return False

    def _record_history(
        self,
        session: TerminalSession,
        command: str,
        exit_code: int,
        duration_ms: float,
    ) -> None:
        """Record a command in the session history."""
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "command": command,
            "exit_code": exit_code,
            "duration_ms": duration_ms,
            "session_id": session.session_id,
        }
        session._history.append(entry)

        # Enforce max history
        if len(session._history) > session.config.max_history_entries:
            session._history.pop(0)

    async def _persist_history(self, session: TerminalSession) -> None:
        """Persist command history to disk."""
        if not self._history_dir:
            return

        history_file = self._history_dir / f"{session.session_id}.json"
        try:
            with open(history_file, "w", encoding="utf-8") as f:
                json.dump(session._history, f, indent=2)
        except Exception as e:
            logger.error("Failed to persist terminal history", error=str(e))

    def _detect_default_shell(self) -> ShellType:
        """Detect the default shell on the system."""
        if os.name == "nt":
            # Check for PowerShell first
            if self._command_exists("pwsh.exe") or self._command_exists("powershell.exe"):
                return ShellType.POWERSHELL
            return ShellType.CMD
        else:
            # Check for bash
            if os.path.exists("/bin/bash"):
                return ShellType.BASH
            return ShellType.ZSH

    def _command_exists(self, command: str) -> bool:
        """Check if a command exists on the system."""
        try:
            if os.name == "nt":
                result = os.system(f"where {command} > nul 2>&1")
                return result == 0
            else:
                result = os.system(f"which {command} > /dev/null 2>&1")
                return result == 0
        except Exception:
            return False
