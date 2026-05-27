"""
Corax Orchestrator - Developer Installer Base Class.

Extends AIInstallerBase with developer tool-specific capabilities:
- Version detection via CLI
- Silent installation with platform-specific flags
- PATH and environment variable management
- Installation verification via CLI commands
- Repair/reinstall flows
- Uninstall detection
- Download management
- Async execution with operation tracking
"""

from typing import Dict, Any, List, Optional, Tuple
from abc import abstractmethod
import asyncio
import os
import re
import shutil
import tempfile
from pathlib import Path

from src.deployment.installers.base import AIInstallerBase, InstallResult, InstallStatus
from src.deployment.windows_utils import WindowsUtils
from src.deployment.macos_utils import MacOSUtils
from src.deployment.operations import OperationTracker, OperationType, OperationStatus, FailureCategory
from src.core.logging import get_logger

logger = get_logger(__name__)


class DevInstallerBase(AIInstallerBase):
    """
    Extended base class for developer tool installers.

    Adds developer-specific capabilities on top of AIInstallerBase:
    - Version detection via --version flags
    - Silent installation with platform detection
    - PATH management
    - Environment variable management
    - CLI-based verification
    - Repair/reinstall flows
    - Operation tracking integration
    """

    def __init__(self, operation_tracker: Optional[OperationTracker] = None) -> None:
        super().__init__()
        self._win_utils = WindowsUtils() if self._is_windows else None
        self._mac_utils = MacOSUtils() if self._is_macos else None
        self._op_tracker = operation_tracker or OperationTracker()

    @property
    @abstractmethod
    def install_dir(self) -> Optional[str]:
        """Default installation directory, if applicable."""
        ...

    @property
    @abstractmethod
    def winget_id(self) -> Optional[str]:
        """Winget package ID for Windows installation."""
        ...

    @property
    @abstractmethod
    def brew_package(self) -> Optional[str]:
        """Homebrew package name for macOS installation."""
        ...

    @property
    @abstractmethod
    def brew_cask(self) -> bool:
        """Whether this is a Homebrew cask (GUI app)."""
        ...

    @property
    @abstractmethod
    def download_url_windows(self) -> Optional[str]:
        """Download URL for Windows installer."""
        ...

    @property
    @abstractmethod
    def download_url_macos(self) -> Optional[str]:
        """Download URL for macOS installer."""
        ...

    @property
    @abstractmethod
    def silent_flags_windows(self) -> List[str]:
        """Silent installation flags for Windows installer."""
        ...

    @property
    @abstractmethod
    def verify_command(self) -> Optional[List[str]]:
        """CLI command to verify installation (e.g., ['git', '--version'])."""
        ...

    @property
    @abstractmethod
    def version_arguments(self) -> List[str]:
        """Arguments to get version string (e.g., ['--version'])."""
        ...

    @property
    def path_entries(self) -> List[str]:
        """Directories to add to PATH after installation."""
        return []

    @property
    def env_vars(self) -> Dict[str, str]:
        """Environment variables to set after installation."""
        return {}

    @property
    def min_version(self) -> Optional[str]:
        """Minimum required version (e.g., '2.30.0'). None if no minimum."""
        return None

    # --- Version Detection ---

    async def get_installed_version(self) -> Optional[str]:
        """
        Detect the installed version via CLI.

        Returns:
            Version string or None if not installed
        """
        if not self.verify_command:
            return None

        exit_code, stdout, stderr = await self._run_command(
            self.verify_command + self.version_arguments,
            timeout=30,
        )

        if exit_code != 0:
            return None

        # Parse version from output
        output = stdout.strip() or stderr.strip()
        return self._parse_version(output)

    def _parse_version(self, output: str) -> Optional[str]:
        """
        Parse version string from CLI output.

        Override in subclasses for custom parsing.
        """
        # Default: look for semantic version pattern
        match = re.search(r'(\d+\.\d+\.\d+)', output)
        if match:
            return match.group(1)
        # Fallback: look for major.minor
        match = re.search(r'(\d+\.\d+)', output)
        if match:
            return match.group(1)
        return output[:50] if output else None

    def _compare_versions(self, version1: str, version2: str) -> int:
        """
        Compare two version strings.

        Returns:
            -1 if v1 < v2, 0 if equal, 1 if v1 > v2
        """
        def parse(v: str) -> List[int]:
            parts = []
            for p in v.split("."):
                try:
                    parts.append(int(p))
                except ValueError:
                    parts.append(0)
            return parts

        v1_parts = parse(version1)
        v2_parts = parse(version2)

        for i in range(max(len(v1_parts), len(v2_parts))):
            p1 = v1_parts[i] if i < len(v1_parts) else 0
            p2 = v2_parts[i] if i < len(v2_parts) else 0
            if p1 < p2:
                return -1
            elif p1 > p2:
                return 1
        return 0

    # --- Detection ---

    async def detect(self) -> InstallResult:
        """Detect if the tool is installed and get version."""
        op_id = self._op_tracker.start_operation(
            OperationType.VALIDATION,
            f"Detect {self.tool_name}",
            tool_key=self.tool_key,
        )

        try:
            # Check via CLI
            version = await self.get_installed_version()

            if version:
                # Check minimum version
                if self.min_version and self._compare_versions(version, self.min_version) < 0:
                    self._op_tracker.finish_operation(
                        op_id, OperationStatus.SUCCEEDED,
                        result_data={"version": version, "outdated": True},
                    )
                    return InstallResult(
                        tool_name=self.tool_name,
                        status=InstallStatus.OUTDATED,
                        version=version,
                        details={"minimum_version": self.min_version},
                    )

                # Find install path
                install_path = None
                if self.verify_command:
                    install_path = shutil.which(self.verify_command[0])

                self._op_tracker.finish_operation(
                    op_id, OperationStatus.SUCCEEDED,
                    result_data={"version": version, "path": install_path},
                )
                return InstallResult(
                    tool_name=self.tool_name,
                    status=InstallStatus.INSTALLED,
                    version=version,
                    install_path=install_path,
                )

            # Check via winget (Windows)
            if self._is_windows and self._win_utils and self.winget_id:
                if await self._win_utils.winget_list(self.winget_id):
                    self._op_tracker.finish_operation(
                        op_id, OperationStatus.SUCCEEDED,
                        result_data={"detected_via": "winget"},
                    )
                    return InstallResult(
                        tool_name=self.tool_name,
                        status=InstallStatus.INSTALLED,
                        details={"detected_via": "winget"},
                    )

            # Check via brew (macOS)
            if self._is_macos and self._mac_utils and self.brew_package:
                if await self._mac_utils.brew_list(self.brew_package):
                    self._op_tracker.finish_operation(
                        op_id, OperationStatus.SUCCEEDED,
                        result_data={"detected_via": "brew"},
                    )
                    return InstallResult(
                        tool_name=self.tool_name,
                        status=InstallStatus.INSTALLED,
                        details={"detected_via": "brew"},
                    )

            self._op_tracker.finish_operation(
                op_id, OperationStatus.SUCCEEDED,
                result_data={"installed": False},
            )
            return InstallResult(
                tool_name=self.tool_name,
                status=InstallStatus.NOT_INSTALLED,
            )

        except Exception as e:
            self._op_tracker.fail_operation(
                op_id, str(e), FailureCategory.UNKNOWN,
            )
            return InstallResult(
                tool_name=self.tool_name,
                status=InstallStatus.FAILED,
                error=str(e),
            )

    # --- Installation ---

    async def install(self, config: Optional[Dict[str, Any]] = None) -> InstallResult:
        """Install the developer tool."""
        op_id = self._op_tracker.start_operation(
            OperationType.INSTALLER,
            f"Install {self.tool_name}",
            tool_key=self.tool_key,
        )

        try:
            # Check if already installed
            detect_result = await self.detect()
            if detect_result.status == InstallStatus.INSTALLED:
                self._op_tracker.finish_operation(
                    op_id, OperationStatus.SKIPPED,
                    result_data={"version": detect_result.version, "reason": "already_installed"},
                )
                return detect_result

            # Platform-specific installation
            if self._is_windows:
                success, message = await self._install_windows(config)
            elif self._is_macos:
                success, message = await self._install_macos(config)
            else:
                success, message = await self._install_linux(config)

            if not success:
                self._op_tracker.fail_operation(
                    op_id, message, FailureCategory.UNKNOWN,
                )
                return InstallResult(
                    tool_name=self.tool_name,
                    status=InstallStatus.FAILED,
                    error=message,
                )

            # Update PATH
            if self.path_entries:
                for entry in self.path_entries:
                    if self._is_windows and self._win_utils:
                        await self._win_utils.add_to_user_path(entry)

            # Set environment variables
            if self.env_vars:
                for name, value in self.env_vars.items():
                    if self._is_windows and self._win_utils:
                        await self._win_utils.set_user_env_var(name, value)

            # Verify installation
            verify_result = await self.verify()
            if verify_result.status == InstallStatus.INSTALLED:
                self._op_tracker.finish_operation(
                    op_id, OperationStatus.SUCCEEDED,
                    result_data={"version": verify_result.version, "path": verify_result.install_path},
                )
            else:
                self._op_tracker.finish_operation(
                    op_id, OperationStatus.SUCCEEDED,
                    result_data={"warning": "Install completed but verification failed"},
                )

            return verify_result

        except Exception as e:
            self._op_tracker.fail_operation(
                op_id, str(e), FailureCategory.UNKNOWN,
            )
            return InstallResult(
                tool_name=self.tool_name,
                status=InstallStatus.FAILED,
                error=str(e),
            )

    async def _install_windows(self, config: Optional[Dict[str, Any]] = None) -> Tuple[bool, str]:
        """Windows-specific installation with fallback strategies."""
        if not self._win_utils:
            return (False, "Windows utilities not available")

        # Strategy 1: winget
        if self.winget_id:
            logger.info(f"Installing {self.tool_name} via winget", winget_id=self.winget_id)
            exit_code, stdout, stderr = await self._win_utils.winget_install(
                self.winget_id, timeout=600
            )
            if exit_code == 0:
                return (True, f"Installed via winget ({self.winget_id})")
            # Check if already installed
            if await self._win_utils.winget_list(self.winget_id):
                return (True, f"Already installed (winget: {self.winget_id})")
            logger.warning(f"winget install failed", exit_code=exit_code, stderr=stderr[:200])

        # Strategy 2: Direct download + execute
        if self.download_url_windows:
            logger.info(f"Installing {self.tool_name} via direct download")
            try:
                dl_path = os.path.join(
                    tempfile.gettempdir(),
                    f"corax_{self.tool_key}_{Path(self.download_url_windows).name}",
                )

                # Download
                dl_cmd = [
                    "powershell.exe", "-NoProfile", "-Command",
                    f"Invoke-WebRequest -Uri '{self.download_url_windows}' -OutFile '{dl_path}' -UseBasicParsing",
                ]
                dl_exit, dl_out, dl_err = await self._run_command(dl_cmd, timeout=600)
                if dl_exit != 0:
                    return (False, f"Download failed: {dl_err[:200]}")

                # Execute installer
                exit_code, stdout, stderr = await self._win_utils.run_installer(
                    dl_path, silent_args=self.silent_flags_windows, timeout=600
                )

                if exit_code == 0:
                    return (True, "Installed via direct installer")

                # Check if actually installed despite exit code
                version = await self.get_installed_version()
                if version:
                    return (True, f"Installer reported {exit_code} but tool is functional (v{version})")

                return (False, f"Installer failed with exit code {exit_code}")

            except Exception as e:
                return (False, f"Direct install failed: {str(e)}")

        return (False, "No Windows install method available")

    async def _install_macos(self, config: Optional[Dict[str, Any]] = None) -> Tuple[bool, str]:
        """macOS-specific installation."""
        if not self._mac_utils:
            return (False, "macOS utilities not available")

        # Strategy 1: Homebrew
        if self.brew_package:
            logger.info(f"Installing {self.tool_name} via Homebrew")
            if self.brew_cask:
                exit_code, stdout, stderr = await self._mac_utils.brew_cask_install(
                    self.brew_package, timeout=600
                )
            else:
                exit_code, stdout, stderr = await self._mac_utils.brew_install(
                    self.brew_package, timeout=600
                )
            if exit_code == 0:
                return (True, f"Installed via Homebrew ({self.brew_package})")
            logger.warning(f"Homebrew install failed", exit_code=exit_code, stderr=stderr[:200])

        # Strategy 2: DMG/PKG download
        if self.download_url_macos:
            logger.info(f"Installing {self.tool_name} via DMG/PKG download")
            try:
                dl_path = os.path.join(
                    tempfile.gettempdir(),
                    f"corax_{self.tool_key}_{Path(self.download_url_macos).name}",
                )

                # Download
                dl_exit, dl_out, dl_err = await self._run_command(
                    ["curl", "-fsSL", "-o", dl_path, self.download_url_macos],
                    timeout=600,
                )
                if dl_exit != 0:
                    return (False, f"Download failed: {dl_err[:200]}")

                # Install based on extension
                ext = Path(dl_path).suffix.lower()
                if ext == ".dmg":
                    exit_code, stdout, stderr = await self._mac_utils.install_dmg(
                        dl_path, f"{self.tool_name}.app", timeout=120
                    )
                elif ext == ".pkg":
                    exit_code, stdout, stderr = await self._mac_utils.install_pkg(
                        dl_path, timeout=120
                    )
                else:
                    return (False, f"Unknown installer type: {ext}")

                if exit_code == 0:
                    return (True, "Installed via DMG/PKG")

                return (False, f"Installer failed with exit code {exit_code}")

            except Exception as e:
                return (False, f"macOS install failed: {str(e)}")

        return (False, "No macOS install method available")

    async def _install_linux(self, config: Optional[Dict[str, Any]] = None) -> Tuple[bool, str]:
        """Linux-specific installation (stub for future)."""
        return (False, "Linux installation not yet implemented")

    # --- Verification ---

    async def verify(self) -> InstallResult:
        """Verify installation by running the tool's CLI."""
        op_id = self._op_tracker.start_validation(
            f"Verify {self.tool_name}",
            tool_key=self.tool_key,
        )

        try:
            version = await self.get_installed_version()

            if version:
                install_path = None
                if self.verify_command:
                    install_path = shutil.which(self.verify_command[0])

                self._op_tracker.finish_operation(
                    op_id, OperationStatus.SUCCEEDED,
                    result_data={"version": version, "path": install_path},
                )
                return InstallResult(
                    tool_name=self.tool_name,
                    status=InstallStatus.INSTALLED,
                    version=version,
                    install_path=install_path,
                )

            self._op_tracker.finish_operation(
                op_id, OperationStatus.FAILED,
                result_data={"error": "Version detection failed"},
            )
            return InstallResult(
                tool_name=self.tool_name,
                status=InstallStatus.FAILED,
                error="Version detection failed after installation",
            )

        except Exception as e:
            self._op_tracker.fail_operation(
                op_id, str(e), FailureCategory.UNKNOWN,
            )
            return InstallResult(
                tool_name=self.tool_name,
                status=InstallStatus.FAILED,
                error=str(e),
            )

    # --- Repair ---

    async def repair(self) -> InstallResult:
        """Attempt to repair a broken installation."""
        op_id = self._op_tracker.start_recovery(
            f"Repair {self.tool_name}",
            tool_key=self.tool_key,
        )

        logger.info(f"Attempting repair for {self.tool_name}")

        try:
            # Check PATH issues
            if self._is_windows and self._win_utils:
                path_fixes = await self._win_utils.repair_path()
                if path_fixes:
                    logger.info(f"PATH repaired for {self.tool_name}", fixes=path_fixes)

            # Reinstall
            result = await self.install()

            if result.status == InstallStatus.INSTALLED:
                self._op_tracker.finish_operation(
                    op_id, OperationStatus.SUCCEEDED,
                    result_data={"version": result.version},
                )
            else:
                self._op_tracker.fail_operation(
                    op_id, result.error or "Repair failed", FailureCategory.UNKNOWN,
                )

            return result

        except Exception as e:
            self._op_tracker.fail_operation(
                op_id, str(e), FailureCategory.UNKNOWN,
            )
            return InstallResult(
                tool_name=self.tool_name,
                status=InstallStatus.FAILED,
                error=str(e),
            )

    # --- Uninstall Detection ---

    async def get_uninstall_info(self) -> Optional[Dict[str, Any]]:
        """Get uninstall information for the tool."""
        if self._is_windows and self._win_utils:
            uninstall_str = self._win_utils.get_registry_uninstall_string(self.tool_name)
            if uninstall_str:
                return {"uninstall_string": uninstall_str}

        return None

    # --- Utility ---

    def get_operation_tracker(self) -> OperationTracker:
        """Get the operation tracker instance."""
        return self._op_tracker
