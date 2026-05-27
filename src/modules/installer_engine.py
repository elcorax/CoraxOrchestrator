"""
Corax Orchestrator - Installer Engine Module.

Orchestrates the installation of tools by coordinating with
platform-specific installers and the tool registry.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, Any, List, Optional, Set, Type

from src.core.logging import get_logger
from src.core.exceptions import InstallationError
from src.modules.tool_registry import ToolRegistry, ToolMetadata
from src.platform.factory import PlatformFactory
from src.platform.base import PlatformBase

logger = get_logger(__name__)


class InstallerStatus(Enum):
    """Status of an installation operation."""
    PENDING = "pending"
    INSTALLING = "installing"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"
    ALREADY_INSTALLED = "already_installed"


@dataclass
class InstallerResult:
    """Result of a single tool installation."""
    tool_name: str
    status: InstallerStatus
    version: Optional[str] = None
    install_path: Optional[str] = None
    error: Optional[str] = None
    duration_seconds: float = 0.0
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "tool_name": self.tool_name,
            "status": self.status.value,
            "version": self.version,
            "install_path": self.install_path,
            "error": self.error,
            "duration_seconds": self.duration_seconds,
            "timestamp": self.timestamp,
        }


@dataclass
class InstallationPlan:
    """A plan for installing multiple tools."""
    tools: List[str]
    install_order: List[str]
    total_tools: int
    estimated_size_mb: int = 0
    requires_admin: bool = False
    requires_restart: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "tools": self.tools,
            "install_order": self.install_order,
            "total_tools": self.total_tools,
            "estimated_size_mb": self.estimated_size_mb,
            "requires_admin": self.requires_admin,
            "requires_restart": self.requires_restart,
        }


class InstallerEngine:
    """
    Orchestrates tool installations.

    Coordinates with the ToolRegistry for metadata, platform-specific
    installers for execution, and manages the installation lifecycle.
    """

    def __init__(
        self,
        tool_registry: Optional[ToolRegistry] = None,
        platform: Optional[PlatformBase] = None,
    ) -> None:
        self.tool_registry = tool_registry or ToolRegistry()
        self.platform = platform or PlatformFactory.create()
        self._results: Dict[str, InstallerResult] = {}

    def create_plan(self, tool_names: List[str]) -> InstallationPlan:
        """
        Create an installation plan for the specified tools.

        Args:
            tool_names: List of tool names to install

        Returns:
            InstallationPlan with dependency-ordered install sequence
        """
        # Resolve dependencies
        all_tools: Set[str] = set(tool_names)
        for name in tool_names:
            deps = self.tool_registry.get_dependencies(name, recursive=True)
            for dep in deps:
                if dep.required:
                    all_tools.add(dep.name)

        # Get install order
        install_order = self.tool_registry.get_install_order(list(all_tools))

        # Calculate requirements
        total_size = 0
        requires_admin = False
        for name in install_order:
            metadata = self.tool_registry.get(name)
            if metadata:
                total_size += metadata.min_disk_gb * 1024  # Convert to MB
                if metadata.requires_admin:
                    requires_admin = True

        return InstallationPlan(
            tools=list(all_tools),
            install_order=install_order,
            total_tools=len(install_order),
            estimated_size_mb=total_size,
            requires_admin=requires_admin,
        )

    async def install_tool(
        self, tool_name: str, version: Optional[str] = None
    ) -> InstallerResult:
        """
        Install a single tool.

        Args:
            tool_name: Name of the tool to install
            version: Optional specific version to install

        Returns:
            InstallerResult with installation outcome
        """
        metadata = self.tool_registry.get(tool_name)
        if not metadata:
            return InstallerResult(
                tool_name=tool_name,
                status=InstallerStatus.FAILED,
                error=f"Unknown tool: {tool_name}",
            )

        logger.info(
            "Installing tool",
            tool=tool_name,
            version=version or "latest",
        )

        start_time = datetime.now(timezone.utc)
        result = InstallerResult(tool_name=tool_name, status=InstallerStatus.PENDING)

        try:
            # Check if already installed
            if self._is_tool_installed(tool_name):
                result.status = InstallerStatus.ALREADY_INSTALLED
                result.version = self._get_tool_version(tool_name)
                logger.info("Tool already installed", tool=tool_name)
            else:
                result.status = InstallerStatus.INSTALLING
                install_result = await self._execute_installation(metadata, version)
                result.status = install_result["status"]
                result.version = install_result.get("version")
                result.install_path = install_result.get("install_path")
                result.error = install_result.get("error")

        except Exception as e:
            result.status = InstallerStatus.FAILED
            result.error = str(e)
            logger.error("Installation failed", tool=tool_name, error=str(e))

        result.duration_seconds = (datetime.now(timezone.utc) - start_time).total_seconds()
        self._results[tool_name] = result
        return result

    async def install_multiple(
        self, tool_names: List[str]
    ) -> Dict[str, InstallerResult]:
        """
        Install multiple tools in dependency order.

        Args:
            tool_names: List of tool names to install

        Returns:
            Dictionary mapping tool names to their installation results
        """
        plan = self.create_plan(tool_names)
        results: Dict[str, InstallerResult] = {}

        logger.info(
            "Starting batch installation",
            total=plan.total_tools,
            order=plan.install_order,
        )

        for tool_name in plan.install_order:
            result = await self.install_tool(tool_name)
            results[tool_name] = result

            # Stop on failure if the tool is a dependency for others
            if result.status == InstallerStatus.FAILED:
                metadata = self.tool_registry.get(tool_name)
                if metadata and any(
                    d.name == tool_name and d.required
                    for name in plan.install_order
                    for d in (self.tool_registry.get(name).dependencies if self.tool_registry.get(name) else [])
                ):
                    logger.warning(
                        "Dependency installation failed, stopping batch",
                        tool=tool_name,
                    )
                    break

        return results

    async def _execute_installation(
        self, metadata: ToolMetadata, version: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Execute the actual installation of a tool.

        This is a stub that will be replaced with actual installer
        implementations. Currently returns a simulated result.

        Args:
            metadata: Tool metadata
            version: Optional specific version

        Returns:
            Dictionary with installation result details
        """
        # TODO: Replace with actual installer implementations
        # This will dispatch to the appropriate installer class
        # based on metadata.installer_class

        logger.info(
            "Installation stub - would install",
            tool=metadata.name,
            installer=metadata.installer_class,
        )

        return {
            "status": InstallerStatus.FAILED,
            "error": (
                f"Installer for '{metadata.name}' not yet implemented. "
                f"Would download from {metadata.download_url}"
            ),
        }

    def _is_tool_installed(self, tool_name: str) -> bool:
        """Check if a tool is already installed."""
        import subprocess
        check_commands = {
            "git": ["git", "--version"],
            "python": ["python", "--version"],
            "nodejs": ["node", "--version"],
            "docker": ["docker", "--version"],
            "ollama": ["ollama", "--version"],
            "vs_code": ["code", "--version"],
            "windsurf": ["windsurf", "--version"],
        }

        cmd = check_commands.get(tool_name)
        if not cmd:
            return False

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
            return result.returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False

    def _get_tool_version(self, tool_name: str) -> Optional[str]:
        """Get the installed version of a tool."""
        import subprocess
        check_commands = {
            "git": ["git", "--version"],
            "python": ["python", "--version"],
            "nodejs": ["node", "--version"],
            "docker": ["docker", "--version"],
            "ollama": ["ollama", "--version"],
        }

        cmd = check_commands.get(tool_name)
        if not cmd:
            return None

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                return result.stdout.strip() or result.stderr.strip()
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass

        return None

    def get_results(self) -> Dict[str, InstallerResult]:
        """Get all installation results."""
        return dict(self._results)
