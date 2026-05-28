"""
Corax Orchestrator - Portable Deployment Support.

Enables Corax to run from USB drives, standalone executables,
and other portable environments without requiring system installation.

Key capabilities:
- Portable mode detection (runtime executable, USB, etc.)
- Self-contained dependency provisioning
- Relative path resolution for all data directories
- Installer caching for offline survivability
- Antivirus-aware startup sequence
- Runtime dependency validation for portable mode
- PATH self-registration
"""

from typing import Optional, Dict, Any, List, Tuple
from dataclasses import dataclass, field
from pathlib import Path
import os
import sys
import shutil
import subprocess
# CRITICAL: Import stdlib platform module BEFORE any src.platform imports.
# Must use explicit import to prevent PyInstaller shadowing by src.platform package.
import platform as _stdlib_platform
platform = _stdlib_platform  # Keep API compatibility

from src.core.logging import get_logger

logger = get_logger(__name__)


@dataclass
class PortableConfig:
    """Configuration for portable deployment mode."""
    portable_root: str = "."
    data_dir: str = "data"
    cache_dir: str = "data/cache"
    installer_cache: str = "data/installer_cache"
    config_dir: str = "config"
    log_dir: str = "data/logs"
    use_relative_paths: bool = True
    antivirus_delays_ms: int = 500
    verify_startup_sequence: bool = True


