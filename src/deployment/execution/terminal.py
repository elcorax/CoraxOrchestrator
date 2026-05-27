"""
Corax Orchestrator - Terminal Session Management.

Manages CLI-first terminal sessions for executing commands,
streaming output, handling timeouts, and parsing results.
This is the primary execution path - GUI automation is fallback only.
"""

from typing import Dict, Any, List, Optional, Tuple, AsyncIterator
from dataclasses import dataclass, field
from datetime import datetime
import asyncio
import os
import time
import re

from src.core.logging import get_logger

logger = get_logger(__name__)


@dataclass
class TerminalResult:
    """Result of a terminal command execution."""
    command: str
    exit_code: int
    stdout: str
    stderr: str
    duration_ms: float
    timed_out: bool = False
    cancelled: bool = False

    @property
    def succeeded(self) -> bool:
        return self.exit_code == 0 and not self.timed_out and not self.cancelled

    @property
    def output(self) -> str:
        """Combined stdout + stderr."""
        out = self.stdout or ""
        err = self.stderr or ""
        if err and out:
            return f"{out}\n{err}"
        return out or err

    def to_dict(self) -> Dict[str, Any]:
        return {
            "command": self.command,
            "exit_code": self.exit_code,
            "stdout": self.stdout[:500] if self.stdout else "",
            "stderr": self.stderr[:500] if self.stderr else "",
            "duration_ms": round(self.duration_ms, 1),
            "timed_out": self.timed_out,
            "cancelled": self.cancelled,
            "succeeded": self.succeeded,
        }


