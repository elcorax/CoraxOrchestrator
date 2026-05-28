"""
Corax Orchestrator - Desktop Capability.

Provides desktop automation foundation for the autonomous agent.
Supports window detection, process-window association, and future
UI interaction hooks.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, Any, List, Optional, Callable
import asyncio
import os
import sys
import subprocess
import re

from src.agent.execution.capabilities.base import (
    CapabilityBase,
    CapabilityResult,
    CapabilityError,
    ExecutionContext,
)
from src.core.logging import get_logger

logger = get_logger(__name__)


class DesktopEvent(Enum):
    """Events that can occur on the desktop."""
    WINDOW_OPENED = "window_opened"
    WINDOW_CLOSED = "window_closed"
    WINDOW_FOCUSED = "window_focused"
    PROCESS_STARTED = "process_started"
    PROCESS_TERMINATED = "process_terminated"


@dataclass
class WindowInfo:
    """
    Information about a desktop window.

    Provides window identification and state information
    for desktop automation purposes.
    """
    window_id: Optional[int] = None
    title: str = ""
    process_name: str = ""
    process_id: Optional[int] = None
    is_visible: bool = True
    is_focused: bool = False
    bounds: Optional[Dict[str, int]] = None  # x, y, width, height
    class_name: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "window_id": self.window_id,
            "title": self.title,
            "process_name": self.process_name,
            "process_id": self.process_id,
            "is_visible": self.is_visible,
            "is_focused": self.is_focused,
            "bounds": self.bounds,
        }


class DesktopCapability(CapabilityBase):
    """
    Desktop automation capability.

    Provides:
    - Window detection and listing
    - Process-window association
    - Window state monitoring
    - UI interaction abstraction hooks
    - Future mouse/keyboard automation hooks
    """

    def __init__(self) -> None:
        super().__init__()
        self._event_callbacks: Dict[DesktopEvent, List[Callable]] = {}
        self._monitoring: bool = False
        self._monitor_task: Optional[asyncio.Task] = None

    @property
    def name(self) -> str:
        return "desktop"

    @property
    def version(self) -> str:
        return "1.0.0"

    @property
    def description(self) -> str:
        return (
            "Desktop automation foundation providing window detection, "
            "process-window association, and UI interaction hooks for "
            "future automation capabilities."
        )

    async def initialize(self, context: ExecutionContext) -> None:
        """Initialize the desktop capability."""
        self._context = context
        self._initialized = True
        logger.info("Desktop capability initialized")

    async def shutdown(self) -> None:
        """Shutdown desktop monitoring."""
        self._monitoring = False
        if self._monitor_task:
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass
        self._initialized = False
        logger.info("Desktop capability shut down")

    async def health_check(self) -> Dict[str, Any]:
        """Check desktop capability health."""
        return {
            "healthy": self._initialized,
            "monitoring": self._monitoring,
            "initialized": self._initialized,
        }

    async def get_capabilities(self) -> List[Dict[str, Any]]:
        """List desktop operations."""
        return [
            {
                "name": "list_windows",
                "description": "List all visible desktop windows",
                "parameters": [],
            },
            {
                "name": "find_window",
                "description": "Find a window by title or process name",
                "parameters": ["title_contains", "process_name"],
            },
            {
                "name": "get_window_info",
                "description": "Get detailed information about a window",
                "parameters": ["window_id"],
            },
            {
                "name": "get_foreground_window",
                "description": "Get the currently focused window",
                "parameters": [],
            },
            {
                "name": "start_monitoring",
                "description": "Start monitoring desktop events",
                "parameters": [],
            },
            {
                "name": "stop_monitoring",
                "description": "Stop monitoring desktop events",
                "parameters": [],
            },
        ]

    # --- Window Operations ---

    async def list_windows(self) -> CapabilityResult:
        """
        List all visible desktop windows.

        Returns:
            CapabilityResult with list of windows
        """
        try:
            windows = await self._enumerate_windows()
            return CapabilityResult(
                success=True,
                capability=self.name,
                data={
                    "windows": [w.to_dict() for w in windows],
                    "count": len(windows),
                },
            )
        except Exception as e:
            return CapabilityResult(
                success=False,
                capability=self.name,
                error=str(e),
            )

    async def find_window(
        self,
        title_contains: Optional[str] = None,
        process_name: Optional[str] = None,
    ) -> CapabilityResult:
        """
        Find a window by title or process name.

        Args:
            title_contains: Substring to match in window title
            process_name: Process name to match

        Returns:
            CapabilityResult with matching windows
        """
        try:
            windows = await self._enumerate_windows()
            matches = []

            for window in windows:
                if title_contains and title_contains.lower() in window.title.lower():
                    matches.append(window)
                elif process_name and process_name.lower() in window.process_name.lower():
                    matches.append(window)

            return CapabilityResult(
                success=len(matches) > 0,
                capability=self.name,
                data={
                    "windows": [w.to_dict() for w in matches],
                    "count": len(matches),
                },
            )
        except Exception as e:
            return CapabilityResult(
                success=False,
                capability=self.name,
                error=str(e),
            )

    async def get_window_info(self, window_id: int) -> CapabilityResult:
        """
        Get detailed information about a window.

        Args:
            window_id: The window identifier

        Returns:
            CapabilityResult with window information
        """
        try:
            windows = await self._enumerate_windows()
            for window in windows:
                if window.window_id == window_id:
                    return CapabilityResult(
                        success=True,
                        capability=self.name,
                        data={"window": window.to_dict()},
                    )

            return CapabilityResult(
                success=False,
                capability=self.name,
                error=f"Window '{window_id}' not found",
            )
        except Exception as e:
            return CapabilityResult(
                success=False,
                capability=self.name,
                error=str(e),
            )

    async def get_foreground_window(self) -> CapabilityResult:
        """
        Get the currently focused window.

        Returns:
            CapabilityResult with foreground window info
        """
        try:
            windows = await self._enumerate_windows()
            for window in windows:
                if window.is_focused:
                    return CapabilityResult(
                        success=True,
                        capability=self.name,
                        data={"window": window.to_dict()},
                    )

            return CapabilityResult(
                success=False,
                capability=self.name,
                error="No foreground window found",
            )
        except Exception as e:
            return CapabilityResult(
                success=False,
                capability=self.name,
                error=str(e),
            )

    # --- Monitoring ---

    async def start_monitoring(self) -> CapabilityResult:
        """
        Start monitoring desktop events.

        Returns:
            CapabilityResult
        """
        if self._monitoring:
            return CapabilityResult(
                success=True,
                capability=self.name,
                data={"message": "Already monitoring"},
            )

        self._monitoring = True
        self._monitor_task = asyncio.create_task(self._monitor_loop())
        logger.info("Desktop monitoring started")

        return CapabilityResult(
            success=True,
            capability=self.name,
            data={"message": "Desktop monitoring started"},
        )

    async def stop_monitoring(self) -> CapabilityResult:
        """
        Stop monitoring desktop events.

        Returns:
            CapabilityResult
        """
        self._monitoring = False
        if self._monitor_task:
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass
        logger.info("Desktop monitoring stopped")

        return CapabilityResult(
            success=True,
            capability=self.name,
            data={"message": "Desktop monitoring stopped"},
        )

    # --- Event Callbacks ---

    def on_event(
        self,
        event: DesktopEvent,
        callback: Callable[[Dict[str, Any]], None],
    ) -> None:
        """Register a callback for a desktop event."""
        if event not in self._event_callbacks:
            self._event_callbacks[event] = []
        self._event_callbacks[event].append(callback)

    # --- Internal Methods ---

    async def _enumerate_windows(self) -> List[WindowInfo]:
        """
        Enumerate desktop windows using platform-specific methods.

        Uses PowerShell on Windows, AppleScript on macOS, and
        xdotool/wmctrl on Linux.
        """
        windows = []

        if os.name == "nt":
            # Windows: Use PowerShell to enumerate windows
            try:
                ps_script = """
                Add-Type @"
                    using System;
                    using System.Runtime.InteropServices;
                    using System.Text;
                    using System.Diagnostics;
                    public class WinAPI {
                        [DllImport("user32.dll")]
                        public static extern IntPtr GetForegroundWindow();
                        [DllImport("user32.dll")]
                        public static extern bool EnumWindows(EnumWindowsProc enumProc, IntPtr lParam);
                        [DllImport("user32.dll")]
                        public static extern int GetWindowText(IntPtr hWnd, StringBuilder text, int count);
                        [DllImport("user32.dll")]
                        public static extern bool IsWindowVisible(IntPtr hWnd);
                        [DllImport("user32.dll")]
                        public static extern uint GetWindowThreadProcessId(IntPtr hWnd, out uint processId);
                        public delegate bool EnumWindowsProc(IntPtr hWnd, IntPtr lParam);
                    }