class PortableDeployment:
    """
    Portable deployment support for Corax.

    Handles:
    - Portable mode detection
    - Self-contained dependency provisioning
    - Relative path resolution
    - Installer caching (files downloaded once, reused)
    - Antivirus-aware startup delays and retries
    - Runtime dependency validation in portable mode
    - USB deployment readiness
    - Standalone executable survivability

    Usage:
        portable = PortableDeployment()
        if portable.is_portable:
            portable.setup_environment()
    """

    def __init__(self, config: Optional[PortableConfig] = None):
        self._config = config or PortableConfig()
        self._is_executable = self._detect_executable()
        self._is_usb = self._detect_usb()
        self._is_portable = self._is_executable or self._is_usb

    # ─── Detection ───────────────────────────────────────────────────

    @property
    def is_portable(self) -> bool:
        """Check if running in portable mode."""
        return self._is_portable

    @property
    def is_executable(self) -> bool:
        """Check if running as a PyInstaller executable."""
        return self._is_executable

    @property
    def is_usb(self) -> bool:
        """Check if running from a USB drive."""
        return self._is_usb

    @property
    def root_path(self) -> str:
        """Get the portable root path."""
        if self._is_executable:
            return os.path.dirname(sys.executable)
        return os.path.abspath(self._config.portable_root)

    def _detect_executable(self) -> bool:
        """Detect if running as a PyInstaller executable."""
        return getattr(sys, 'frozen', False)

    def _detect_usb(self) -> bool:
        """
        Detect if running from a USB drive.

        Checks if the root path is on a removable drive (Windows)
        or certain known mount points (Linux/macOS).
        """
        try:
            root = os.path.abspath(self._config.portable_root)
            if platform.system() == "Windows":
                drive = os.path.splitdrive(root)[0]
                if drive:
                    # Check if drive is removable
                    try:
                        import ctypes
                        drive_letter = drive.rstrip("\\")
                        drive_type = ctypes.windll.kernel32.GetDriveTypeW(drive_letter + "\\")
                        # DRIVE_REMOVABLE = 2
                        return drive_type == 2
                    except Exception:
                        pass
            elif platform.system() == "Linux":
                # Check if path contains /media/ or /mnt/
                root_lower = root.lower()
                if "/media/" in root_lower or "/mnt/" in root_lower:
                    return True
            # macOS: /Volumes/
            elif platform.system() == "Darwin":
                if "/volumes/" in root.lower():
                    return True
        except Exception:
            pass
        return False

    # ─── Environment Setup ───────────────────────────────────────────

    def setup_environment(self) -> bool:
        """
        Set up the portable environment.

        Creates required directories, adjusts paths, validates
        dependencies, and applies antivirus-aware settings.

        Returns:
            True if environment setup succeeded
        """
        logger.info(
            "Setting up portable environment",
            is_executable=self._is_executable,
            is_usb=self._is_usb,
            root=self.root_path,
        )

        try:
            # Create required directories
            self._create_data_directories()

            # Add self to PATH
            self._register_path()

            # Validate dependencies
            if self._config.verify_startup_sequence:
                if not self._validate_runtime_dependencies():
                    logger.warning("Runtime dependencies not fully validated")

            # Set up installer cache
            self._setup_installer_cache()

            logger.info("Portable environment setup complete")
            return True

        except Exception as e:
            logger.error("Portable environment setup failed", error=str(e))
            return False

    def _create_data_directories(self) -> None:
        """Create all required data directories."""
        root = self.root_path
        dirs = [
            os.path.join(root, self._config.data_dir),
            os.path.join(root, self._config.cache_dir),
            os.path.join(root, self._config.installer_cache),
            os.path.join(root, self._config.log_dir),
        ]

        for d in dirs:
            Path(d).mkdir(parents=True, exist_ok=True)
            logger.debug("Portable directory ensured", path=d)

    def _register_path(self) -> None:
        """Add the portable root to PATH for subprocess execution."""
        root = self.root_path

        # Add root to PATH
        root_paths = [
            root,
            os.path.join(root, "bin"),
            os.path.join(root, "Scripts"),
            os.path.join(root, "cmd"),
        ]

        existing_paths = os.environ.get("PATH", "").split(os.pathsep)
        for p in root_paths:
            if os.path.isdir(p) and p not in existing_paths:
                os.environ["PATH"] = p + os.pathsep + os.environ.get("PATH", "")
                logger.debug("Added to PATH", path=p)

    def _validate_runtime_dependencies(self) -> bool:
        """Validate that all runtime dependencies are available."""
        dependencies = ["python", "pip"]
        if platform.system() == "Windows":
            dependencies.extend(["powershell", "where"])
        else:
            dependencies.extend(["sh", "which"])

        all_ok = True
        for dep in dependencies:
            try:
                if platform.system() == "Windows":
                    result = subprocess.run(
                        ["where", dep], capture_output=True, timeout=5
                    )
                else:
                    result = subprocess.run(
                        ["which", dep], capture_output=True, timeout=5
                    )
                if result.returncode != 0:
                    logger.warning("Dependency not found in PATH", dep=dep)
                    all_ok = False
            except Exception:
                logger.warning("Could not check dependency", dep=dep)
                all_ok = False

        return all_ok

    def _setup_installer_cache(self) -> None:
        """Set up the installer cache directory."""
        cache_path = os.path.join(self.root_path, self._config.installer_cache)
        Path(cache_path).mkdir(parents=True, exist_ok=True)
        logger.debug("Installer cache ready", path=cache_path)

    # ─── Path Resolution ─────────────────────────────────────────────

    def resolve_path(self, relative_path: str) -> str:
        """
        Resolve a path relative to the portable root.

        Args:
            relative_path: Path relative to the portable root

        Returns:
            Absolute path
        """
        if self._is_portable and self._config.use_relative_paths:
            return os.path.join(self.root_path, relative_path)
        return os.path.abspath(relative_path)

    def get_cache_path(self, url: str) -> str:
        """
        Get the cache path for a download URL.

        Args:
            url: Download URL to cache

        Returns:
            Cache file path
        """
        import hashlib
        url_hash = hashlib.md5(url.encode()).hexdigest()
        filename = f"{url_hash}_{os.path.basename(url.split('?')[0])}"
        cache_path = os.path.join(self.root_path, self._config.installer_cache, filename)
        return cache_path

    def get_cached_installer(self, url: str) -> Optional[str]:
        """
        Check if an installer is already cached.

        Args:
            url: Download URL to check

        Returns:
            Cached file path, or None if not cached
        """
        cache_path = self.get_cache_path(url)
        if os.path.exists(cache_path):
            logger.debug("Found cached installer", path=cache_path)
            return cache_path
        return None

    def cache_installer(self, url: str, file_data: bytes) -> str:
        """
        Cache an installer file.

        Args:
            url: Original download URL
            file_data: File content

        Returns:
            Cached file path
        """
        cache_path = self.get_cache_path(url)
        try:
            with open(cache_path, "wb") as f:
                f.write(file_data)
            logger.info("Installer cached", path=cache_path)
        except Exception as e:
            logger.warning("Failed to cache installer", error=str(e))

        return cache_path

    # ─── Antivirus Awareness ─────────────────────────────────────────

    def antivirus_safe_execute(
        self,
        command: List[str],
        timeout: int = 60,
        retry_on_failure: bool = True,
    ) -> Tuple[int, str, str]:
        """
        Execute a command with antivirus-aware retry logic.

        Some antivirus software (Windows Defender, etc.) may flag or
        delay newly downloaded executables. This function adds:
        - Small delays before first execution
        - Retry on access-denied errors
        - Extended timeout for AV scanning

        Args:
            command: Command to execute
            timeout: Timeout in seconds
            retry_on_failure: Whether to retry on access errors

        Returns:
            (return_code, stdout, stderr)
        """
        import time as _time

        max_attempts = 3 if retry_on_failure else 1

        for attempt in range(max_attempts):
            try:
                # Small delay before first execution to let AV finish scanning
                if attempt > 0:
                    _time.sleep(self._config.antivirus_delays_ms / 1000.0 * attempt)

                result = subprocess.run(
                    command,
                    capture_output=True,
                    timeout=timeout + (attempt * 5),  # Extended timeout on retry
                    text=True,
                )

                # Check if access was denied (AV interference)
                if result.returncode != 0 and "access denied" in result.stderr.lower():
                    if attempt < max_attempts - 1:
                        logger.warning(
                            "AV interference detected, retrying",
                            command=command[0],
                            attempt=attempt + 1,
                        )
                        continue

                return result.returncode, result.stdout, result.stderr

            except subprocess.TimeoutExpired:
                if attempt < max_attempts - 1:
                    logger.warning(
                        "Command timed out, retrying",
                        command=command[0],
                        attempt=attempt + 1,
                    )
                    continue
                return -1, "", "Timeout"

            except Exception as e:
                if attempt < max_attempts - 1:
                    continue
                return -1, "", str(e)

        return -1, "", "All attempts failed"

    # ─── Deployment → Portable Mapping ───────────────────────────────

    def get_deployment_path(self, tool_name: str) -> str:
        """
        Get the deployment path for a tool in portable mode.

        Args:
            tool_name: Tool identifier

        Returns:
            Expected deployment path
        """
        root = self.root_path
        portable_tool_paths = {
            "ollama": os.path.join(root, "ollama"),
            "lm_studio": os.path.join(root, "LMStudio"),
            "open_webui": os.path.join(root, "open_webui"),
            "anythingllm": os.path.join(root, "anythingllm"),
            "comfyui": os.path.join(root, "comfyui"),
            "open_interpreter": os.path.join(root, "open_interpreter"),
            "git": os.path.join(root, "git"),
            "python": os.path.join(root, "python"),
            "node": os.path.join(root, "node"),
            "vscode": os.path.join(root, "vscode"),
            "windsurf": os.path.join(root, "windsurf"),
        }
        return portable_tool_paths.get(tool_name, os.path.join(root, tool_name))

    # ─── USB Readiness ───────────────────────────────────────────────

    def prepare_usb_environment(self, usb_path: str) -> bool:
        """
        Prepare the environment for USB deployment.

        Args:
            usb_path: Root path of the USB drive

        Returns:
            True if preparation succeeded
        """
        logger.info("Preparing USB environment", path=usb_path)

        try:
            # Create directory structure
            self._config.portable_root = usb_path
            self._create_data_directories()
            self._setup_installer_cache()

            # Create USB startup script
            self._create_usb_startup_script(usb_path)

            logger.info("USB environment prepared successfully")
            return True

        except Exception as e:
            logger.error("USB environment preparation failed", error=str(e))
            return False

    def _create_usb_startup_script(self, usb_path: str) -> None:
        """Create a startup script for USB deployment."""
        if platform.system() == "Windows":
            script_path = os.path.join(usb_path, "run_corax.bat")
            script_content = (
                "@echo off\n"
                "title Corax Orchestrator (Portable)\n"
                "echo Starting Corax Orchestrator in portable mode...\n"
                "echo.\n"
                f'cd /d "%~dp0"\n'
                "echo Setting up portable environment...\n"
                "echo.\n"
                'start "" "%~dp0CoraxOrchestrator.exe" --portable\n'
                "echo.\n"
                "echo Corax started. Close this window to stop.\n"
            )
            try:
                with open(script_path, "w", encoding="utf-8") as f:
                    f.write(script_content)
                logger.info("USB startup script created", path=script_path)
            except Exception as e:
                logger.warning("Failed to create USB startup script", error=str(e))

    def get_environment_report(self) -> Dict[str, Any]:
        """Get a detailed report of the portable environment."""
        return {
            "is_portable": self._is_portable,
            "is_executable": self._is_executable,
            "is_usb": self._is_usb,
            "root_path": self.root_path,
            "os": platform.system(),
            "os_version": platform.version(),
            "python_version": sys.version,
            "executable_path": sys.executable if not self._is_executable else "frozen",
            "frozen": self._is_executable,
            "argv": sys.argv,
            "data_dirs_exist": {
                "data": os.path.isdir(os.path.join(self.root_path, "data")),
                "cache": os.path.isdir(os.path.join(self.root_path, "data/cache")),
                "installer_cache": os.path.isdir(
                    os.path.join(self.root_path, "data/installer_cache")
                ),
                "logs": os.path.isdir(os.path.join(self.root_path, "data/logs")),
            },
            "path_contains_root": self.root_path in os.environ.get("PATH", ""),
        }
