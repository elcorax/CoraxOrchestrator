"""
Corax Orchestrator - Execution Capabilities Layer.

The Execution Capabilities Layer provides the autonomous agent with
real system execution abilities. It bridges the gap between high-level
agent decisions and low-level system operations.

Architecture:
    capabilities/
    ├── __init__.py              # Package exports
    ├── base.py                  # Abstract capability interfaces
    ├── terminal.py              # Terminal session management
    ├── process.py               # Process management
    ├── installer_interaction.py # Installer interaction abstraction
    ├── desktop.py               # Desktop automation foundation
    ├── browser.py               # Browser automation foundation
    ├── sandbox.py               # Secure execution boundaries
    └── recovery.py              # Recovery integration
"""

from src.agent.execution.capabilities.base import (
    CapabilityBase,
    CapabilityResult,
    CapabilityError,
    ExecutionContext,
    CapabilityRegistry,
)
from src.agent.execution.capabilities.terminal import (
    TerminalCapability,
    TerminalSession,
    TerminalConfig,
    ShellType,
)
from src.agent.execution.capabilities.process import (
    ProcessCapability,
    ProcessInfo,
    ProcessEvent,
    ProcessFilter,
)
from src.agent.execution.capabilities.installer_interaction import (
    InstallerInteractionCapability,
    InstallerConfig,
    InstallerState,
    InstallStrategy,
)
from src.agent.execution.capabilities.desktop import (
    DesktopCapability,
    WindowInfo,
    DesktopEvent,
)
from src.agent.execution.capabilities.browser import (
    BrowserCapability,
    BrowserInstance,
    BrowserTab,
)
from src.agent.execution.capabilities.sandbox import (
    SandboxCapability,
    SandboxPolicy,
    ExecutionPermission,
    PathProtectionRule,
)
from src.agent.execution.capabilities.recovery import (
    ExecutionRecoveryCapability,
    ExecutionCheckpoint,
    CommandRecoveryStrategy,
)

__all__ = [
    "CapabilityBase",
    "CapabilityResult",
    "CapabilityError",
    "ExecutionContext",
    "CapabilityRegistry",
    "TerminalCapability",
    "TerminalSession",
    "TerminalConfig",
    "ShellType",
    "ProcessCapability",
    "ProcessInfo",
    "ProcessEvent",
    "ProcessFilter",
    "InstallerInteractionCapability",
    "InstallerConfig",
    "InstallerState",
    "InstallStrategy",
    "DesktopCapability",
    "WindowInfo",
    "DesktopEvent",
    "BrowserCapability",
    "BrowserInstance",
    "BrowserTab",
    "SandboxCapability",
    "SandboxPolicy",
    "ExecutionPermission",
    "PathProtectionRule",
    "ExecutionRecoveryCapability",
    "ExecutionCheckpoint",
    "CommandRecoveryStrategy",
]