class TerminalSession:
    """
    Manages a CLI terminal session for command execution.

    Features:
    - Async command execution with timeout
    - Real-time stdout/stderr streaming
    - Exit code analysis
    - Command queuing with dependency awareness
    - Environment variable management
    - Working directory management
    - Structured execution events
    """

    def __init__(
        self,
        shell: Optional[str] = None,
        cwd: Optional[str] = None,
        env: Optional[Dict[str, str]] = None,
        default_timeout: int = 120,
    ) -> None:
        self._shell = shell or self._detect_shell()
        self._cwd = cwd or os.getcwd()
        self._env = env or os.environ.copy()
        self._default_timeout = default_timeout
        self._session_id = f"term_{int(time.time())}"
        self._command_count = 0
        self._history: List[TerminalResult] = []

    def _detect_shell(self) -> str:
        """Detect the default system shell."""
        if os.name == "nt":
            return "powershell.exe"
        return os.environ.get("SHELL", "/bin/bash")

    @property
    def session_id(self) -> str:
        return self._session_id

    @property
    def history(self) -> List[TerminalResult]:
        return list(self._history)

    @property
    def cwd(self) -> str:
        return self._cwd

    async def execute(
        self,
        command: str,
        timeout: Optional[int] = None,
        cwd: Optional[str] = None,
        env: Optional[Dict[str, str]] = None,
        shell: bool = True,
    ) -> TerminalResult:
        """
        Execute a command in the terminal session.

        Args:
            command: Command string to execute
            timeout: Timeout in seconds (default: self._default_timeout)
            cwd: Working directory (default: self._cwd)
            env: Environment variables (default: self._env)
            shell: Whether to use shell execution

        Returns:
            TerminalResult with execution outcome
        """
        self._command_count += 1
        cmd_id = f"CMD-{self._command_count:04d}"
        timeout = timeout or self._default_timeout
        work_dir = cwd or self._cwd
        cmd_env = {**self._env, **(env or {})}

        logger.info(
            f"[{cmd_id}] Executing command",
            command=command[:200],
            timeout=timeout,
            cwd=work_dir,
        )

        start = time.time()

        proc = None
        try:
            if shell:
                # Shell execution (supports pipes, redirects, etc.)
                proc = await asyncio.create_subprocess_shell(
                    command,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    cwd=work_dir,
                    env=cmd_env,
                )
            else:
                # Direct execution (no shell interpretation)
                parts = self._split_command(command)
                proc = await asyncio.create_subprocess_exec(
                    *parts,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    cwd=work_dir,
                    env=cmd_env,
                )

            try:
                stdout, stderr = await asyncio.wait_for(
                    proc.communicate(), timeout=timeout
                )
                duration_ms = (time.time() - start) * 1000

                result = TerminalResult(
                    command=command,
                    exit_code=proc.returncode or 0,
                    stdout=stdout.decode("utf-8", errors="replace"),
                    stderr=stderr.decode("utf-8", errors="replace"),
                    duration_ms=duration_ms,
                )

            except asyncio.TimeoutError:
                duration_ms = (time.time() - start) * 1000
                try:
                    proc.kill()
                except Exception:
                    pass

                result = TerminalResult(
                    command=command,
                    exit_code=-1,
                    stdout="",
                    stderr=f"Command timed out after {timeout}s",
                    duration_ms=duration_ms,
                    timed_out=True,
                )
            finally:
                # Ensure subprocess resources are cleaned up
                if proc and proc.returncode is None:
                    try:
                        proc.kill()
                    except Exception:
                        pass
                if proc and proc.stdout:
                    try:
                        proc.stdout.close()
                    except Exception:
                        pass
                if proc and proc.stderr:
                    try:
                        proc.stderr.close()
                    except Exception:
                        pass
                if proc:
                    try:
                        await proc.wait()
                    except Exception:
                        pass

        except FileNotFoundError:
            duration_ms = (time.time() - start) * 1000
            result = TerminalResult(
                command=command,
                exit_code=-2,
                stdout="",
                stderr=f"Command not found: {command.split()[0] if command else 'unknown'}",
                duration_ms=duration_ms,
            )
        except Exception as e:
            duration_ms = (time.time() - start) * 1000
            result = TerminalResult(
                command=command,
                exit_code=-3,
                stdout="",
                stderr=str(e),
                duration_ms=duration_ms,
            )

        self._history.append(result)

        # Log result
        if result.succeeded:
            logger.info(
                f"[{cmd_id}] Command succeeded",
                exit_code=result.exit_code,
                duration_ms=round(result.duration_ms, 1),
            )
        elif result.timed_out:
            logger.warning(
                f"[{cmd_id}] Command timed out",
                timeout=timeout,
                duration_ms=round(result.duration_ms, 1),
            )
        else:
            logger.warning(
                f"[{cmd_id}] Command failed",
                exit_code=result.exit_code,
                stderr=result.stderr[:200],
                duration_ms=round(result.duration_ms, 1),
            )

        return result

    async def execute_powershell(
        self,
        script: str,
        timeout: Optional[int] = None,
    ) -> TerminalResult:
        """Execute a PowerShell script."""
        return await self.execute(
            f"powershell.exe -NoProfile -Command \"{script}\"",
            timeout=timeout,
        )

    async def execute_with_streaming(
        self,
        command: str,
        timeout: Optional[int] = None,
        cwd: Optional[str] = None,
    ) -> TerminalResult:
        """
        Execute a command with real-time stdout streaming.

        Useful for long-running installers where you want to
        see progress output as it happens.
        """
        timeout = timeout or self._default_timeout
        work_dir = cwd or self._cwd
        start = time.time()

        proc = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=work_dir,
            env=self._env,
        )

        stdout_lines = []
        stderr_lines = []

        async def read_stream(stream, lines, is_stderr=False):
            while True:
                line = await stream.readline()
                if not line:
                    break
                text = line.decode("utf-8", errors="replace").rstrip()
                lines.append(text)
                if text.strip():
                    prefix = "STDERR" if is_stderr else "STDOUT"
                    logger.debug(f"[stream] {prefix}: {text[:200]}")

        try:
            await asyncio.wait_for(
                asyncio.gather(
                    read_stream(proc.stdout, stdout_lines),
                    read_stream(proc.stderr, stderr_lines),
                ),
                timeout=timeout,
            )
        except asyncio.TimeoutError:
            try:
                proc.kill()
            except Exception:
                pass
            return TerminalResult(
                command=command,
                exit_code=-1,
                stdout="\n".join(stdout_lines),
                stderr="\n".join(stderr_lines) + f"\nTimed out after {timeout}s",
                duration_ms=(time.time() - start) * 1000,
                timed_out=True,
            )
        finally:
            # Ensure subprocess resources are cleaned up
            if proc and proc.returncode is None:
                try:
                    proc.kill()
                except Exception:
                    pass
            if proc and proc.stdout:
                try:
                    proc.stdout.close()
                except Exception:
                    pass
            if proc and proc.stderr:
                try:
                    proc.stderr.close()
                except Exception:
                    pass
            if proc:
                try:
                    await proc.wait()
                except Exception:
                    pass

        return TerminalResult(
            command=command,
            exit_code=proc.returncode or 0,
            stdout="\n".join(stdout_lines),
            stderr="\n".join(stderr_lines),
            duration_ms=(time.time() - start) * 1000,
        )

    async def execute_script(
        self,
        script_path: str,
        args: Optional[List[str]] = None,
        timeout: Optional[int] = None,
    ) -> TerminalResult:
        """Execute a script file."""
        if not os.path.exists(script_path):
            return TerminalResult(
                command=script_path,
                exit_code=-2,
                stdout="",
                stderr=f"Script not found: {script_path}",
                duration_ms=0,
            )

        if os.name == "nt" and script_path.endswith(".ps1"):
            cmd = f"powershell.exe -NoProfile -ExecutionPolicy Bypass -File \"{script_path}\""
            if args:
                cmd += " " + " ".join(args)
        else:
            cmd = f"\"{script_path}\""
            if args:
                cmd += " " + " ".join(args)

        return await self.execute(cmd, timeout=timeout)

    async def check_tool(self, tool_name: str, version_arg: str = "--version") -> Optional[str]:
        """Check if a tool is available and get its version."""
        result = await self.execute(f"{tool_name} {version_arg}", timeout=15)
        if result.succeeded:
            output = result.stdout or result.stderr
            # Extract version number
            match = re.search(r'(\d+\.\d+\.\d+)', output)
            if match:
                return match.group(1)
            match = re.search(r'(\d+\.\d+)', output)
            if match:
                return match.group(1)
            return output.strip()[:50]
        return None

    async def check_multiple_tools(
        self, tools: List[str]
    ) -> Dict[str, Optional[str]]:
        """Check multiple tools concurrently."""
        results = await asyncio.gather(
            *[self.check_tool(t) for t in tools],
            return_exceptions=True,
        )
        return {
            tool: str(result) if result and not isinstance(result, Exception) else None
            for tool, result in zip(tools, results)
        }

    def _split_command(self, command: str) -> List[str]:
        """Split a command string into parts, respecting quotes."""
        parts = []
        current = ""
        in_quote = False
        quote_char = None

        for char in command:
            if char in ('"', "'") and not in_quote:
                in_quote = True
                quote_char = char
            elif char == quote_char and in_quote:
                in_quote = False
                quote_char = None
            elif char == " " and not in_quote:
                if current:
                    parts.append(current)
                    current = ""
            else:
                current += char

        if current:
            parts.append(current)

        return parts

    def get_history_text(self) -> str:
        """Get formatted execution history."""
        lines = []
        for i, result in enumerate(self._history, 1):
            status = "✓" if result.succeeded else "✗"
            lines.append(
                f"[{status}] CMD-{i:04d} | exit={result.exit_code} | "
                f"{result.duration_ms:.0f}ms | {result.command[:100]}"
            )
        return "\n".join(lines)

    def get_stats(self) -> Dict[str, Any]:
        """Get terminal session statistics."""
        total = len(self._history)
        succeeded = sum(1 for r in self._history if r.succeeded)
        failed = sum(1 for r in self._history if not r.succeeded)
        timed_out = sum(1 for r in self._history if r.timed_out)
        total_duration = sum(r.duration_ms for r in self._history)

        return {
            "session_id": self._session_id,
            "total_commands": total,
            "succeeded": succeeded,
            "failed": failed,
            "timed_out": timed_out,
            "total_duration_ms": round(total_duration, 1),
            "average_duration_ms": round(total_duration / total, 1) if total else 0,
        }
