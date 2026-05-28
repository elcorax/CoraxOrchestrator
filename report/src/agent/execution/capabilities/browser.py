"""
Corax Orchestrator - Browser Capability.

Provides browser automation foundation for the autonomous agent.
Supports browser launch management, tab/session management, and
future Playwright/Selenium integration hooks.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Callable
import asyncio
import os
import sys
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


@dataclass
class BrowserTab:
    """
    Represents a browser tab.

    Tracks tab state for session management and automation.
    """
    tab_id: str
    title: str = ""
    url: str = ""
    is_active: bool = False
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "tab_id": self.tab_id,
            "title": self.title,
            "url": self.url,
            "is_active": self.is_active,
        }


@dataclass
class BrowserInstance:
    """
    Represents a browser instance.

    Manages a browser process and its tabs/sessions for
    automation purposes.
    """
    instance_id: str
    browser_type: str  # chrome, firefox, edge, etc.
    headless: bool = False
    pid: Optional[int] = None
    is_running: bool = False
    tabs: List[BrowserTab] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    data_dir: Optional[str] = None
    remote_debug_port: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "instance_id": self.instance_id,
            "browser_type": self.browser_type,
            "headless": self.headless,
            "pid": self.pid,
            "is_running": self.is_running,
            "tab_count": len(self.tabs),
            "created_at": self.created_at,
            "remote_debug_port": self.remote_debug_port,
        }


class BrowserCapability(CapabilityBase):
    """
    Browser automation capability.

    Provides:
    - Browser launch management (Chrome, Firefox, Edge)
    - Tab/session management
    - Headless mode support
    - Remote debugging port management
    - Future Playwright/Selenium integration hooks
    - Browser detection and discovery
    """

    # Known browser executable paths
    BROWSER_PATHS = {
        "chrome": {
            "win32": [
                r"C:\Program Files\Google\Chrome\Application\chrome.exe",
                r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
                os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
            ],
            "darwin": [
                "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            ],
            "linux": [
                "/usr/bin/google-chrome",
                "/usr/bin/chromium-browser",
                "/usr/bin/chromium",
            ],
        },
        "firefox": {
            "win32": [
                r"C:\Program Files\Mozilla Firefox\firefox.exe",
                r"C:\Program Files (x86)\Mozilla Firefox\firefox.exe",
            ],
            "darwin": [
                "/Applications/Firefox.app/Contents/MacOS/firefox",
            ],
            "linux": [
                "/usr/bin/firefox",
            ],
        },
        "edge": {
            "win32": [
                r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
                os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\Edge\Application\msedge.exe"),
            ],
            "darwin": [
                "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
            ],
            "linux": [
                "/usr/bin/microsoft-edge",
            ],
        },
    }

    def __init__(self) -> None:
        super().__init__()
        self._instances: Dict[str, BrowserInstance] = {}
        self._next_debug_port: int = 9222

    @property
    def name(self) -> str:
        return "browser"

    @property
    def version(self) -> str:
        return "1.0.0"

    @property
    def description(self) -> str:
        return (
            "Browser automation foundation providing browser launch "
            "management, tab/session management, and integration hooks "
            "for future Playwright/Selenium automation."
        )

    async def initialize(self, context: ExecutionContext) -> None:
        """Initialize the browser capability."""
        self._context = context
        self._initialized = True
        logger.info("Browser capability initialized")

    async def shutdown(self) -> None:
        """Shutdown all browser instances."""
        for instance_id in list(self._instances.keys()):
            await self.close_browser(instance_id)
        self._initialized = False
        logger.info("Browser capability shut down")

    async def health_check(self) -> Dict[str, Any]:
        """Check browser capability health."""
        return {
            "healthy": self._initialized,
            "active_instances": len(self._instances),
            "running_instances": sum(
                1 for i in self._instances.values() if i.is_running
            ),
            "initialized": self._initialized,
        }

    async def get_capabilities(self) -> List[Dict[str, Any]]:
        """List browser operations."""
        return [
            {
                "name": "launch_browser",
                "description": "Launch a browser instance",
                "parameters": ["browser_type", "headless", "url"],
            },
            {
                "name": "close_browser",
                "description": "Close a browser instance",
                "parameters": ["instance_id"],
            },
            {
                "name": "list_instances",
                "description": "List all browser instances",
                "parameters": [],
            },
            {
                "name": "get_instance_info",
                "description": "Get information about a browser instance",
                "parameters": ["instance_id"],
            },
            {
                "name": "detect_browsers",
                "description": "Detect installed browsers on the system",
                "parameters": [],
            },
            {
                "name": "create_tab",
                "description": "Create a new tab in a browser instance",
                "parameters": ["instance_id", "url"],
            },
            {
                "name": "list_tabs",
                "description": "List tabs in a browser instance",
                "parameters": ["instance_id"],
            },
        ]

    # --- Browser Launch Management ---

    async def launch_browser(
        self,
        browser_type: str = "chrome",
        headless: bool = False,
        url: Optional[str] = None,
        data_dir: Optional[str] = None,
    ) -> CapabilityResult:
        """
        Launch a browser instance.

        Args:
            browser_type: Type of browser (chrome, firefox, edge)
            headless: Whether to run in headless mode
            url: URL to navigate to on launch
            data_dir: Custom data directory for the browser

        Returns:
            CapabilityResult with instance information
        """
        if not self._initialized:
            return CapabilityResult(
                success=False,
                capability=self.name,
                error="Browser capability not initialized",
            )

        # Find browser executable
        browser_path = self._find_browser(browser_type)
        if not browser_path:
            return CapabilityResult(
                success=False,
                capability=self.name,
                error=f"Browser '{browser_type}' not found on system",
            )

        instance_id = f"browser_{uuid4().hex[:8]}"
        debug_port = self._next_debug_port
        self._next_debug_port += 1

        # Build command
        cmd = [browser_path]

        if headless:
            if browser_type in ("chrome", "edge"):
                cmd.extend(["--headless=new"])
            elif browser_type == "firefox":
                cmd.extend(["--headless"])

        # Add remote debugging for Chrome/Edge
        if browser_type in ("chrome", "edge"):
            cmd.extend([
                f"--remote-debugging-port={debug_port}",
                "--no-first-run",
                "--no-default-browser-check",
            ])

        # Add data directory
        if data_dir:
            if browser_type in ("chrome", "edge"):
                cmd.append(f"--user-data-dir={data_dir}")
        else:
            # Use temporary directory
            import tempfile
            data_dir = tempfile.mkdtemp(prefix=f"corax_browser_{instance_id[:8]}_")
            if browser_type in ("chrome", "edge"):
                cmd.append(f"--user-data-dir={data_dir}")

        # Add URL
        if url:
            cmd.append(url)

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            instance = BrowserInstance(
                instance_id=instance_id,
                browser_type=browser_type,
                headless=headless,
                pid=proc.pid,
                is_running=True,
                data_dir=data_dir,
                remote_debug_port=debug_port if browser_type in ("chrome", "edge") else None,
            )

            self._instances[instance_id] = instance

            # Start background monitoring
            asyncio.create_task(self._monitor_instance(instance_id, proc))

            logger.info(
                "Browser launched",
                instance_id=instance_id,
                browser=browser_type,
                headless=headless,
                pid=proc.pid,
            )

            return CapabilityResult(
                success=True,
                capability=self.name,
                data=instance.to_dict(),
            )

        except FileNotFoundError:
            return CapabilityResult(
                success=False,
                capability=self.name,
                error=f"Browser executable not found: {browser_path}",
            )
        except Exception as e:
            return CapabilityResult(
                success=False,
                capability=self.name,
                error=str(e),
            )

    async def close_browser(self, instance_id: str) -> CapabilityResult:
        """
        Close a browser instance.

        Args:
            instance_id: The instance to close

        Returns:
            CapabilityResult
        """
        instance = self._instances.get(instance_id)
        if not instance:
            return CapabilityResult(
                success=False,
                capability=self.name,
                error=f"Instance '{instance_id}' not found",
            )

        try:
            # Kill the process
            if instance.pid:
                if os.name == "nt":
                    os.system(f"taskkill /F /PID {instance.pid} > nul 2>&1")
                else:
                    os.system(f"kill -9 {instance.pid} 2>/dev/null")

            instance.is_running = False
            del self._instances[instance_id]

            logger.info("Browser closed", instance_id=instance_id)

            return CapabilityResult(
                success=True,
                capability=self.name,
                data={"instance_id": instance_id},
            )

        except Exception as e:
            return CapabilityResult(
                success=False,
                capability=self.name,
                error=str(e),
            )

    # --- Instance Management ---

    async def list_instances(self) -> List[Dict[str, Any]]:
        """List all browser instances."""
        return [
            instance.to_dict() for instance in self._instances.values()
        ]

    async def get_instance_info(self, instance_id: str) -> Optional[Dict[str, Any]]:
        """Get information about a browser instance."""
        instance = self._instances.get(instance_id)
        return instance.to_dict() if instance else None

    # --- Browser Detection ---

    async def detect_browsers(self) -> Dict[str, Any]:
        """
        Detect installed browsers on the system.

        Returns:
            Dict with detected browsers and their paths
        """
        detected = {}
        platform_key = "win32" if os.name == "nt" else (
            "darwin" if sys.platform == "darwin" else "linux"
        )

        for browser_name, paths in self.BROWSER_PATHS.items():
            platform_paths = paths.get(platform_key, [])
            for path in platform_paths:
                if os.path.exists(path):
                    detected[browser_name] = path
                    break

        return {
            "detected_browsers": detected,
            "count": len(detected),
        }

    # --- Tab Management ---

    async def create_tab(
        self,
        instance_id: str,
        url: str = "about:blank",
    ) -> CapabilityResult:
        """
        Create a new tab in a browser instance.

        Args:
            instance_id: The browser instance
            url: URL to navigate to

        Returns:
            CapabilityResult with tab information
        """
        instance = self._instances.get(instance_id)
        if not instance:
            return CapabilityResult(
                success=False,
                capability=self.name,
                error=f"Instance '{instance_id}' not found",
            )

        tab = BrowserTab(
            tab_id=f"tab_{uuid4().hex[:8]}",
            url=url,
        )
        instance.tabs.append(tab)

        # If remote debugging is available, navigate via CDP
        if instance.remote_debug_port and url != "about:blank":
            asyncio.create_task(
                self._navigate_via_cdp(instance.remote_debug_port, url)
            )

        return CapabilityResult(
            success=True,
            capability=self.name,
            data=tab.to_dict(),
        )

    async def list_tabs(self, instance_id: str) -> CapabilityResult:
        """
        List tabs in a browser instance.

        Args:
            instance_id: The browser instance

        Returns:
            CapabilityResult with tab list
        """
        instance = self._instances.get(instance_id)
        if not instance:
            return CapabilityResult(
                success=False,
                capability=self.name,
                error=f"Instance '{instance_id}' not found",
            )

        return CapabilityResult(
            success=True,
            capability=self.name,
            data={
                "tabs": [tab.to_dict() for tab in instance.tabs],
                "count": len(instance.tabs),
            },
        )

    # --- Internal Methods ---

    def _find_browser(self, browser_type: str) -> Optional[str]:
        """Find the browser executable path."""
        platform_key = "win32" if os.name == "nt" else (
            "darwin" if sys.platform == "darwin" else "linux"
        )

        paths = self.BROWSER_PATHS.get(browser_type, {}).get(platform_key, [])
        for path in paths:
            if os.path.exists(path):
                return path

        return None

    async def _monitor_instance(
        self,
        instance_id: str,
        proc: asyncio.subprocess.Process,
    ) -> None:
        """Monitor a browser process and update state on exit."""
        try:
            await proc.wait()
            instance = self._instances.get(instance_id)
            if instance:
                instance.is_running = False
                logger.info(
                    "Browser process exited",
                    instance_id=instance_id,
                    return_code=proc.returncode,
                )
        except Exception as e:
            logger.error(
                "Browser monitor error",
                instance_id=instance_id,
                error=str(e),
            )

    async def _navigate_via_cdp(self, port: int, url: str) -> None:
        """
        Navigate to a URL via Chrome DevTools Protocol.

        This is a foundation for future Playwright/Selenium integration.
        Currently uses a simple HTTP request to the CDP endpoint.
        """
        try:
            import json
            import http.client

            # Get list of available tabs via CDP
            conn = http.client.HTTPConnection(f"127.0.0.1:{port}", timeout=5)
            conn.request("GET", "/json")
            response = conn.getresponse()
            data = json.loads(response.read().decode())
            conn.close()

            if data:
                # Navigate the first tab
                tab_id = data[0].get("id")
                if tab_id:
                    conn = http.client.HTTPConnection(f"127.0.0.1:{port}", timeout=5)
                    payload = json.dumps({
                        "id": 1,
                        "method": "Page.navigate",
                        "params": {"url": url},
                    })
                    conn.request("POST", f"/session/{tab_id}", payload, {
                        "Content-Type": "application/json",
                    })
                    conn.getresponse()
                    conn.close()

        except Exception as e:
            logger.debug("CDP navigation not available", error=str(e))
