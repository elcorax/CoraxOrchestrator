"""
Corax Orchestrator - Legacy Base Installer (Deprecated).

This module has been migrated to src.deployment.installers.base.
This file exists only as a compatibility shim and will be removed
in a future version. All new code should import from
src.deployment.installers instead.
"""

import warnings
from typing import Any

warnings.warn(
    "src.installers.base is deprecated. Use src.deployment.installers.base instead.",
    DeprecationWarning,
    stacklevel=2,
)

# Re-export from the new location
from src.deployment.installers.base import AIInstallerBase as BaseInstaller
from src.deployment.installers.base import InstallResult as InstallerResult
from src.deployment.installers.base import InstallStatus as InstallerStatus

__all__ = [
    "BaseInstaller",
    "InstallerResult",
    "InstallerStatus",
]
