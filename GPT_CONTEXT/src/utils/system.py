"""
Corax Orchestrator - System Utility Functions.

Provides common system-level utility functions for command execution,
path resolution, and privilege detection.
"""

import os
import sys
import asyncio
import subprocess
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple


async def run_command_async(
    command: List[str],
    cwd: Optional[Path] = None,
    env: Optional[Dict[str, str]] = None,
    timeout: Optional[int] = None,
) -> Tuple[int, str, str]:
    """
    Run a command asynchronously and return the result.

    Args:
        command: Command and arguments as a list
        cwd: Working directory
        env: Environment variables
        timeout: Timeout in seconds

    Returns:
        Tuple of (exit_code, stdout, stderr)
    """
    try:
        process = await asyncio.create_subprocess_exec(
            *command,
            cwd=cwd,
            env={**os.environ, **(env or {})},
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        stdout, stderr = await asyncio.wait_for(
            process.communicate(), timeout=timeout
        )

        return (
            process.returncode or 0,
            stdout.decode("utf-8", errors="replace"),
            stderr.decode("utf-8", errors="replace"),
        )
    except asyncio.TimeoutError:
        if process:
            process.kill()
        return (-1, "", f"Command timed out after {timeout}s")
    except Exception as e:
        return (-1, "", str(e))


def run_command(
    command: List[str],
    cwd: Optional[Path] = None,
    env: Optional[Dict[str, str]] = None,
    timeout: Optional[int] = None,
) -> Tuple[int, str, str]:
    """
    Run a command synchronously and return the result.

    Args:
        command: Command and arguments as a list
        cwd: Working directory
        env: Environment variables
        timeout: Timeout in seconds

    Returns:
        Tuple of (exit_code, stdout, stderr)
    """
    try:
        result = subprocess.run(
            command,
            cwd=cwd,
            env={**os.environ, **(env or {})},
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return (result.returncode, result.stdout, result.stderr)
    except subprocess.TimeoutExpired:
        return (-1, "", f"Command timed out after {timeout}s")
    except Exception as e:
        return (-1, "", str(e))


def is_admin() -> bool:
    """Check if the current process has administrator/root privileges."""
    if sys.platform == "win32":
        try:
            import ctypes
            return ctypes.windll.shell32.IsUserAnAdmin() != 0
        except Exception:
            return False
    else:
        return os.geteuid() == 0


def get_env_path(name: str, default: str = "") -> str:
    """Get an environment variable value."""
    return os.environ.get(name, default)


def get_downloads_path() -> Path:
    """Get the user's downloads directory."""
    if sys.platform == "win32":
        return Path(os.environ.get("USERPROFILE", "C:\\Users\\Default")) / "Downloads"
    return Path.home() / "Downloads"


def get_temp_path() -> Path:
    """Get the system temporary directory."""
    if sys.platform == "win32":
        return Path(os.environ.get("TEMP", "C:\\Windows\\Temp"))
    return Path("/tmp")


def get_home_path() -> Path:
    """Get the user's home directory."""
    return Path.home()
