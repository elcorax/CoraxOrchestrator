"""Cross-platform abstraction layer for Corax Orchestrator."""

# Import stdlib `platform` module FIRST to prevent shadowing by this package name.
# This ensures `import platform` in any submodule resolves to the stdlib module.
import sys as _sys
_sys.modules.setdefault('platform', __import__('platform'))

from src.platform.base import PlatformBase, PlatformType, Architecture
from src.platform.factory import PlatformFactory

# Lazy imports to avoid circular import with stdlib `import platform` in submodules
class _LazyModule:
    """Proxy that lazily imports platform submodules on first access."""
    def __init__(self, module_path, class_name):
        self._module_path = module_path
        self._class_name = class_name
        self._resolved = None
    def __call__(self, *args, **kwargs):
        if self._resolved is None:
            import importlib
            mod = importlib.import_module(self._module_path)
            self._resolved = getattr(mod, self._class_name)
        return self._resolved(*args, **kwargs)
    def __getattr__(self, name):
        if self._resolved is None:
            import importlib
            mod = importlib.import_module(self._module_path)
            self._resolved = getattr(mod, self._class_name)
        return getattr(self._resolved, name)

WindowsPlatform = _LazyModule("src.platform.windows", "WindowsPlatform")
MacOSPlatform = _LazyModule("src.platform.macos", "MacOSPlatform")
LinuxPlatform = _LazyModule("src.platform.linux", "LinuxPlatform")

__all__ = [
    "PlatformBase",
    "PlatformType",
    "Architecture",
    "WindowsPlatform",
    "MacOSPlatform",
    "LinuxPlatform",
    "PlatformFactory",
]
