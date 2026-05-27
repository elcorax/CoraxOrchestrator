"""
Corax Orchestrator - ComfyUI Installer.

Deploys ComfyUI for local image generation workflows.
"""

from typing import Dict, Any, List, Optional
import asyncio
import json
import os
import tempfile

from src.deployment.installers.base import (
    AIInstallerBase,
    InstallResult,
    InstallStatus,
)
from src.core.logging import get_logger

logger = get_logger(__name__)


class ComfyUIInstaller(AIInstallerBase):
    """
    ComfyUI installer - Local image generation workflow UI.

    Supports:
    - Git clone from GitHub
    - Python virtual environment setup
    - Dependency installation
    - Custom node management
    - Model directory configuration
    """

    COMFYUI_REPO = "https://github.com/comfyanonymous/ComfyUI.git"
    COMFYUI_DEFAULT_PORT = 8188

    @property
    def tool_name(self) -> str:
        return "ComfyUI"

    @property
    def tool_key(self) -> str:
        return "comfyui"

    @property
    def description(self) -> str:
        return "Local image generation workflow UI for Stable Diffusion"

    @property
    def default_port(self) -> Optional[int]:
        return self.COMFYUI_DEFAULT_PORT

    @property
    def min_disk_gb(self) -> int:
        return 10

    @property
    def dependencies(self) -> List[str]:
        return ["git", "python"]

    async def detect(self) -> InstallResult:
        """Detect if ComfyUI is installed."""
        install_paths = self._get_common_paths()
        for path in install_paths:
            main_py = os.path.join(path, "main.py")
            if os.path.exists(main_py):
                # Get version from git
                version = "unknown"
                git_dir = os.path.join(path, ".git")
                if os.path.exists(git_dir):
                    code, stdout, _ = await self._run_command(
                        ["git", "-C", path, "describe", "--tags", "--always"],
                        timeout=10,
                    )
                    if code == 0:
                        version = stdout.strip()

                return InstallResult(
                    tool_name=self.tool_name,
                    status=InstallStatus.INSTALLED,
                    version=version,
                    install_path=path,
                    port=self.COMFYUI_DEFAULT_PORT,
                    details={"detected_via": "common_path"},
                )

        return InstallResult(
            tool_name=self.tool_name,
            status=InstallStatus.NOT_INSTALLED,
        )

    async def install(self, config: Optional[Dict[str, Any]] = None) -> InstallResult:
        """Install ComfyUI."""
        config = config or {}
        logger.info("Installing ComfyUI")

        try:
            install_dir = config.get(
                "install_dir",
                self._get_default_install_dir(),
            )

            # Clone repository
            logger.info("Cloning ComfyUI repository", target=install_dir)
            if os.path.exists(install_dir):
                # Update existing
                code, stdout, stderr = await self._run_command(
                    ["git", "-C", install_dir, "pull"],
                    timeout=120,
                )
                if code != 0:
                    return InstallResult(
                        tool_name=self.tool_name,
                        status=InstallStatus.FAILED,
                        error=f"Git pull failed: {stderr[:500]}",
                    )
            else:
                # Fresh clone
                os.makedirs(os.path.dirname(install_dir), exist_ok=True)
                code, stdout, stderr = await self._run_command(
                    ["git", "clone", self.COMFYUI_REPO, install_dir],
                    timeout=300,
                )
                if code != 0:
                    return InstallResult(
                        tool_name=self.tool_name,
                        status=InstallStatus.FAILED,
                        error=f"Git clone failed: {stderr[:500]}",
                    )

            # Create virtual environment
            venv_path = os.path.join(install_dir, "venv")
            if not os.path.exists(venv_path):
                logger.info("Creating virtual environment")
                code, stdout, stderr = await self._run_command(
                    [self._find_in_path("python") or "python",
                     "-m", "venv", venv_path],
                    timeout=120,
                )
                if code != 0:
                    return InstallResult(
                        tool_name=self.tool_name,
                        status=InstallStatus.FAILED,
                        error=f"Virtual env creation failed: {stderr[:500]}",
                    )

            # Install dependencies
            logger.info("Installing ComfyUI dependencies")
            pip_path = os.path.join(venv_path, "Scripts", "pip") if self._is_windows else os.path.join(venv_path, "bin", "pip")

            code, stdout, stderr = await self._run_command(
                [pip_path, "install", "-r",
                 os.path.join(install_dir, "requirements.txt")],
                timeout=600,
            )
            if code != 0:
                return InstallResult(
                    tool_name=self.tool_name,
                    status=InstallStatus.FAILED,
                    error=f"Dependency installation failed: {stderr[:500]}",
                )

            # Install PyTorch if not present
            code, stdout, _ = await self._run_command(
                [pip_path, "list", "--format=columns"],
                timeout=30,
            )
            if "torch" not in stdout:
                logger.info("Installing PyTorch")
                await self._run_command(
                    [pip_path, "install", "torch", "torchvision",
                     "--index-url", "https://download.pytorch.org/whl/cpu"],
                    timeout=600,
                )

            return await self.verify()

        except Exception as e:
            logger.error("ComfyUI installation failed", error=str(e))
            return InstallResult(
                tool_name=self.tool_name,
                status=InstallStatus.FAILED,
                error=str(e),
            )

    async def verify(self) -> InstallResult:
        """Verify ComfyUI installation."""
        install_paths = self._get_common_paths()
        found_path = None
        for path in install_paths:
            main_py = os.path.join(path, "main.py")
            if os.path.exists(main_py):
                found_path = path
                break

        if not found_path:
            return InstallResult(
                tool_name=self.tool_name,
                status=InstallStatus.FAILED,
                error="ComfyUI not found",
            )

        # Check venv
        venv_path = os.path.join(found_path, "venv")
        venv_ok = os.path.exists(venv_path)

        # Check key dependencies
        pip_path = os.path.join(venv_path, "Scripts", "pip") if self._is_windows else os.path.join(venv_path, "bin", "pip")
        deps_ok = False
        if os.path.exists(pip_path):
            code, stdout, _ = await self._run_command(
                [pip_path, "list", "--format=columns"],
                timeout=30,
            )
            deps_ok = "torch" in stdout

        return InstallResult(
            tool_name=self.tool_name,
            status=InstallStatus.INSTALLED,
            install_path=found_path,
            port=self.COMFYUI_DEFAULT_PORT,
            details={
                "venv_created": venv_ok,
                "dependencies_installed": deps_ok,
                "install_path": found_path,
            },
        )

    async def configure(self, config: Dict[str, Any]) -> InstallResult:
        """Configure ComfyUI."""
        install_path = self._get_common_paths()[0] if self._get_common_paths() else None
        if not install_path or not os.path.exists(install_path):
            return InstallResult(
                tool_name=self.tool_name,
                status=InstallStatus.FAILED,
                error="ComfyUI not installed",
            )

        updates = []

        # Configure extra model paths
        if "extra_model_paths" in config:
            extra_paths_config = os.path.join(install_path, "extra_model_paths.yaml")
            with open(extra_paths_config, "w") as f:
                import yaml
                yaml.dump(config["extra_model_paths"], f)
            updates.append("extra_model_paths")

        return InstallResult(
            tool_name=self.tool_name,
            status=InstallStatus.INSTALLED,
            install_path=install_path,
            details={"configured": updates},
        )

    async def uninstall(self) -> InstallResult:
        """Uninstall ComfyUI."""
        install_paths = self._get_common_paths()
        for path in install_paths:
            if os.path.exists(path):
                import shutil
                shutil.rmtree(path, ignore_errors=True)

        return InstallResult(
            tool_name=self.tool_name,
            status=InstallStatus.NOT_INSTALLED,
        )

    async def repair(self) -> InstallResult:
        """Repair ComfyUI installation."""
        logger.info("Repairing ComfyUI installation")

        # Reinstall dependencies
        install_paths = self._get_common_paths()
        for path in install_paths:
            venv_path = os.path.join(path, "venv")
            pip_path = os.path.join(venv_path, "Scripts", "pip") if self._is_windows else os.path.join(venv_path, "bin", "pip")

            if os.path.exists(pip_path):
                await self._run_command(
                    [pip_path, "install", "--upgrade", "-r",
                     os.path.join(path, "requirements.txt")],
                    timeout=600,
                )

        return await self.verify()

    def _get_default_install_dir(self) -> str:
        """Get default ComfyUI install directory."""
        if self._is_windows:
            return os.path.expandvars(r"%USERPROFILE%\ComfyUI")
        elif self._is_macos:
            return os.path.expanduser("~/ComfyUI")
        else:
            return os.path.expanduser("~/ComfyUI")

    def _get_common_paths(self) -> List[str]:
        """Get common ComfyUI install paths."""
        paths = [self._get_default_install_dir()]
        if self._is_windows:
            paths.append(r"C:\ComfyUI")
        return paths
