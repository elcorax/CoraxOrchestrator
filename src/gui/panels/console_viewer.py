"""
Corax Orchestrator - Live Console Viewer Panel.

Streaming log viewer, command output display, operation timeline,
and structured log event visualization with real-time updates.

Subscribes to RuntimeStateBus for live telemetry events.
"""

from typing import Optional, Any, List
from datetime import datetime

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QGroupBox, QTextEdit, QListWidget, QListWidgetItem, QSplitter,
    QComboBox, QCheckBox, QLineEdit,
)
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont, QColor, QTextCursor

from src.core.logging import get_logger
from src.runtime.state_bus import state_bus, BusEvent, EventType, EventSubscriber

logger = get_logger(__name__)


class ConsoleViewerPanel(QWidget):
    """
    Live console viewer with streaming logs, command output,
    and operation timeline visualization.

    Subscribes to RuntimeStateBus for live log/event telemetry.
    """

    def __init__(self, kernel: Any = None):
        super().__init__()
        self._kernel = kernel
        self._refresh_timer = QTimer()
        self._refresh_timer.timeout.connect(self._poll_logs)
        self._log_buffer: List[str] = []
        self._auto_scroll = True
        self._log_level_filter = "ALL"
        self._search_filter = ""
        self._subscriber_id: int = 0

        self._setup_ui()
        self._subscribe_to_state_bus()
        self._refresh_timer.start(1000)

    def _subscribe_to_state_bus(self) -> None:
        """Subscribe to state bus for event-driven log updates."""
        try:
            class _ConsoleBusSubscriber(EventSubscriber):
                def __init__(self, panel):
                    super().__init__("console_viewer")
                    self._panel = panel
                    self.subscribe_all()

                def on_event_sync(self, event: BusEvent) -> None:
                    try:
                        self._panel._on_bus_event(event)
                    except Exception:
                        pass

            subscriber = _ConsoleBusSubscriber(self)
            state_bus.attach(subscriber)
            self._subscriber_id = id(subscriber)
        except Exception as e:
            logger.debug("State bus subscription deferred: %s", e)

    def _on_bus_event(self, event: BusEvent) -> None:
        """Handle incoming bus events for live log display."""
        try:
            payload = event.payload
            if not payload:
                return

            # Log messages
            msg = payload.get("message") or payload.get("text") or ""
            level = (payload.get("level") or "INFO").upper()
            if msg:
                self.append_log(str(msg), level=level)

            # Command output
            cmd = payload.get("command", "")
            op = payload.get("operation", "")
            if cmd:
                self.append_command_output(str(cmd), command=str(op))

            # Operation timeline events
            evt_str = event.event_type.value if hasattr(event.event_type, 'value') else str(event.event_type)
            timeline_events = {
                "deployment.started": ("start", "Deployment started"),
                "deployment.completed": ("end", "Deployment completed"),
                "deployment.tool.started": ("start", "Tool deployment started"),
                "deployment.tool.completed": ("end", "Tool deployment completed"),
                "deployment.tool.failed": ("error", "Tool deployment failed"),
                "recovery.started": ("start", "Recovery started"),
                "recovery.completed": ("end", "Recovery completed"),
                "recovery.failed": ("error", "Recovery failed"),
            }
            if evt_str in timeline_events:
                evt_type, default_msg = timeline_events[evt_str]
                self.add_timeline_event(msg or default_msg, event_type=evt_type)
        except Exception:
            pass

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)

        splitter = QSplitter(Qt.Vertical)

        # ─── Top: Live Log Stream ────────────────────────────────────────
        log_group = QGroupBox("Live Log Stream")
        log_layout = QVBoxLayout(log_group)

        # Toolbar
        toolbar = QHBoxLayout()

        self._level_combo = QComboBox()
        self._level_combo.addItems(["ALL", "INFO", "WARN", "ERROR", "DEBUG"])
        self._level_combo.currentTextChanged.connect(self._on_filter_change)
        toolbar.addWidget(QLabel("Level:"))
        toolbar.addWidget(self._level_combo)

        self._search_input = QLineEdit()
        self._search_input.setPlaceholderText("Search logs...")
        self._search_input.textChanged.connect(self._on_filter_change)
        toolbar.addWidget(self._search_input, 1)

        self._clear_btn = QPushButton("Clear")
        self._clear_btn.clicked.connect(self._clear_logs)
        toolbar.addWidget(self._clear_btn)

        self._scroll_toggle = QPushButton("Auto-scroll: ON")
        self._scroll_toggle.clicked.connect(self._toggle_scroll)
        toolbar.addWidget(self._scroll_toggle)

        log_layout.addLayout(toolbar)

        # Log display
        self._log_display = QTextEdit()
        self._log_display.setReadOnly(True)
        self._log_display.setFont(QFont("Consolas", 9))
        self._log_display.setMaximumBlockCount(10000)
        log_layout.addWidget(self._log_display, 1)

        splitter.addWidget(log_group)

        # ─── Middle: Command Output ──────────────────────────────────────
        cmd_group = QGroupBox("Command Output")
        cmd_layout = QVBoxLayout(cmd_group)

        cmd_toolbar = QHBoxLayout()
        self._cmd_label = QLabel("No active command")
        cmd_toolbar.addWidget(self._cmd_label, 1)
        self._cmd_clear_btn = QPushButton("Clear Output")
        self._cmd_clear_btn.clicked.connect(self._clear_cmd_output)
        cmd_toolbar.addWidget(self._cmd_clear_btn)
        cmd_layout.addLayout(cmd_toolbar)

        self._cmd_output = QTextEdit()
        self._cmd_output.setReadOnly(True)
        self._cmd_output.setFont(QFont("Consolas", 9))
        self._cmd_output.setMaximumBlockCount(5000)
        cmd_layout.addWidget(self._cmd_output, 1)

        splitter.addWidget(cmd_group)

        # ─── Bottom: Operation Timeline ──────────────────────────────────
        timeline_group = QGroupBox("Operation Timeline")
        timeline_layout = QVBoxLayout(timeline_group)

        timeline_toolbar = QHBoxLayout()
        self._timeline_count = QLabel("0 events")
        timeline_toolbar.addWidget(self._timeline_count, 1)
        self._timeline_clear_btn = QPushButton("Clear Timeline")
        self._timeline_clear_btn.clicked.connect(self._clear_timeline)
        timeline_toolbar.addWidget(self._timeline_clear_btn)
        timeline_layout.addLayout(timeline_toolbar)

        self._timeline_list = QListWidget()
        self._timeline_list.setFont(QFont("Consolas", 9))
        timeline_layout.addWidget(self._timeline_list, 1)

        splitter.addWidget(timeline_group)

        splitter.setSizes([400, 200, 200])
        layout.addWidget(splitter)

    # ─── Public API ──────────────────────────────────────────────────────

    def append_log(self, text: str, level: str = "INFO") -> None:
        """Append a log line with color coding."""
        timestamp = datetime.now().strftime("%H:%M:%S")
        line = f"[{timestamp}] [{level}] {text}"

        # Apply filter
        if self._log_level_filter != "ALL" and level != self._log_level_filter:
            return
        if self._search_filter and self._search_filter.lower() not in text.lower():
            return

        color = self._get_level_color(level)
        self._log_display.setTextColor(color)
        self._log_display.append(line)
        self._log_display.setTextColor(QColor("#cdd6f4"))

        if self._auto_scroll:
            cursor = self._log_display.textCursor()
            cursor.movePosition(QTextCursor.End)
            self._log_display.setTextCursor(cursor)

    def append_command_output(self, text: str, command: str = "") -> None:
        """Append command output."""
        if command:
            self._cmd_label.setText(f"Command: {command}")
        self._cmd_output.append(text)
        cursor = self._cmd_output.textCursor()
        cursor.movePosition(QTextCursor.End)
        self._cmd_output.setTextCursor(cursor)

    def add_timeline_event(
        self, event: str, event_type: str = "info"
    ) -> None:
        """Add an operation timeline event."""
        timestamp = datetime.now().strftime("%H:%M:%S")
        prefix = {
            "info": "ℹ",
            "success": "✓",
            "warning": "⚠",
            "error": "✗",
            "start": "▶",
            "end": "■",
            "retry": "↻",
            "repair": "🔧",
        }.get(event_type, "•")

        item = QListWidgetItem(f"[{timestamp}] {prefix} {event}")
        if event_type == "error":
            item.setForeground(QColor("#f38ba8"))
        elif event_type == "warning":
            item.setForeground(QColor("#f9e2af"))
        elif event_type == "success":
            item.setForeground(QColor("#a6e3a1"))
        elif event_type == "start":
            item.setForeground(QColor("#89b4fa"))

        self._timeline_list.insertItem(0, item)
        while self._timeline_list.count() > 200:
            self._timeline_list.takeItem(self._timeline_list.count() - 1)
        self._timeline_count.setText(f"{self._timeline_list.count()} events")

    def set_active_command(self, command: str) -> None:
        """Set the currently active command."""
        self._cmd_label.setText(f"Running: {command}")

    def clear_command(self) -> None:
        """Clear the active command display."""
        self._cmd_label.setText("No active command")

    # ─── Internal ────────────────────────────────────────────────────────

    def _get_level_color(self, level: str) -> QColor:
        colors = {
            "ERROR": QColor("#f38ba8"),
            "WARN": QColor("#f9e2af"),
            "INFO": QColor("#89b4fa"),
            "DEBUG": QColor("#a6adc8"),
            "SUCCESS": QColor("#a6e3a1"),
        }
        return colors.get(level, QColor("#cdd6f4"))

    def _on_filter_change(self) -> None:
        self._log_level_filter = self._level_combo.currentText()
        self._search_filter = self._search_input.text()

    def _clear_logs(self) -> None:
        self._log_display.clear()

    def _clear_cmd_output(self) -> None:
        self._cmd_output.clear()
        self._cmd_label.setText("No active command")

    def _clear_timeline(self) -> None:
        self._timeline_list.clear()
        self._timeline_count.setText("0 events")

    def _toggle_scroll(self) -> None:
        self._auto_scroll = not self._auto_scroll
        self._scroll_toggle.setText(
            f"Auto-scroll: {'ON' if self._auto_scroll else 'OFF'}"
        )

    def _poll_logs(self) -> None:
        """Reserved for future buffer-based polling."""
        pass
