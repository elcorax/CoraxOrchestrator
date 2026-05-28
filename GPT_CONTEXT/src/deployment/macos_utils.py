"""
Corax Orchestrator - macOS Abstraction Preparation.

Provides macOS-specific execution abstractions for future deployment support.
Prepared for brew, dmg/pkg installation, and shell profile management.

NOTE: This module is prepared for future macOS deployment support.
Full macOS deployment is not yet implemented.
"""

from typing import Dict, Any, List, Optional, Tuple
import asyncio
import os
import shutil
from pathlib import Path

from src.core.logging import get_logger

logger = get_logger(__name__)


class MacOSUtils:
    """
    macOS-specific execution utilities for deployment.

    Provides brew integration, DMG/PKG installation, and shell
    profile management abstractions.

    NOTE: This is a preparation layer. Full macOS deployment
    is not yet implemented.
    """

    def __init__(self) -> None:
        self._brew_available: Optional[bool] = None

    # --- Brew Integration ---

    async def check_brew(self) -> bool:
        """Check if Homebrew is available."""
        if self._brew_available is not None:
            return self._brew_available

        brew_path = shutil.which("brew")
        self._brew_available = brew_path is not None
        if self._brew_available:
            logger.info("Homebrew available", path=brew_path)
        return self._brew_available

    async def brew_install(self, package: str, timeout: int = 300) -> Tuple[int, str, str]:
        """Install a package using Homebrew."""
        return await self._run_command(["brew", "install", package], timeout=timeout)

    async def brew_cask_install(self, package: str, timeout: int = 300) -> Tuple[int, str, str]:
        """Install a cask using Homebrew."""
        return await self._run_command(["brew", "install", "--cask", package], timeout=timeout)

    async def brew_list(self, package: str) -> bool:
        """Check if a package is installed via Homebrew."""
        exit_code, _, _ = await self._run_command(
            ["brew", "list", package], timeout=30
        )
        return exit_code == 0

    # --- DMG/PKG Installation ---

    async def install_dmg(
        self,
        dmg_path: str,
        app_name: str,
        timeout: int = 120,
    ) -> Tuple[int, str, str]:
        """
        Install an application from a DMG file.

        Mounts the DMG, copies the .app to /Applications, then unmounts.

        Args:
            dmg_path: Path to the .dmg file
            app_name: Name of the .app bundle (e.g., "Visual Studio Code.app")
            timeout: Timeout in seconds

        Returns:
            Tuple of (exit_code, stdout, stderr)
        """
        script = f"""
        hdiutil attach "{dmg_path}" -nobrowse -quiet
        cp -R "/Volumes/{app_name.replace('.app', '')}/{app_name}" /Applications/
        hdiutil detach "/Volumes/{app_name.replace('.app', '')}" -quiet
        """
        return await self._run_command(["bash", "-c", script], timeout=timeout)

    async def install_pkg(
        self,
        pkg_path: str,
        timeout: int = 120,
    ) -> Tuple[int, str, str]:
        """
        Install a package from a PKG file.

        Args:
            pkg_path: Path to the .pkg file
            timeout: Timeout in seconds

        Returns:
            Tuple of (exit_code, stdout, stderr)
        """
        return await self._run_command(
            ["sudo", "installer", "-pkg", pkg_path, "-target", "/"],
            timeout=timeout,
        )

    # --- Shell Profile Management ---

    def get_shell_profile_path(self) -> Optional[str]:
        """Get the path to the user's shell profile."""
        shell = os.environ.get("SHELL", "")
        home = os.path.expanduser("~")

        if "zsh" in shell:
            return os.path.join(home, ".zshrc")
        elif "bash" in shell:
            return os.path.join(home, ".bash_profile")
        elif "fish" in shell:
            return os.path.join(home, ".config", "fish", "config.fish")
        return os.path.join(home, ".zshrc")  # Default to .zshrc

    def read_shell_profile(self) -> str:
        """Read the current shell profile content."""
        profile_path = self.get_shell_profile_path()
        if profile_path and os.path.exists(profile_path):
            with open(profile_path, "r") as f:
                return f.read()
        return ""

    async def append_to_shell_profile(self, lines: List[str]) -> bool:
        """
        Append lines to the shell profile if not already present.

        Args:
            lines: Lines to append

        Returns:
            True if modified
        """
        profile_path = self.get_shell_profile_path()
        if not profile_path:
            logger.warning("No shell profile found")
            return False

        current = self.read_shell_profile()
        modified = False

        with open(profile_path, "a") as f:
            for line in lines:
                if line not in current:
                    f.write(f"\n{line}")
                    modified = True

        if modified:
            logger.info("Shell profile updated", path=profile_path)

        return modified

    async def add_to_path_in_profile(self, directory: str) -> bool:
        """
        Add a directory to PATH in the shell profile.

        Args:
            directory: Directory to add to PATH

        Returns:
            True if modified
        """
        export_line = f'export PATH="$PATH:{directory}"'
        return await self.append_to_shell_profile([export_line])

    # --- Utility ---

    async def _run_command(
        self,
        command: List[str],
        timeout: int = 120,
    ) -> Tuple[int, str, str]:
        """Run a command asynchronously."""
        try:
            proc = await asyncio.create_subprocess_exec(
                *command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
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