"@
                $foreground = [WinAPI]::GetForegroundWindow()
                $windows = @()
                $enumProc = {
                    param($hWnd, $lParam)
                    if ([WinAPI]::IsWindowVisible($hWnd)) {
                        $sb = New-Object System.Text.StringBuilder 256
                        [WinAPI]::GetWindowText($hWnd, $sb, 256)
                        $title = $sb.ToString()
                        if ($title -ne "") {
                            $pid = 0
                            [WinAPI]::GetWindowThreadProcessId($hWnd, [ref]$pid)
                            $proc = Get-Process -Id $pid -ErrorAction SilentlyContinue
                            $windows += [PSCustomObject]@{
                                WindowId = [int]$hWnd
                                Title = $title
                                ProcessName = if ($proc) { $proc.ProcessName } else { "" }
                                ProcessId = $pid
                                IsVisible = $true
                                IsFocused = ($hWnd -eq $foreground)
                            }
                        }
                    }
                    return $true
                }
                $handle = [System.Runtime.InteropServices.GCHandle]::Alloc($windows)
                try {
                    [WinAPI]::EnumWindows($enumProc, [IntPtr]::Zero)
                } finally {
                    $handle.Free()
                }
                $windows | ConvertTo-Json -Compress
                """
                proc = await asyncio.create_subprocess_exec(
                    "powershell.exe", "-NoProfile", "-Command", ps_script,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=15)
                output = stdout.decode("utf-8", errors="replace").strip()

                if output:
                    import json
                    data = json.loads(output)
                    if isinstance(data, list):
                        for item in data:
                            windows.append(WindowInfo(
                                window_id=item.get("WindowId"),
                                title=item.get("Title", ""),
                                process_name=item.get("ProcessName", ""),
                                process_id=item.get("ProcessId"),
                                is_visible=item.get("IsVisible", True),
                                is_focused=item.get("IsFocused", False),
                            ))
                    elif isinstance(data, dict):
                        windows.append(WindowInfo(
                            window_id=data.get("WindowId"),
                            title=data.get("Title", ""),
                            process_name=data.get("ProcessName", ""),
                            process_id=data.get("ProcessId"),
                            is_visible=data.get("IsVisible", True),
                            is_focused=data.get("IsFocused", False),
                        ))

            except Exception as e:
                logger.error("Window enumeration error", error=str(e))

        elif sys.platform == "darwin":
            # macOS: Use AppleScript
            try:
                ascript = '''
                tell application "System Events"
                    set windowList to {}
                    set procList to every process whose visible is true
                    repeat with proc in procList
                        set winList to every window of proc
                        repeat with win in winList
                            set end of windowList to {|title|:name of win, |pid|:unix id of proc, |proc|:name of proc}
                        end repeat
                    end repeat
                    return windowList
                end tell
                '''
                proc = await asyncio.create_subprocess_exec(
                    "osascript", "-e", ascript,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=15)
                # Parse AppleScript output
                for line in stdout.decode().split("\n"):
                    if line.strip():
                        windows.append(WindowInfo(
                            title=line.strip(),
                            process_name="unknown",
                        ))
            except Exception as e:
                logger.error("macOS window enumeration error", error=str(e))

        else:
            # Linux: Use wmctrl
            try:
                proc = await asyncio.create_subprocess_exec(
                    "wmctrl", "-l",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=10)
                for line in stdout.decode().split("\n"):
                    if line.strip():
                        parts = line.split(None, 3)
                        if len(parts) >= 4:
                            windows.append(WindowInfo(
                                title=parts[3],
                                process_name=parts[2],
                            ))
            except Exception:
                pass  # wmctrl not available

        return windows

    async def _monitor_loop(self) -> None:
        """Background loop for monitoring desktop events."""
        previous_windows: List[WindowInfo] = []

        while self._monitoring:
            try:
                current_windows = await self._enumerate_windows()

                # Detect new windows
                current_ids = {w.window_id for w in current_windows if w.window_id}
                previous_ids = {w.window_id for w in previous_windows if w.window_id}

                new_ids = current_ids - previous_ids
                closed_ids = previous_ids - current_ids

                for window in current_windows:
                    if window.window_id in new_ids:
                        self._emit_event(DesktopEvent.WINDOW_OPENED, window.to_dict())

                for window in previous_windows:
                    if window.window_id in closed_ids:
                        self._emit_event(DesktopEvent.WINDOW_CLOSED, window.to_dict())

                previous_windows = current_windows
                await asyncio.sleep(2)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Desktop monitor error", error=str(e))
                await asyncio.sleep(5)

    def _emit_event(self, event: DesktopEvent, data: Dict[str, Any]) -> None:
        """Emit a desktop event to registered callbacks."""
        callbacks = self._event_callbacks.get(event, [])
        for callback in callbacks:
            try:
                callback(data)
            except Exception as e:
                logger.error("Event callback error", error=str(e))
