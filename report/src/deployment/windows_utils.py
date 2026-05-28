"""
Corax Orchestrator - Windows Execution Utilities.

Provides Windows-specific execution capabilities including:
- winget package management
- Direct installer execution with silent flags
- Fallback installer strategies
- PATH management (read, append, verify)
- Environment variable management (user/system scope)
- Admin elevation detection and requests
- Registry operations for installed software detection
"""

from typing import Dict, Any, List, Optional, Tuple
import asyncio
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from src.core.logging import get_logger
from src.core.exceptions import InstallationError, PermissionError

logger = get_logger(__name__)


class WindowsUtils:
    """
    Windows-specific execution utilities for deployment.

    Provides winget integration, installer execution, PATH/env
    management, and admin elevation support.
    """

    def __init__(self) -> None:
        self._winget_available: Optional[bool] = None

    # --- Winget Integration ---

    async def check_winget(self) -> bool:
        """Check if winget is available on the system."""
        if self._winget_available is not None:
            return self._winget_available

        proc = None
        try:
            proc = await asyncio.create_subprocess_exec(
                "winget", "--version",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=10)
            self._winget_available = proc.returncode == 0
            if self._winget_available:
                logger.info("winget available", version=stdout.decode().strip())
            return self._winget_available
        except Exception:
            self._winget_available = False
            return False
        finally:
            if proc:
                if proc.returncode is None:
                    try:
                        proc.kill()
                    except Exception:
                        pass
                if proc.stdout:
                    try:
                        proc.stdout.close()
                    except Exception:
                        pass
                if proc.stderr:
                    try:
                        proc.stderr.close()
                    except Exception:
                        pass
                try:
                    await proc.wait()
                except Exception:
                    pass

    async def winget_install(
        self,
        package_id: str,
        source: Optional[str] = None,
        accept_source_agreements: bool = True,
        timeout: int = 300,
    ) -> Tuple[int, str, str]:
        """
        Install a package using winget.

        Args:
            package_id: Winget package ID (e.g., "Git.Git")
            source: Optional source (e.g., "winget")
            accept_source_agreements: Auto-accept source agreements
            timeout: Timeout in seconds

        Returns:
            Tuple of (exit_code, stdout, stderr)
        """
        cmd = ["winget", "install", "--id", package_id, "--silent", "--accept-package-agreements"]
        if accept_source_agreements:
            cmd.append("--accept-source-agreements")
        if source:
            cmd.extend(["--source", source])

        logger.info("Installing via winget", package=package_id)
        return await self._run_command(cmd, timeout=timeout)

    async def winget_upgrade(
        self,
        package_id: str,
        timeout: int = 300,
    ) -> Tuple[int, str, str]:
        """Upgrade a package using winget."""
        cmd = [
            "winget", "upgrade", "--id", package_id,
            "--silent", "--accept-package-agreements", "--accept-source-agreements",
        ]
        return await self._run_command(cmd, timeout=timeout)

    async def winget_list(self, package_id: str) -> bool:
        """Check if a package is installed via winget."""
        cmd = ["winget", "list", "--id", package_id, "--accept-source-agreements"]
        exit_code, stdout, _ = await self._run_command(cmd, timeout=30)
        # winget returns 0 if found, non-zero if not found
        return exit_code == 0 and package_id.lower() in stdout.lower()

    # --- Direct Installer Execution ---

    async def run_installer(
        self,
        installer_path: str,
        silent_args: Optional[List[str]] = None,
        timeout: int = 600,
        cwd: Optional[str] = None,
        wait_for_exit: bool = True,
    ) -> Tuple[int, str, str]:
        """
        Run an installer executable with silent flags.

        Args:
            installer_path: Path to the installer
            silent_args: Additional silent installation arguments
            timeout: Timeout in seconds
            cwd: Working directory
            wait_for_exit: Whether to wait for the process to exit

        Returns:
            Tuple of (exit_code, stdout, stderr)
        """
        if not os.path.exists(installer_path):
            return (-1, "", f"Installer not found: {installer_path}")

        # Determine silent flags based on installer type
        ext = Path(installer_path).suffix.lower()
        if silent_args is None:
            if ext == ".msi":
                silent_args = ["/quiet", "/norestart"]
            elif ext == ".exe":
                # Common silent flags: /S, /silent, /verysilent
                silent_args = ["/S"]
            else:
                silent_args = []

        cmd = [installer_path] + silent_args
        logger.info("Running installer", path=installer_path, args=silent_args)

        if wait_for_exit:
            return await self._run_command(cmd, timeout=timeout, cwd=cwd)
        else:
            # Fire and forget
            try:
                proc = await asyncio.create_subprocess_exec(
                    *cmd, cwd=cwd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                # Don't wait - let it run in background
                return (0, f"Started PID {proc.pid}", "")
            except Exception as e:
                return (-1, "", str(e))

    async def run_msi_installer(
        self,
        msi_path: str,
        additional_args: Optional[List[str]] = None,
        timeout: int = 600,
    ) -> Tuple[int, str, str]:
        """Run an MSI installer with msiexec."""
        args = ["msiexec", "/i", msi_path, "/quiet", "/norestart"]
        if additional_args:
            args.extend(additional_args)
        return await self._run_command(args, timeout=timeout)

    # --- Fallback Installer Strategy ---

    async def install_with_fallback(
        self,
        tool_name: str,
        winget_id: Optional[str] = None,
        installer_url: Optional[str] = None,
        installer_args: Optional[List[str]] = None,
        download_path: Optional[str] = None,
        verify_command: Optional[List[str]] = None,
        timeout: int = 600,
    ) -> Tuple[bool, str]:
        """
        Install a tool with automatic fallback strategies.

        Strategy order:
        1. winget (if available)
        2. Direct installer download + execution
        3. Manual instructions

        Args:
            tool_name: Human-readable tool name
            winget_id: Winget package ID
            installer_url: URL to download installer
            installer_args: Silent installation arguments
            download_path: Where to save the download
            verify_command: Command to verify installation
            timeout: Timeout in seconds

        Returns:
            Tuple of (success, message)
        """
        # Strategy 1: winget
        if winget_id and await self.check_winget():
            logger.info(f"Attempting winget install for {tool_name}", winget_id=winget_id)
            exit_code, stdout, stderr = await self.winget_install(winget_id, timeout=timeout)
            if exit_code == 0:
                logger.info(f"winget install succeeded for {tool_name}")
                return (True, f"Installed via winget ({winget_id})")

            # winget may return 0 even if already installed
            if await self.winget_list(winget_id):
                logger.info(f"{tool_name} already installed via winget")
                return (True, f"Already installed (winget: {winget_id})")

            logger.warning(f"winget install failed for {tool_name}", exit_code=exit_code, stderr=stderr)

        # Strategy 2: Direct download + execute
        if installer_url:
            logger.info(f"Attempting direct install for {tool_name}")
            try:
                dl_path = download_path or os.path.join(
                    tempfile.gettempdir(), f"corax_{tool_name}_{Path(installer_url).name}"
                )

                # Download
                from src.deployment.installers.base import AIInstallerBase
                # Use PowerShell for download
                dl_cmd = [
                    "powershell.exe", "-NoProfile", "-Command",
                    f"Invoke-WebRequest -Uri '{installer_url}' -OutFile '{dl_path}' -UseBasicParsing",
                ]
                dl_exit, dl_out, dl_err = await self._run_command(dl_cmd, timeout=timeout)
                if dl_exit != 0:
                    return (False, f"Download failed: {dl_err}")

                # Execute installer
                exit_code, stdout, stderr = await self.run_installer(
                    dl_path, silent_args=installer_args, timeout=timeout
                )

                if exit_code == 0:
                    logger.info(f"Direct install succeeded for {tool_name}")
                    return (True, f"Installed via direct installer")

                # Check if it actually installed despite exit code
                if verify_command:
                    v_exit, v_out, v_err = await self._run_command(verify_command, timeout=30)
                    if v_exit == 0:
                        return (True, f"Installer reported {exit_code} but tool is functional")

                return (False, f"Installer failed with exit code {exit_code}: {stderr[:200]}")

            except Exception as e:
                return (False, f"Direct install failed: {str(e)}")

        # Strategy 3: Manual instructions
        return (False, f"No automated install method available for {tool_name}")

    # --- PATH Management ---

    def get_user_path(self) -> List[str]:
        """Get the current user PATH entries."""
        import winreg
        try:
            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Environment",
                0,
                winreg.KEY_READ,
            ) as key:
                path_value, _ = winreg.QueryValueEx(key, "PATH")
                return [p.strip() for p in path_value.split(";") if p.strip()]
        except Exception:
            return os.environ.get("PATH", "").split(";")

    def get_system_path(self) -> List[str]:
        """Get the system PATH entries."""
        import winreg
        try:
            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment",
                0,
                winreg.KEY_READ,
            ) as key:
                path_value, _ = winreg.QueryValueEx(key, "PATH")
                return [p.strip() for p in path_value.split(";") if p.strip()]
        except Exception:
            return []

    def path_contains(self, directory: str) -> bool:
        """Check if a directory is in the user PATH."""
        user_path = self.get_user_path()
        normalized = os.path.normpath(directory).lower()
        return any(os.path.normpath(p).lower() == normalized for p in user_path)

    async def add_to_user_path(self, directory: str) -> bool:
        """
        Add a directory to the user PATH.

        Args:
            directory: Directory to add

        Returns:
            True if added or already present
        """
        if self.path_contains(directory):
            logger.debug("Directory already in PATH", directory=directory)
            return True

        import winreg
        try:
            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Environment",
                0,
                winreg.KEY_SET_VALUE,
            ) as key:
                current_path, _ = winreg.QueryValueEx(key, "PATH")
                new_path = f"{current_path};{directory}" if current_path else directory
                winreg.SetValueEx(key, "PATH", 0, winreg.REG_EXPAND_SZ, new_path)

            # Broadcast environment change
            await self._broadcast_env_change()
            logger.info("Added to user PATH", directory=directory)
            return True

        except Exception as e:
            logger.error("Failed to add to PATH", directory=directory, error=str(e))
            return False

    async def remove_from_user_path(self, directory: str) -> bool:
        """Remove a directory from the user PATH."""
        import winreg
        try:
            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Environment",
                0,
                winreg.KEY_SET_VALUE,
            ) as key:
                current_path, _ = winreg.QueryValueEx(key, "PATH")
                entries = [p for p in current_path.split(";") if p.strip()]
                normalized = os.path.normpath(directory).lower()
                filtered = [p for p in entries if os.path.normpath(p).lower() != normalized]
                new_path = ";".join(filtered)
                winreg.SetValueEx(key, "PATH", 0, winreg.REG_EXPAND_SZ, new_path)

            await self._broadcast_env_change()
            logger.info("Removed from user PATH", directory=directory)
            return True
        except Exception as e:
            logger.error("Failed to remove from PATH", directory=directory, error=str(e))
            return False

    def get_path_issues(self) -> List[str]:
        """Detect common PATH issues."""
        issues = []
        user_path = self.get_user_path()

        for entry in user_path:
            if not entry:
                continue
            # Check for unresolved environment variables
            if "%" in entry:
                resolved = os.path.expandvars(entry)
                if "%" in resolved:
                    issues.append(f"Unresolved variable in PATH: {entry}")
            # Check for non-existent directories
            elif not os.path.exists(entry):
                issues.append(f"Non-existent directory in PATH: {entry}")

        return issues

    async def repair_path(self) -> List[str]:
        """Repair common PATH issues. Returns list of fixes applied."""
        fixes = []
        user_path = self.get_user_path()
        cleaned = []

        for entry in user_path:
            if not entry:
                continue
            # Remove non-existent directories
            resolved = os.path.expandvars(entry)
            if "%" not in resolved and not os.path.exists(resolved):
                fixes.append(f"Removed non-existent: {entry}")
                continue
            cleaned.append(entry)

        if fixes:
            import winreg
            try:
                with winreg.OpenKey(
                    winreg.HKEY_CURRENT_USER,
                    r"Environment",
                    0,
                    winreg.KEY_SET_VALUE,
                ) as key:
                    winreg.SetValueEx(key, "PATH", 0, winreg.REG_EXPAND_SZ, ";".join(cleaned))
                await self._broadcast_env_change()
            except Exception as e:
                logger.error("Failed to repair PATH", error=str(e))

        return fixes

    # --- Environment Variable Management ---

    async def set_user_env_var(self, name: str, value: str) -> bool:
        """
        Set a user-level environment variable.

        Args:
            name: Variable name
            value: Variable value

        Returns:
            True if successful
        """
        import winreg
        try:
            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Environment",
                0,
                winreg.KEY_SET_VALUE,
            ) as key:
                winreg.SetValueEx(key, name, 0, winreg.REG_EXPAND_SZ, value)

            await self._broadcast_env_change()
            logger.info("Environment variable set", name=name)
            return True
        except Exception as e:
            logger.error("Failed to set env var", name=name, error=str(e))
            return False

    async def get_user_env_var(self, name: str) -> Optional[str]:
        """Get a user-level environment variable."""
        import winreg
        try:
            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Environment",
                0,
                winreg.KEY_READ,
            ) as key:
                value, _ = winreg.QueryValueEx(key, name)
                return value
        except FileNotFoundError:
            return None
        except Exception as e:
            logger.error("Failed to get env var", name=name, error=str(e))
            return None

    async def delete_user_env_var(self, name: str) -> bool:
        """Delete a user-level environment variable."""
        import winreg
        try:
            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Environment",
                0,
                winreg.KEY_SET_VALUE,
            ) as key:
                winreg.DeleteValue(key, name)

            await self._broadcast_env_change()
            logger.info("Environment variable deleted", name=name)
            return True
        except FileNotFoundError:
            return True  # Already doesn't exist
        except Exception as e:
            logger.error("Failed to delete env var", name=name, error=str(e))
            return False

    async def _broadcast_env_change(self) -> None:
        """Broadcast environment variable change to Windows."""
        try:
            import ctypes
            HWND_BROADCAST = 0xFFFF
            WM_SETTINGCHANGE = 0x001A
            SMTO_ABORTIFHUNG = 0x0002
            result = ctypes.c_long()
            ctypes.windll.user32.SendMessageTimeoutW(
                HWND_BROADCAST, WM_SETTINGCHANGE, 0, "Environment",
                SMTO_ABORTIFHUNG, 5000, ctypes.byref(result),
            )
        except Exception as e:
            logger.debug("Failed to broadcast env change", error=str(e))

    # --- Admin Elevation ---

    def is_admin(self) -> bool:
        """Check if the current process has admin privileges."""
        try:
            import ctypes
            return ctypes.windll.shell32.IsUserAnAdmin() != 0
        except Exception:
            return False

    async def request_admin(self, reason: str = "") -> bool:
        """
        Request admin elevation for the current process.

        Note: On Windows, this typically requires restarting the process.
        This method logs the request and provides guidance.

        Args:
            reason: Reason for elevation request

        Returns:
            True if already admin
        """
        if self.is_admin():
            return True

        logger.warning(
            "Admin elevation required",
            reason=reason,
            message="Restart the deployment with administrator privileges",
        )
        return False

    async def run_as_admin(
        self,
        command: List[str],
        timeout: int = 300,
    ) -> Tuple[int, str, str]:
        """
        Run a command with elevated privileges using PowerShell.

        Args:
            command: Command to run
            timeout: Timeout in seconds

        Returns:
            Tuple of (exit_code, stdout, stderr)
        """
        cmd_str = " & ".join(f'"{c}"' if " " in c else c for c in command)
        ps_script = f"""
        Start-Process -FilePath "{command[0]}" -ArgumentList '{ " ".join(command[1:]) }' -Verb RunAs -Wait
        """
        return await self._run_command(
            ["powershell.exe", "-NoProfile", "-Command", ps_script],
            timeout=timeout,
        )

    # --- Registry Operations ---

    def get_registry_installed_version(self, key_path: str, value_name: str = "DisplayVersion") -> Optional[str]:
        """Get installed version from Windows Registry."""
        import winreg
        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key_path, 0, winreg.KEY_READ) as key:
                value, _ = winreg.QueryValueEx(key, value_name)
                return str(value)
        except FileNotFoundError:
            # Try CURRENT_USER
            try:
                with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_READ) as key:
                    value, _ = winreg.QueryValueEx(key, value_name)
                    return str(value)
            except FileNotFoundError:
                return None
        except Exception:
            return None

    def get_registry_uninstall_string(self, display_name: str) -> Optional[str]:
        """Get uninstall string for a program from registry."""
        import winreg
        paths = [
            r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall",
            r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall",
        ]

        for base_path in paths:
            try:
                with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, base_path, 0, winreg.KEY_READ) as key:
                    for i in range(winreg.QueryInfoKey(key)[0]):
                        subkey_name = winreg.EnumKey(key, i)
                        try:
                            with winreg.OpenKey(key, subkey_name) as subkey:
                                name, _ = winreg.QueryValueEx(subkey, "DisplayName")
                                if display_name.lower() in name.lower():
                                    uninstall, _ = winreg.QueryValueEx(subkey, "UninstallString")
                                    return str(uninstall)
                        except (FileNotFoundError, OSError):
                            continue
            except FileNotFoundError:
                continue

        return None

    # --- Utility ---

    async def _run_command(
        self,
        command: List[str],
        timeout: int = 120,
        cwd: Optional[str] = None,
    ) -> Tuple[int, str, str]:
        """Run a command asynchronously."""
        proc = None
        try:
            proc = await asyncio.create_subprocess_exec(
                *command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd,
            )
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=timeout
            )
            return (
                proc.returncode or 0,
                stdout.decode("utf-8", errors="replace"),
                stderr.decode("utf-8", errors="replace"),
            )
        except asyncio.TimeoutError:
            return (-1, "", f"Command timed out after {timeout}s")
        except FileNotFoundError:
            return (-2, "", f"Command not found: {command[0]}")
        except Exception as e:
            return (-3, "", str(e))
        finally:
            if proc:
                if proc.returncode is None:
                    try:
                        proc.kill()
                    except Exception:
                        pass
                if proc.stdout:
                    try:
                        proc.stdout.close()
                    except Exception:
                        pass
                if proc.stderr:
                    try:
                        proc.stderr.close()
                    except Exception:
                        pass
                try:
                    await proc.wait()
                except Exception:
                    pass

    def find_in_path(self, executable: str) -> Optional[str]:
        """Find an executable in PATH."""
        return shutil.which(executable)

    def get_program_files(self) -> str:
        """Get Program Files directory."""
        return os.environ.get("ProgramFiles", r"C:\Program Files")

    def get_program_files_x86(self) -> str:
        """Get Program Files (x86) directory."""
        return os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")

    def get_local_appdata(self) -> str:
        """Get Local AppData directory."""
        return os.environ.get("LOCALAPPDATA", os.path.expandvars(r"%USERPROFILE%\AppData\Local"))

    def get_roaming_appdata(self) -> str:
        """Get Roaming AppData directory."""
        return os.environ.get("APPDATA", os.path.expandvars(r"%USERPROFILE%\AppData\Roaming"))

    def get_user_profile(self) -> str:
        """Get user profile directory."""
        return os.environ.get("USERPROFILE", "")
