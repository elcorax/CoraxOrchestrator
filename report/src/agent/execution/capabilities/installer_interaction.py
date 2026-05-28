"""
Corax Orchestrator - Installer Interaction Capability.

Provides abstraction for interacting with software installers.
Supports silent installers, interactive installers, unattended
install strategies, and installer state tracking.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, Any, List, Optional, Callable
from pathlib import Path
import asyncio
import os
import time
import re
from uuid import uuid4

from src.agent.execution.capabilities.base import (
    CapabilityBase,
    CapabilityResult,
    CapabilityError,
    ExecutionContext,
)
from src.core.logging import get_logger

logger = get_logger(__name__)


class InstallStrategy(Enum):
    """Available installation strategies."""
    SILENT = "silent"
    UNATTENDED = "unattended"
    INTERACTIVE = "interactive"
    PACKAGE_MANAGER = "package_manager"
    PORTABLE = "portable"


class InstallerState(Enum):
    """States in the installer lifecycle."""
    PENDING = "pending"
    DOWNLOADING = "downloading"
    INSTALLING = "installing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    ROLLED_BACK = "rolled_back"


@dataclass
class InstallerConfig:
    """Configuration for an installer interaction."""
    installer_path: str
    installer_type: str  # exe, msi, dmg, pkg, sh, appimage
    install_strategy: InstallStrategy = InstallStrategy.SILENT
    silent_flags: List[str] = field(default_factory=list)
    unattended_flags: List[str] = field(default_factory=list)
    interactive_responses: List[str] = field(default_factory=list)
    expected_duration_minutes: int = 10
    requires_admin: bool = True
    requires_reboot: bool = False
    working_directory: Optional[str] = None
    environment: Dict[str, str] = field(default_factory=dict)
    validation_command: Optional[str] = None
    rollback_command: Optional[str] = None
    install_log_path: Optional[str] = None
    download_url: Optional[str] = None
    expected_checksum: Optional[str] = None
    checksum_type: str = "sha256"


@dataclass
class InstallerStateInfo:
    """
    Tracks the state of an installer operation.

    Provides complete lifecycle tracking for installer interactions
    including progress, errors, and recovery information.
    """
    install_id: str
    tool_name: str
    config: InstallerConfig
    state: InstallerState = InstallerState.PENDING
    progress: float = 0.0  # 0.0 to 1.0
    stdout: str = ""
    stderr: str = ""
    exit_code: Optional[int] = None
    error_message: Optional[str] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    duration_ms: Optional[float] = None
    retry_count: int = 0
    max_retries: int = 3
    events: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "install_id": self.install_id,
            "tool_name": self.tool_name,
            "state": self.state.value,
            "progress": self.progress,
            "exit_code": self.exit_code,
            "error_message": self.error_message,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "duration_ms": self.duration_ms,
            "retry_count": self.retry_count,
        }


class InstallerInteractionCapability(CapabilityBase):
    """
    Installer interaction capability.

    Provides:
    - Silent installer execution
    - Unattended install strategies
    - Interactive installer support with response automation
    - Installer detection and validation
    - Installer state tracking
    - Progress monitoring
    - Rollback support
    - Checksum verification
    """

    # Known silent flags for common installers
    SILENT_FLAGS_MAP: Dict[str, List[str]] = {
        ".exe": ["/S", "/silent", "/quiet", "/verysilent"],
        ".msi": ["/quiet", "/qn", "/passive"],
        ".dmg": [],  # macOS - handled differently
        ".pkg": ["--quiet"],  # macOS
        ".sh": ["--quiet", "--silent", "-y"],
        ".AppImage": ["--no-sandbox"],
    }

    # Known unattended flags
    UNATTENDED_FLAGS_MAP: Dict[str, List[str]] = {
        ".exe": ["/S", "/verysilent", "/suppressmsgboxes"],
        ".msi": ["/quiet", "/norestart", "/log"],
        ".pkg": ["--quiet"],
    }

    def __init__(self) -> None:
        super().__init__()
        self._installers: Dict[str, InstallerStateInfo] = {}
        self._progress_callbacks: List[Callable] = []

    @property
    def name(self) -> str:
        return "installer_interaction"

    @property
    def version(self) -> str:
        return "1.0.0"

    @property
    def description(self) -> str:
        return (
            "Abstraction for interacting with software installers. "
            "Supports silent, unattended, and interactive installation "
            "strategies with progress tracking and rollback."
        )

    async def initialize(self, context: ExecutionContext) -> None:
        """Initialize the installer interaction capability."""
        self._context = context
        self._initialized = True
        logger.info("Installer interaction capability initialized")

    async def shutdown(self) -> None:
        """Shutdown and cancel any active installers."""
        for install_id, info in self._installers.items():
            if info.state in (InstallerState.DOWNLOADING, InstallerState.INSTALLING):
                info.state = InstallerState.CANCELLED
        self._initialized = False
        logger.info("Installer interaction capability shut down")

    async def health_check(self) -> Dict[str, Any]:
        """Check installer capability health."""
        active = sum(
            1 for i in self._installers.values()
            if i.state in (InstallerState.DOWNLOADING, InstallerState.INSTALLING)
        )
        return {
            "healthy": self._initialized,
            "active_installers": active,
            "total_tracked": len(self._installers),
            "initialized": self._initialized,
        }

    async def get_capabilities(self) -> List[Dict[str, Any]]:
        """List installer operations."""
        return [
            {
                "name": "install_silent",
                "description": "Run a silent installation",
                "parameters": ["installer_path", "tool_name", "silent_flags"],
            },
            {
                "name": "install_unattended",
                "description": "Run an unattended installation",
                "parameters": ["installer_path", "tool_name", "unattended_flags"],
            },
            {
                "name": "install_interactive",
                "description": "Run an interactive installation with automated responses",
                "parameters": ["installer_path", "tool_name", "responses"],
            },
            {
                "name": "detect_installer_type",
                "description": "Detect the type of an installer file",
                "parameters": ["installer_path"],
            },
            {
                "name": "validate_installation",
                "description": "Validate that an installation succeeded",
                "parameters": ["install_id", "validation_command"],
            },
            {
                "name": "rollback_installation",
                "description": "Rollback a completed installation",
                "parameters": ["install_id"],
            },
            {
                "name": "get_installer_status",
                "description": "Get the status of an installer",
                "parameters": ["install_id"],
            },
            {
                "name": "list_installers",
                "description": "List all tracked installer operations",
                "parameters": [],
            },
        ]

    # --- Installation Methods ---

    async def install_silent(
        self,
        installer_path: str,
        tool_name: str,
        silent_flags: Optional[List[str]] = None,
        config: Optional[InstallerConfig] = None,
    ) -> CapabilityResult:
        """
        Run a silent installation.

        Args:
            installer_path: Path to the installer
            tool_name: Name of the tool being installed
            silent_flags: Additional silent flags
            config: Full installer configuration

        Returns:
            CapabilityResult with installation status
        """
        if not self._initialized:
            return CapabilityResult(
                success=False,
                capability=self.name,
                error="Installer capability not initialized",
            )

        # Build configuration
        if config is None:
            installer_type = self._detect_installer_type(installer_path)
            flags = silent_flags or self.SILENT_FLAGS_MAP.get(installer_type, [])
            config = InstallerConfig(
                installer_path=installer_path,
                installer_type=installer_type,
                install_strategy=InstallStrategy.SILENT,
                silent_flags=flags,
            )

        return await self._execute_installer(config, tool_name)

    async def install_unattended(
        self,
        installer_path: str,
        tool_name: str,
        unattended_flags: Optional[List[str]] = None,
        config: Optional[InstallerConfig] = None,
    ) -> CapabilityResult:
        """
        Run an unattended installation.

        Args:
            installer_path: Path to the installer
            tool_name: Name of the tool being installed
            unattended_flags: Additional unattended flags
            config: Full installer configuration

        Returns:
            CapabilityResult with installation status
        """
        if not self._initialized:
            return CapabilityResult(
                success=False,
                capability=self.name,
                error="Installer capability not initialized",
            )

        if config is None:
            installer_type = self._detect_installer_type(installer_path)
            flags = unattended_flags or self.UNATTENDED_FLAGS_MAP.get(installer_type, [])
            config = InstallerConfig(
                installer_path=installer_path,
                installer_type=installer_type,
                install_strategy=InstallStrategy.UNATTENDED,
                unattended_flags=flags,
            )

        return await self._execute_installer(config, tool_name)

    async def install_interactive(
        self,
        installer_path: str,
        tool_name: str,
        responses: List[str],
        config: Optional[InstallerConfig] = None,
    ) -> CapabilityResult:
        """
        Run an interactive installation with automated responses.

        Args:
            installer_path: Path to the installer
            tool_name: Name of the tool being installed
            responses: List of responses to send to the installer prompts
            config: Full installer configuration

        Returns:
            CapabilityResult with installation status
        """
        if not self._initialized:
            return CapabilityResult(
                success=False,
                capability=self.name,
                error="Installer capability not initialized",
            )

        if config is None:
            installer_type = self._detect_installer_type(installer_path)
            config = InstallerConfig(
                installer_path=installer_path,
                installer_type=installer_type,
                install_strategy=InstallStrategy.INTERACTIVE,
                interactive_responses=responses,
            )

        return await self._execute_installer(config, tool_name)

    # --- Installer Detection ---

    async def detect_installer_type(self, installer_path: str) -> str:
        """
        Detect the type of an installer file.

        Args:
            installer_path: Path to the installer

        Returns:
            The installer type extension (e.g., '.exe', '.msi')
        """
        return self._detect_installer_type(installer_path)

    def _detect_installer_type(self, installer_path: str) -> str:
        """Detect installer type from file extension."""
        ext = Path(installer_path).suffix.lower()
        if ext in self.SILENT_FLAGS_MAP:
            return ext
        return ext or ".exe"

    # --- Validation and Rollback ---

    async def validate_installation(
        self,
        install_id: str,
        validation_command: Optional[str] = None,
    ) -> CapabilityResult:
        """
        Validate that an installation succeeded.

        Args:
            install_id: The installation to validate
            validation_command: Command to run for validation

        Returns:
            CapabilityResult with validation status
        """
        install_info = self._installers.get(install_id)
        if not install_info:
            return CapabilityResult(
                success=False,
                capability=self.name,
                error=f"Installation '{install_id}' not found",
            )

        cmd = validation_command or install_info.config.validation_command
        if not cmd:
            return CapabilityResult(
                success=True,
                capability=self.name,
                data={
                    "install_id": install_id,
                    "state": install_info.state.value,
                    "validated": install_info.state == InstallerState.COMPLETED,
                },
            )

        # Run validation command
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd.split(),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=30)

            validated = proc.returncode == 0
            if validated:
                install_info.state = InstallerState.COMPLETED

            return CapabilityResult(
                success=validated,
                capability=self.name,
                data={
                    "install_id": install_id,
                    "validated": validated,
                    "exit_code": proc.returncode,
                    "stdout": stdout.decode("utf-8", errors="replace"),
                },
            )

        except Exception as e:
            return CapabilityResult(
                success=False,
                capability=self.name,
                error=f"Validation failed: {e}",
                data={"install_id": install_id},
            )

    async def rollback_installation(self, install_id: str) -> CapabilityResult:
        """
        Rollback a completed installation.

        Args:
            install_id: The installation to rollback

        Returns:
            CapabilityResult with rollback status
        """
        install_info = self._installers.get(install_id)
        if not install_info:
            return CapabilityResult(
                success=False,
                capability=self.name,
                error=f"Installation '{install_id}' not found",
            )

        rollback_cmd = install_info.config.rollback_command
        if not rollback_cmd:
            return CapabilityResult(
                success=False,
                capability=self.name,
                error="No rollback command configured for this installer",
            )

        try:
            proc = await asyncio.create_subprocess_exec(
                *rollback_cmd.split(),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=60)

            if proc.returncode == 0:
                install_info.state = InstallerState.ROLLED_BACK
                logger.info(
                    "Installation rolled back",
                    install_id=install_id,
                    tool=install_info.tool_name,
                )

            return CapabilityResult(
                success=proc.returncode == 0,
                capability=self.name,
                data={
                    "install_id": install_id,
                    "state": install_info.state.value,
                    "exit_code": proc.returncode,
                },
            )

        except Exception as e:
            return CapabilityResult(
                success=False,
                capability=self.name,
                error=f"Rollback failed: {e}",
            )

    # --- Status Queries ---

    async def get_installer_status(self, install_id: str) -> Optional[Dict[str, Any]]:
        """Get the status of an installer operation."""
        install_info = self._installers.get(install_id)
        return install_info.to_dict() if install_info else None

    async def list_installers(self) -> List[Dict[str, Any]]:
        """List all tracked installer operations."""
        return [info.to_dict() for info in self._installers.values()]

    # --- Progress Callbacks ---

    def on_progress(self, callback: Callable[[str, float], None]) -> None:
        """Register a progress callback."""
        self._progress_callbacks.append(callback)

    # --- Internal Methods ---

    async def _execute_installer(
        self,
        config: InstallerConfig,
        tool_name: str,
    ) -> CapabilityResult:
        """Execute an installer with the given configuration."""
        install_id = f"install_{uuid4().hex[:8]}"
        start_time = time.time()

        install_info = InstallerStateInfo(
            install_id=install_id,
            tool_name=tool_name,
            config=config,
            state=InstallerState.INSTALLING,
            started_at=datetime.now(timezone.utc).isoformat(),
        )
        self._installers[install_id] = install_info

        logger.info(
            "Starting installation",
            install_id=install_id,
            tool=tool_name,
            strategy=config.install_strategy.value,
            installer=config.installer_path,
        )

        # Build command
        cmd_parts = self._build_installer_command(config)

        for attempt in range(install_info.max_retries + 1):
            if attempt > 0:
                logger.info(
                    "Retrying installation",
                    install_id=install_id,
                    attempt=attempt,
                )
                install_info.retry_count = attempt
                await asyncio.sleep(2 ** attempt)

            try:
                proc = await asyncio.create_subprocess_exec(
                    *cmd_parts,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    cwd=config.working_directory,
                    env={**os.environ, **config.environment},
                )

                # Handle interactive installers
                if config.install_strategy == InstallStrategy.INTERACTIVE:
                    asyncio.create_task(
                        self._handle_interactive(proc, config.interactive_responses)
                    )

                try:
                    stdout, stderr = await asyncio.wait_for(
                        proc.communicate(),
                        timeout=config.expected_duration_minutes * 60,
                    )

                    install_info.stdout = stdout.decode("utf-8", errors="replace")
                    install_info.stderr = stderr.decode("utf-8", errors="replace")
                    install_info.exit_code = proc.returncode
                    install_info.duration_ms = (time.time() - start_time) * 1000

                    if proc.returncode == 0:
                        install_info.state = InstallerState.COMPLETED
                        install_info.progress = 1.0
                        install_info.completed_at = datetime.now(timezone.utc).isoformat()

                        self._notify_progress(install_id, 1.0)

                        logger.info(
                            "Installation completed",
                            install_id=install_id,
                            tool=tool_name,
                            duration_ms=f"{install_info.duration_ms:.0f}",
                        )

                        return CapabilityResult(
                            success=True,
                            capability=self.name,
                            data={
                                "install_id": install_id,
                                "tool_name": tool_name,
                                "state": InstallerState.COMPLETED.value,
                                "duration_ms": install_info.duration_ms,
                            },
                            duration_ms=install_info.duration_ms,
                        )
                    else:
                        install_info.state = InstallerState.FAILED
                        install_info.error_message = (
                            f"Installer exited with code {proc.returncode}"
                        )
                        install_info.completed_at = datetime.now(timezone.utc).isoformat()

                        if attempt < install_info.max_retries:
                            continue

                        return CapabilityResult(
                            success=False,
                            capability=self.name,
                            error=install_info.error_message,
                            data={
                                "install_id": install_id,
                                "tool_name": tool_name,
                                "exit_code": proc.returncode,
                                "stderr": install_info.stderr,
                            },
                            duration_ms=install_info.duration_ms,
                        )

                except asyncio.TimeoutError:
                    proc.kill()
                    await proc.wait()
                    install_info.state = InstallerState.FAILED
                    install_info.error_message = (
                        f"Installation timed out after "
                        f"{config.expected_duration_minutes} minutes"
                    )
                    install_info.completed_at = datetime.now(timezone.utc).isoformat()
                    install_info.duration_ms = (time.time() - start_time) * 1000

                    if attempt < install_info.max_retries:
                        continue

                    return CapabilityResult(
                        success=False,
                        capability=self.name,
                        error=install_info.error_message,
                        data={"install_id": install_id},
                    )

            except FileNotFoundError:
                install_info.state = InstallerState.FAILED
                install_info.error_message = (
                    f"Installer not found: {config.installer_path}"
                )
                return CapabilityResult(
                    success=False,
                    capability=self.name,
                    error=install_info.error_message,
                    data={"install_id": install_id},
                )
            except Exception as e:
                install_info.state = InstallerState.FAILED
                install_info.error_message = str(e)
                if attempt < install_info.max_retries:
                    continue
                return CapabilityResult(
                    success=False,
                    capability=self.name,
                    error=str(e),
                    data={"install_id": install_id},
                )

        return CapabilityResult(
            success=False,
            capability=self.name,
            error="All installation retry attempts exhausted",
            data={"install_id": install_id},
        )

    def _build_installer_command(self, config: InstallerConfig) -> List[str]:
        """Build the installer command based on strategy."""
        cmd = [config.installer_path]

        if config.install_strategy == InstallStrategy.SILENT:
            cmd.extend(config.silent_flags)
        elif config.install_strategy == InstallStrategy.UNATTENDED:
            cmd.extend(config.unattended_flags)

        return cmd

    async def _handle_interactive(
        self,
        proc: asyncio.subprocess.Process,
        responses: List[str],
    ) -> None:
        """Handle interactive installer by sending responses."""
        try:
            for response in responses:
                await asyncio.sleep(2)  # Wait for prompt
                if proc.stdin:
                    proc.stdin.write(f"{response}\n".encode())
                    await proc.stdin.drain()
        except Exception as e:
            logger.error("Interactive installer error", error=str(e))

    def _notify_progress(self, install_id: str, progress: float) -> None:
        """Notify progress callbacks."""
        for callback in self._progress_callbacks:
            try:
                callback(install_id, progress)
            except Exception as e:
                logger.error("Progress callback error", error=str(e))
