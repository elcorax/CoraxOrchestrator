"""
AI Runtime and Developer Tool Installers package.

Uses lazy imports to avoid cascading import failures.
Each installer class is imported only when accessed.
"""

from typing import TYPE_CHECKING

# Always import base classes (they have no heavy dependencies)
from src.deployment.installers.base import AIInstallerBase, InstallResult, InstallStatus
from src.deployment.installers.dev_base import DevInstallerBase

# Lazy imports for concrete installers to avoid cascading failures
# Each installer is imported on first access via __getattr__
_INSTALLER_REGISTRY: dict = {}

__all__ = [
    "AIInstallerBase",
    "InstallResult",
    "InstallStatus",
    "DevInstallerBase",
    "OllamaInstaller",
    "LMStudioInstaller",
    "OpenWebUIInstaller",
    "AnythingLLMInstaller",
    "ComfyUIInstaller",
    "OpenInterpreterInstaller",
    "GitInstaller",
    "PythonInstaller",
    "NodeInstaller",
    "VSCodeInstaller",
    "WindsurfInstaller",
    "JavaInstaller",
    "FlutterInstaller",
    "DockerInstaller",
]


def __getattr__(name: str):
    """Lazy-load installer classes on first access."""
    _lazy_map = {
        "OllamaInstaller": "src.deployment.installers.ollama",
        "LMStudioInstaller": "src.deployment.installers.lm_studio",
        "OpenWebUIInstaller": "src.deployment.installers.open_webui",
        "AnythingLLMInstaller": "src.deployment.installers.anythingllm",
        "ComfyUIInstaller": "src.deployment.installers.comfyui",
        "OpenInterpreterInstaller": "src.deployment.installers.open_interpreter",
        "GitInstaller": "src.deployment.installers.git_installer",
        "PythonInstaller": "src.deployment.installers.python_installer",
        "NodeInstaller": "src.deployment.installers.node_installer",
        "VSCodeInstaller": "src.deployment.installers.vscode_installer",
        "WindsurfInstaller": "src.deployment.installers.windsurf_installer",
        "JavaInstaller": "src.deployment.installers.java_installer",
        "FlutterInstaller": "src.deployment.installers.flutter_installer",
        "DockerInstaller": "src.deployment.installers.docker_installer",
    }

    if name in _lazy_map:
        import importlib
        module = importlib.import_module(_lazy_map[name])
        cls = getattr(module, name)
        # Cache for subsequent access
        globals()[name] = cls
        return cls

    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


