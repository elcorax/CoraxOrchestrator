"""
Corax Orchestrator - GUI Layer.

Full operational GUI with PySide6, async event-driven architecture,
and runtime-integrated UI state.

Panels:
- Dashboard: deployment overview, runtime status, AI stack status
- Deployment Progress: real-time progress visualization
- Tool Selection: selectable installers, dependency graph, model selection
- Deployment Control: start/pause/resume/cancel, mode switching, emergency stop
- Permissions: elevation, filesystem, network, execution scope visibility
- Reports Viewer: searchable reports with HTML/JSON/Markdown rendering
- Runtime Monitor: live terminal output, structured logs, operation IDs
- Settings: deployment paths, retry, timeout, cache, recovery, autonomous mode
"""

from src.gui.ui_state import ui_state, UIStateManager, UIStatePhase
from src.gui.application import CoraxApplication
from src.gui.main_window import MainWindow

__all__ = [
    "ui_state",
    "UIStateManager",
    "UIStatePhase",
    "CoraxApplication",
    "MainWindow",
]
