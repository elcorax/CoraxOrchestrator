"""
Corax Orchestrator - PyInstaller hook for stdlib `platform` module.

CRITICAL: This hook prevents the `src.platform` package from shadowing
the stdlib `platform` module during PyInstaller's dependency graph analysis.

PyInstaller's graph walker (PyModuleGraph) processes `import platform` statements
and can resolve to the `src/platform` package instead of the stdlib module,
causing infinite recursion and silent freeze.

This hook forces PyInstaller to recognize the stdlib `platform` module
BEFORE it encounters the `src.platform` package.
"""

import os
import sys
from pathlib import Path


def hook(hook_api):
    """
    PyInstaller hook entry point.
    
    Ensures the stdlib `platform` module is registered in PyInstaller's
    module graph before the `src.platform` package is analyzed.
    """
    # Force PyInstaller to find stdlib platform module first
    import platform as _stdlib_platform
    
    # Get the actual file path of stdlib platform module
    platform_file = getattr(_stdlib_platform, '__file__', None)
    if platform_file and os.path.exists(platform_file):
        # Explicitly add stdlib platform to PyInstaller's module graph
        hook_api.add_module('platform', platform_file)
    
    # Exclude the src.platform package from being confused with stdlib platform
    # by ensuring PyInstaller resolves 'import platform' → stdlib
    logger = hook_api._logger if hasattr(hook_api, '_logger') else None
    if logger:
        logger.info("hook-platform: Registered stdlib platform module")
