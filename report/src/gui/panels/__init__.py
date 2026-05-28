"""
Corax Orchestrator - GUI Panels.

All operational panels for the Corax GUI.
"""

from src.gui.panels.dashboard import DashboardPanel
from src.gui.panels.deployment_progress import DeploymentProgressPanel
from src.gui.panels.tool_selection import ToolSelectionPanel
from src.gui.panels.deployment_control import DeploymentControlPanel
from src.gui.panels.permissions import PermissionsPanel
from src.gui.panels.reports_viewer import ReportsViewerPanel
from src.gui.panels.runtime_monitor import RuntimeMonitorPanel
from src.gui.panels.settings import SettingsPanel
from src.gui.panels.console_viewer import ConsoleViewerPanel

__all__ = [
    "DashboardPanel",
    "DeploymentProgressPanel",
    "ToolSelectionPanel",
    "DeploymentControlPanel",
    "PermissionsPanel",
    "ReportsViewerPanel",
    "RuntimeMonitorPanel",
    "SettingsPanel",
    "ConsoleViewerPanel",
]
