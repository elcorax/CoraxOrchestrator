"""
Corax Orchestrator - System Scanner Module.

Scans the system for hardware specifications, installed software,
and environmental characteristics to determine deployment requirements.
"""

from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

from src.core.logging import get_logger
from src.core.exceptions import DetectionError
from src.platform.factory import PlatformFactory
from src.platform.base import PlatformBase, PlatformInfo

logger = get_logger(__name__)


@dataclass
class HardwareSpecs:
    """Container for detected hardware specifications."""
    cpu: Dict[str, Any] = field(default_factory=dict)
    memory: Dict[str, Any] = field(default_factory=dict)
    disks: List[Dict[str, Any]] = field(default_factory=list)
    gpus: List[Dict[str, Any]] = field(default_factory=list)
    network: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SoftwareInventory:
    """Container for detected software inventory."""
    operating_system: Dict[str, Any] = field(default_factory=dict)
    installed_applications: List[Dict[str, str]] = field(default_factory=list)
    development_tools: Dict[str, Optional[str]] = field(default_factory=dict)
    package_managers: List[str] = field(default_factory=list)
    runtimes: Dict[str, Optional[str]] = field(default_factory=dict)


@dataclass
class ScanResult:
    """Complete system scan result."""
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    platform: Optional[PlatformInfo] = None
    hardware: HardwareSpecs = field(default_factory=HardwareSpecs)
    software: SoftwareInventory = field(default_factory=SoftwareInventory)
    errors: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize scan result to dictionary."""
        return {
            "timestamp": self.timestamp,
            "platform": self.platform.to_dict() if self.platform else {},
            "hardware": asdict(self.hardware),
            "software": asdict(self.software),
            "errors": self.errors,
        }


class SystemScanner:
    """
    Scans the system for hardware and software information.

    Provides comprehensive system introspection capabilities for
    determining deployment requirements and compatibility.
    """

    def __init__(self, platform: Optional[PlatformBase] = None) -> None:
        self.platform = platform or PlatformFactory.create()
        self._result: Optional[ScanResult] = None

    async def scan(self) -> ScanResult:
        """
        Perform a complete system scan.

        Returns:
            ScanResult containing all detected system information
        """
        logger.info("Starting system scan")

        result = ScanResult()

        try:
            result.platform = self.platform.platform_info
        except Exception as e:
            error = f"Platform detection failed: {e}"
            logger.error(error)
            result.errors.append(error)

        # Scan hardware
        result.hardware = await self._scan_hardware(result)

        # Scan software
        result.software = await self._scan_software(result)

        self._result = result
        logger.info(
            "System scan completed",
            cpu_cores=result.hardware.cpu.get("cores"),
            memory_gb=result.hardware.memory.get("total_gb"),
            gpu_count=len(result.hardware.gpus),
            errors=len(result.errors),
        )
        return result

    async def _scan_hardware(self, result: ScanResult) -> HardwareSpecs:
        """Scan hardware specifications."""
        hardware = HardwareSpecs()

        try:
            hardware.cpu = self.platform.get_cpu_info()
        except Exception as e:
            result.errors.append(f"CPU detection failed: {e}")

        try:
            hardware.memory = self.platform.get_memory_info()
        except Exception as e:
            result.errors.append(f"Memory detection failed: {e}")

        try:
            hardware.disks = self.platform.get_disk_info()
        except Exception as e:
            result.errors.append(f"Disk detection failed: {e}")

        try:
            hardware.gpus = self.platform.get_gpu_info()
        except Exception as e:
            result.errors.append(f"GPU detection failed: {e}")

        try:
            hardware.network = self.platform.get_network_info()
        except Exception as e:
            result.errors.append(f"Network detection failed: {e}")

        return hardware

    async def _scan_software(self, result: ScanResult) -> SoftwareInventory:
        """Scan software inventory."""
        software = SoftwareInventory()

        # OS info
        if result.platform:
            software.operating_system = {
                "platform": result.platform.platform_type.value,
                "version": result.platform.os_version,
                "architecture": result.platform.architecture.value,
                "hostname": result.platform.hostname,
            }

        # Installed applications
        try:
            software.installed_applications = self.platform.get_installed_software()
        except Exception as e:
            result.errors.append(f"Software detection failed: {e}")

        # Package managers
        try:
            pm = self.platform.get_package_manager()
            if pm:
                software.package_managers = [pm]
        except Exception as e:
            result.errors.append(f"Package manager detection failed: {e}")

        # Development tools
        software.development_tools = await self._detect_dev_tools()

        # Runtimes
        software.runtimes = await self._detect_runtimes()

        return software

    async def _detect_dev_tools(self) -> Dict[str, Optional[str]]:
        """Detect installed development tools asynchronously."""
        tools = {}
        tool_checks = {
            "git": ["git", "--version"],
            "docker": ["docker", "--version"],
            "code": ["code", "--version"],
            "node": ["node", "--version"],
            "npm": ["npm", "--version"],
            "python": ["python", "--version"],
            "pip": ["pip", "--version"],
            "ollama": ["ollama", "--version"],
            "windsurf": ["windsurf", "--version"],
        }

        import asyncio
        loop = asyncio.get_event_loop()

        async def _check_tool(cmd: List[str]) -> Optional[str]:
            try:
                proc = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                try:
                    stdout, _ = await asyncio.wait_for(
                        proc.communicate(), timeout=5
                    )
                    if proc.returncode == 0:
                        return stdout.decode().strip()
                except asyncio.TimeoutError:
                    proc.kill()
                    await proc.wait()
                return None
            except (FileNotFoundError, OSError):
                return None

        for tool_name, cmd in tool_checks.items():
            tools[tool_name] = await _check_tool(cmd)

        return tools

    async def _detect_runtimes(self) -> Dict[str, Optional[str]]:
        """Detect installed language runtimes asynchronously."""
        import asyncio
        runtimes = {}
        runtime_checks = {
            "python": ["python", "--version"],
            "python3": ["python3", "--version"],
            "node": ["node", "--version"],
            "nodejs": ["nodejs", "--version"],
            "dotnet": ["dotnet", "--version"],
            "java": ["java", "-version"],
            "go": ["go", "version"],
            "rustc": ["rustc", "--version"],
        }

        async def _check_runtime(cmd: List[str]) -> Optional[str]:
            try:
                proc = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                try:
                    stdout, stderr = await asyncio.wait_for(
                        proc.communicate(), timeout=5
                    )
                    if proc.returncode == 0:
                        return (stdout.decode().strip() or stderr.decode().strip())
                except asyncio.TimeoutError:
                    proc.kill()
                    await proc.wait()
                return None
            except (FileNotFoundError, OSError):
                return None

        for runtime_name, cmd in runtime_checks.items():
            runtimes[runtime_name] = await _check_runtime(cmd)

        return runtimes

    def get_last_result(self) -> Optional[ScanResult]:
        """Get the last scan result."""
        return self._result
