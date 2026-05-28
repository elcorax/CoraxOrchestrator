"""
Corax Orchestrator - Platform Factory.

Provides factory method for creating the appropriate platform
implementation based on the current operating system.
"""

from typing import Optional, TYPE_CHECKING

from src.platform.base import PlatformBase, PlatformType, detect_current_platform
from src.core.exceptions import PlatformError
from src.core.logging import get_logger

if TYPE_CHECKING:
    from src.platform.windows import WindowsPlatform
    from src.platform.macos import MacOSPlatform
    from src.platform.linux import LinuxPlatform

logger = get_logger(__name__)


class PlatformFactory:
    """
    Factory for creating platform-specific implementations.

    Usage:
        platform = PlatformFactory.create()
        info = platform.detect()
        exit_code, stdout, stderr = await platform.run_command("python", ["--version"])
    """

    _instance: Optional[PlatformBase] = None

    @classmethod
    def create(cls, platform_type: Optional[PlatformType] = None) -> PlatformBase:
        """
        Create a platform-specific implementation.

        Args:
            platform_type: Optional platform type override.
                          If not provided, auto-detects the current platform.

        Returns:
            A platform-specific implementation instance.

        Raises:
            PlatformError: If the platform is not supported.
        """
        if cls._instance is not None:
            return cls._instance

        if platform_type is None:
            platform_type = detect_current_platform()

        logger.info("Creating platform implementation", platform=platform_type.value)

        # Lazy imports to avoid circular import with stdlib `import platform` in submodules
        if platform_type == PlatformType.WINDOWS:
            from src.platform.windows import WindowsPlatform as _WindowsPlatform
            instance: PlatformBase = _WindowsPlatform()
        elif platform_type == PlatformType.MACOS:
            from src.platform.macos import MacOSPlatform as _MacOSPlatform
            instance = _MacOSPlatform()
        elif platform_type == PlatformType.LINUX:
            from src.platform.linux import LinuxPlatform as _LinuxPlatform
            instance = _LinuxPlatform()
        else:
            raise PlatformError(
                message=f"Unsupported platform: {platform_type}",
                platform=platform_type.value if platform_type else "unknown",
                operation="create_platform",
            )

        cls._instance = instance
        return instance

    @classmethod
    def reset(cls) -> None:
        """Reset the cached platform instance (useful for testing)."""
        cls._instance = None
