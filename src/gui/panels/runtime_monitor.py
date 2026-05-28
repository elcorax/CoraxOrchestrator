"""
Corax Orchestrator - Live Deployment Monitor Panel.

Real-time terminal output, structured logs, operation IDs,
elapsed time, estimated remaining time, and current command display.

Uses the centralized UIStateManager for real-time synchronization.
"""

from typing import Optional, Any, List
from datetime import datetime

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QGroupBox, QGridLayout, QFrame, QScrollArea,
    QTextEdit, QListWidget, QListWidgetItem, QProgressBar,
    QSplitter, QTabWidget,
)
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont, QColor, QTextCursor

from src.core.logging import get_logger
from src.gui.ui_state import ui_state
from src.runtime.state_bus import state_bus, BusEvent, EventType, EventSubscriber


logger = get_logger(__name__)


class RuntimeMonitorPanel(QWidget):
    """Live deployment monitor with terminal output and structured logs."""

    def __init__(self, kernel: Any = None):
        super().__init__()
        self._kernel = kernel
        self._refresh_timer = QTimer()
        self._refresh_timer.timeout.connect(self._refresh)
        self._terminal_lines: List[str] = []
        self._max_terminal_lines = 500
        self._subscriber_id: Optional[str] = None

        self._setup_ui()
        self._subscribe_to_state_bus()
        self._refresh_timer.start(1000)

    def _subscribe_to_state_bus(self) -> None:
        """Subscribe to state bus for live telemetry events via anonymous subscriber."""
        try:
            class _MonitorSubscriber(EventSubscriber):
                """Internal subscriber that forwards bus events to the monitor."""
                def __init__(self, monitor):
                    super().__init__("runtime_monitor")
                    self._monitor = monitor
                    self.subscribe_all()

                def on_event_sync(self, event: BusEvent) -> None:
                    try:
                        self._monitor._on_bus_event(event)
                    except Exception:
                        pass

            subscriber = _MonitorSubscriber(self)
            state_bus.attach(subscriber)
            self._subscriber_id = id(subscriber)
            logger.info("RuntimeMonitor subscribed to state bus")
        except Exception as e:
            logger.warning(f"State bus subscription failed: {e}")


    def _on_bus_event(self, event: BusEvent) -> None:
        """Handle incoming state bus events for live display."""
        try:
            if event.event_type == EventType.DEPLOYMENT_PROGRESS:
                payload = event.payload
                tool = payload.get("tool_name", "unknown")
                progress = payload.get("progress_percent", 0)
                step = payload.get("current_step", "")
                self.append_terminal(f"[{tool}] {step} ({progress:.0f}%)")
                self.append_log("INFO", f"{tool}: {step} ({progress:.0f}%)")

            elif event.event_type == EventType.DEPLOYMENT_TOOL_STARTED:
                tool = event.payload.get("tool_name", "unknown")
                self.append_terminal(f"▶ Starting: {tool}")
                self.append_log("INFO", f"Starting deployment of {tool}")

            elif event.event_type == EventType.DEPLOYMENT_TOOL_COMPLETED:
                tool = event.payload.get("tool_name", "unknown")
                duration = event.payload.get("duration_seconds", 0)
                self.append_terminal(f"✓ Completed: {tool} ({duration:.1f}s)")
                self.append_log("SUCCESS", f"{tool} deployed in {duration:.1f}s")

            elif event.event_type == EventType.DEPLOYMENT_TOOL_FAILED:
                tool = event.payload.get("tool_name", "unknown")
                category = event.payload.get("failure_category", "unknown")
                self.append_terminal(f"✗ Failed: {tool} ({category})")
                self.append_log("ERROR", f"{tool} failed: {category}")

            elif event.event_type == EventType.DEPLOYMENT_STARTED:
                payload = event.payload
                mode = payload.get("mode", "safe")
                tools_count = payload.get("tools_count", 0)
                self.append_terminal(f"═══ Deployment STARTED ({mode} mode) ═══")
                self.append_log("INFO", f"Deployment started in {mode} mode with {tools_count} tools")

            elif event.event_type == EventType.DEPLOYMENT_COMPLETED:
                payload = event.payload
                success = payload.get("success", False)
                installed = payload.get("tools_installed", 0)
                total = payload.get("tools_total", 0)
                elapsed = payload.get("elapsed_seconds", 0)
                if success:
                    self.append_terminal(f"═══ Deployment COMPLETED ({installed}/{total} tools, {elapsed:.0f}s) ═══")
                    self.append_log("SUCCESS", f"Deployment completed: {installed}/{total} tools")
                else:
                    self.append_terminal(f"═══ Deployment FAILED ({installed}/{total} tools, {elapsed:.0f}s) ═══")
                    self.append_log("ERROR", "Deployment failed")

            elif event.event_type == EventType.RECOVERY_ACTIVITY:
                payload = event.payload
                component = payload.get("component", "unknown")
                action = payload.get("action", "")
                status = payload.get("status", "running")
                msg = f"[RECOVERY] {component}: {action} ({status})"
                self.append_terminal(msg)
                self.append_log("WARNING", msg)

            elif event.event_type == EventType.RETRY_EVENT:
                payload = event.payload
                tool = payload.get("tool_name", "unknown")
                attempt = payload.get("retry_count", 0)
                max_r = payload.get("max_retries", 3)
                err = payload.get("last_error", "")
                self.append_terminal(f"⟳ Retry {attempt}/{max_r} for {tool}: {err[:60]}")
                self.append_log("WARNING", f"Retrying {tool} ({attempt}/{max_r})")

            elif event.event_type == EventType.ERROR_OCCURRED:
                component = event.payload.get("component", "unknown")
                message = event.payload.get("message", "")
                self.append_log("ERROR", f"[{component}] {message}")

            elif event.event_type == EventType.KERNEL_READY:
                self.append_terminal("◆ Kernel ready")
                self.append_log("INFO", "Runtime kernel initialized")

            elif event.event_type == EventType.MODEL_PROGRESS:
                payload = event.payload
                model = payload.get("model_name", "unknown")
                progress = payload.get("progress_percent", 0)
                if int(progress) % 25 == 0 or progress >= 100:
                    self.append_terminal(f"  Model {model}: {progress:.0f}%")
        except Exception as e:
            logger.debug(f"Bus event handler error: {e}")


    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)

        # ─── Info Bar ─────────────────────────────────────────────────────
        info_bar = QHBoxLayout()

        self._op_id_label = QLabel("Operation: --")
        self._op_id_label.setObjectName("subheading")
        info_bar.addWidget(self._op_id_label)

        self._elapsed_label = QLabel("Elapsed: 0s")
        info_bar.addWidget(self._elapsed_label)

        self._remaining_label = QLabel("Remaining: --")
        info_bar.addWidget(self._remaining_label)

        self._current_tool_label = QLabel("Tool: --")
        self._current_tool_label.setObjectName("subheading")
        info_bar.addWidget(self._current_tool_label)

        info_bar.addStretch()
        layout.addLayout(info_bar)

        # ─── Terminal Output ──────────────────────────────────────────────
        terminal_group = QGroupBox("Live Terminal Output")
        terminal_layout = QVBoxLayout(terminal_group)

        self._terminal_output = QTextEdit()
        self._terminal_output.setReadOnly(True)
        self._terminal_output.setFont(QFont("Consolas", 10))
        self._terminal_output.setStyleSheet(
            "background-color: #1e1e2e; color: #cdd6f4;"
        )
        terminal_layout.addWidget(self._terminal_output)

        # Terminal controls
        term_controls = QHBoxLayout()
        clear_btn = QPushButton("Clear Terminal")
        clear_btn.clicked.connect(self._clear_terminal)
        term_controls.addWidget(clear_btn)
        term_controls.addStretch()
        terminal_layout.addLayout(term_controls)

        layout.addWidget(terminal_group, 2)

        # ─── Structured Logs ──────────────────────────────────────────────
        log_group = QGroupBox("Structured Logs")
        log_layout = QVBoxLayout(log_group)

        self._log_list = QListWidget()
        self._log_list.setFont(QFont("Consolas", 9))
        log_layout.addWidget(self._log_list)

        layout.addWidget(log_group, 1)

    def append_terminal(self, text: str) -> None:
        """Append text to the terminal output."""
        self._terminal_lines.append(text)
        if len(self._terminal_lines) > self._max_terminal_lines:
            self._terminal_lines = self._terminal_lines[-self._max_terminal_lines:]

        self._terminal_output.append(text)
        # Auto-scroll to bottom
        cursor = self._terminal_output.textCursor()
        cursor.movePosition(QTextCursor.End)
        self._terminal_output.setTextCursor(cursor)

    def append_log(self, level: str, message: str) -> None:
        """Append a structured log entry."""
        timestamp = datetime.now().strftime("%H:%M:%S")
        text = f"[{timestamp}] [{level}] {message}"
        item = QListWidgetItem(text)

        if level == "ERROR":
            item.setForeground(QColor("#f38ba8"))
        elif level == "WARNING":
            item.setForeground(QColor("#f9e2af"))
        elif level == "SUCCESS":
            item.setForeground(QColor("#a6e3a1"))
        else:
            item.setForeground(QColor("#cdd6f4"))

        self._log_list.insertItem(0, item)
        while self._log_list.count() > 200:
            self._log_list.takeItem(self._log_list.count() - 1)

    def _refresh(self) -> None:
        """Refresh from centralized UI state."""
        try:
            ops = ui_state.get_active_operations()

            if ops:
                op = ops[0]
                if hasattr(self, '_op_id_label') and self._op_id_label:
                    self._op_id_label.setText(f"Operation: {op.operation_id[:16]}...")
                if hasattr(self, '_elapsed_label') and self._elapsed_label:
                    self._elapsed_label.setText(f"Elapsed: {op.elapsed_seconds:.0f}s")
                if hasattr(self, '_remaining_label') and self._remaining_label:
                    if op.estimated_remaining_seconds > 0:
                        self._remaining_label.setText(
                            f"Remaining: {op.estimated_remaining_seconds:.0f}s"
                        )
                    else:
                        self._remaining_label.setText("Remaining: --")
                if hasattr(self, '_current_tool_label') and self._current_tool_label:
                    self._current_tool_label.setText(f"Tool: {op.tool_name}")
            else:
                if hasattr(self, '_op_id_label') and self._op_id_label:
                    self._op_id_label.setText("Operation: --")
                if hasattr(self, '_elapsed_label') and self._elapsed_label:
                    self._elapsed_label.setText(f"Elapsed: {ui_state.deployment_elapsed:.0f}s")
                if hasattr(self, '_remaining_label') and self._remaining_label:
                    remaining = ui_state.estimated_remaining
                    if remaining > 0:
                        self._remaining_label.setText(f"Remaining: {remaining:.0f}s")
                    else:
                        self._remaining_label.setText("Remaining: --")
                if hasattr(self, '_current_tool_label') and self._current_tool_label:
                    self._current_tool_label.setText("Tool: --")
        except Exception as e:
            logger.warning(f"RuntimeMonitor refresh suppressed: {e}")

    def _clear_terminal(self) -> None:
        """Clear the terminal output."""
        self._terminal_lines.clear()
        self._terminal_output.clear()
