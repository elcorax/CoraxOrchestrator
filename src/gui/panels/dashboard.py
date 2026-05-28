"""
Corax Orchestrator - Dashboard Panel.

Deployment overview with runtime status, AI stack status,
current phase, operation progress, active tasks, retry queue,
failure queue, and repair activity.

Uses the centralized UIStateManager for real-time synchronization.
"""

import asyncio
from typing import Optional, Dict, Any
from datetime import datetime

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QGroupBox, QGridLayout, QFrame, QScrollArea, QListWidget,
    QListWidgetItem, QProgressBar,
)
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont, QColor

from src.core.logging import get_logger
from src.gui.ui_state import ui_state, UIStatePhase

logger = get_logger(__name__)


class DashboardPanel(QWidget):
    """Main dashboard showing deployment overview and system status."""

    def __init__(self, kernel: Any = None):
        super().__init__()
        self._kernel = kernel
        self._refresh_timer = QTimer()
        self._refresh_timer.timeout.connect(self._refresh)
        self._scan_result = None

        self._setup_ui()
        self._refresh_timer.start(2000)

        # Register for state changes
        ui_state.on_state_change(self._on_ui_state_change)

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)

        # Corax Branding Header
        header = QHBoxLayout()
        logo_label = QLabel("🔷")
        logo_font = QFont()
        logo_font.setPointSize(28)
        logo_label.setFont(logo_font)
        header.addWidget(logo_label)

        title_col = QVBoxLayout()
        title = QLabel("Corax Orchestrator")
        title_font = QFont()
        title_font.setPointSize(16)
        title_font.setBold(True)
        title.setFont(title_font)
        title.setStyleSheet("color: #89b4fa;")
        title_col.addWidget(title)

        subtitle = QLabel("CORAX LIMITED · Intelligent AI Workstation Deployment")
        subtitle.setStyleSheet("color: #a6adc8; font-size: 10px;")
        title_col.addWidget(subtitle)
        header.addLayout(title_col)
        header.addStretch()
        layout.addLayout(header)

        # Separator
        sep = QLabel("━" * 60)
        sep.setStyleSheet("color: #313244;")
        layout.addWidget(sep)

        # Top row: status cards
        cards = QHBoxLayout()

        # Runtime status card
        self._runtime_card = self._make_card("Runtime Status", "Unknown", "status_warn")
        cards.addWidget(self._runtime_card)

        # Deployment status card
        self._deploy_card = self._make_card("Deployment", "Not Started", "subheading")
        cards.addWidget(self._deploy_card)

        # AI Stack status card
        self._ai_card = self._make_card("AI Stack", "Not Deployed", "subheading")
        cards.addWidget(self._ai_card)

        # System health card
        self._health_card = self._make_card("System Health", "Unknown", "status_warn")
        cards.addWidget(self._health_card)

        # Timing & Progress row
        timing_row = QHBoxLayout()

        timing_group = QGroupBox("Deployment Timing")
        timing_layout = QVBoxLayout(timing_group)
        self._elapsed_label = QLabel("Elapsed: 0s")
        self._elapsed_label.setObjectName("subheading")
        timing_layout.addWidget(self._elapsed_label)
        self._remaining_label = QLabel("Estimated remaining: --")
        self._remaining_label.setObjectName("subheading")
        timing_layout.addWidget(self._remaining_label)
        self._throughput_label = QLabel("Throughput: -- tools/min")
        self._throughput_label.setObjectName("subheading")
        timing_layout.addWidget(self._throughput_label)
        timing_row.addWidget(timing_group)

        deploy_progress_group = QGroupBox("Deployment Progress")
        deploy_progress_layout = QVBoxLayout(deploy_progress_group)
        self._deploy_progress_bar = QProgressBar()
        self._deploy_progress_bar.setRange(0, 100)
        self._deploy_progress_bar.setValue(0)
        deploy_progress_layout.addWidget(self._deploy_progress_bar)
        self._deploy_summary_label = QLabel("0 / 0 installed")
        self._deploy_summary_label.setObjectName("subheading")
        self._deploy_summary_label.setAlignment(Qt.AlignCenter)
        deploy_progress_layout.addWidget(self._deploy_summary_label)
        timing_row.addWidget(deploy_progress_group)

        layout.addLayout(timing_row)

        # Middle: scan results and activity
        mid = QHBoxLayout()

        # Scan results
        scan_group = QGroupBox("System Overview")
        scan_layout = QVBoxLayout(scan_group)
        self._scan_info = QLabel("Run a scan to see system information")
        self._scan_info.setWordWrap(True)
        scan_layout.addWidget(self._scan_info)

        scan_btn = QPushButton("Run Scan")
        scan_btn.setObjectName("primary")
        scan_btn.clicked.connect(self.run_scan)
        scan_layout.addWidget(scan_btn)

        mid.addWidget(scan_group)

        # Activity feed
        activity_group = QGroupBox("Recent Activity")
        activity_layout = QVBoxLayout(activity_group)
        self._activity_list = QListWidget()
        activity_layout.addWidget(self._activity_list)
        mid.addWidget(activity_group)

        layout.addLayout(mid, 1)

        # Bottom: retry/failure queues
        bottom = QHBoxLayout()

        retry_group = QGroupBox("Retry Queue")
        retry_layout = QVBoxLayout(retry_group)
        self._retry_list = QListWidget()
        retry_layout.addWidget(self._retry_list)
        bottom.addWidget(retry_group)

        failure_group = QGroupBox("Failure Queue")
        failure_layout = QVBoxLayout(failure_group)
        self._failure_list = QListWidget()
        failure_layout.addWidget(self._failure_list)
        bottom.addWidget(failure_group)

        repair_group = QGroupBox("Repair Activity")
        repair_layout = QVBoxLayout(repair_group)
        self._repair_list = QListWidget()
        repair_layout.addWidget(self._repair_list)
        bottom.addWidget(repair_group)

        layout.addLayout(bottom)

    def _make_card(self, title: str, value: str, style: str) -> QGroupBox:
        card = QGroupBox(title)
        layout = QVBoxLayout(card)
        label = QLabel(value)
        label.setObjectName(style)
        label.setAlignment(Qt.AlignCenter)
        font = QFont()
        font.setPointSize(14)
        font.setBold(True)
        label.setFont(font)
        layout.addWidget(label)
        setattr(self, f"_{title.lower().replace(' ', '_')}_label", label)
        return card

    def run_scan(self) -> None:
        """Execute a system scan asynchronously."""
        ui_state.phase = UIStatePhase.SCANNING
        self._scan_info.setText("Scanning system...")
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.ensure_future(self._do_scan())
            else:
                loop.run_until_complete(self._do_scan())
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(self._do_scan())

    async def _do_scan(self) -> None:
        """Perform the actual scan."""
        try:
            from src.modules.system_scanner import SystemScanner
            scanner = SystemScanner()
            result = await scanner.scan()
            result_dict = result.to_dict()
            self._scan_result = result_dict
            ui_state.set_scan_result(result_dict)
            self._update_scan_display()
            self._add_activity("System scan completed")
            ui_state.system_health = "OK"
            ui_state.phase = UIStatePhase.IDLE
        except Exception as e:
            self._scan_info.setText(f"Scan failed: {e}")
            self._add_activity(f"Scan failed: {e}")
            ui_state.system_health = "Degraded"
            ui_state.phase = UIStatePhase.FAILED

    def _update_scan_display(self) -> None:
        """Update UI with scan results."""
        if not self._scan_result:
            return
        hw = self._scan_result.get("hardware", {})
        cpu = hw.get("cpu", {})
        mem = hw.get("memory", {})
        os_info = self._scan_result.get("os", {})

        lines = [
            f"OS: {os_info.get('platform', 'Unknown')} {os_info.get('os_version', '')}",
            f"CPU: {cpu.get('name', 'Unknown')} ({cpu.get('cores', '?')} cores)",
            f"RAM: {mem.get('total_gb', '?')} GB",
            f"Hostname: {os_info.get('hostname', 'Unknown')}",
        ]
        self._scan_info.setText("\n".join(lines))

    def _add_activity(self, text: str) -> None:
        """Add an activity entry - guarded against missing widget."""
        if not hasattr(self, '_activity_list') or self._activity_list is None:
            return
        item = QListWidgetItem(f"[{datetime.now().strftime('%H:%M:%S')}] {text}")
        self._activity_list.insertItem(0, item)
        while self._activity_list.count() > 50:
            self._activity_list.takeItem(self._activity_list.count() - 1)

    def _on_ui_state_change(self) -> None:
        """Called when UI state changes - triggers refresh."""
        # This runs in the UI thread via the timer
        pass

    def _refresh(self) -> None:
        """Periodic refresh from centralized UI state - fully guarded."""
        try:
            # Update status cards from UI state with hasattr guards
            labels_map = {
                "runtime_status": (getattr(self, '_runtime_status_label', None), 
                                    getattr(ui_state, 'runtime_status', 'Unknown')),
                "deployment_status": (getattr(self, '_deployment_label', None), 
                                       getattr(ui_state, 'deployment_status', 'Not Started')),
                "ai_stack_status": (getattr(self, '_ai_stack_label', None), 
                                     getattr(ui_state, 'ai_stack_status', 'Not Deployed')),
                "system_health": (getattr(self, '_system_health_label', None), 
                                   getattr(ui_state, 'system_health', 'Unknown')),
            }
            style_map = {
                "Ready": "status_ok",
                "OK": "status_ok",
                "Running": "status_ok",
                "Starting": "status_warn",
                "Unknown": "status_warn",
                "Failed": "status_error",
                "Degraded": "status_warn",
                "Not Started": "subheading",
                "Not Deployed": "subheading",
            }
            for _key, (label, status) in labels_map.items():
                if label is None:
                    continue
                style = style_map.get(status, "subheading")
                try:
                    label.setText(str(status))
                    label.setObjectName(style)
                    style_obj = label.style()
                    if style_obj is not None:
                        style_obj.unpolish(label)
                        style_obj.polish(label)
                except Exception as inner_e:
                    logger.warning(f"Dashboard card style update suppressed: {inner_e}")

            # Update retry queue - guarded
            if hasattr(self, '_retry_list') and self._retry_list is not None:
                self._retry_list.clear()
                for item in ui_state.get_retry_queue():
                    text = (
                        f"{item.tool_name} "
                        f"(retry {item.retry_count}/{item.max_retries})"
                    )
                    if item.last_error:
                        text += f" - {item.last_error[:60]}"
                    self._retry_list.addItem(text)

            # Update failure queue - guarded
            if hasattr(self, '_failure_list') and self._failure_list is not None:
                self._failure_list.clear()
                for tool in ui_state.get_failure_queue():
                    self._failure_list.addItem(tool)

            # Update timing - guarded
            if hasattr(self, '_elapsed_label') and self._elapsed_label is not None:
                elapsed = getattr(ui_state, 'deployment_elapsed', 0)
                self._elapsed_label.setText(f"Elapsed: {elapsed:.0f}s")

            if hasattr(self, '_remaining_label') and self._remaining_label is not None:
                remaining = getattr(ui_state, 'estimated_remaining', 0)
                if remaining > 0:
                    self._remaining_label.setText(f"Estimated remaining: {remaining:.0f}s")
                else:
                    self._remaining_label.setText("Estimated remaining: --")

            # Update deployment progress - guarded
            if hasattr(self, '_deploy_progress_bar') and self._deploy_progress_bar is not None:
                total = getattr(ui_state, 'tools_total', 0)
                installed = getattr(ui_state, 'tools_installed', 0)
                failed = getattr(ui_state, 'tools_failed', 0)
                if total > 0:
                    progress = int((installed + failed) / total * 100)
                    self._deploy_progress_bar.setValue(progress)
                    if hasattr(self, '_deploy_summary_label'):
                        self._deploy_summary_label.setText(
                            f"{installed} / {total} installed ({failed} failed)"
                        )

            # Update repair activities - guarded
            if hasattr(self, '_repair_list') and self._repair_list is not None:
                self._repair_list.clear()
                for activity in ui_state.get_repair_activities()[:10]:
                    text = f"[{activity.status}] {activity.component}: {activity.action}"
                    if activity.message:
                        text += f" - {activity.message[:60]}"
                    item = QListWidgetItem(text)
                    if activity.status == "failed":
                        item.setForeground(QColor("#f38ba8"))
                    elif activity.status == "completed":
                        item.setForeground(QColor("#a6e3a1"))
                    self._repair_list.insertItem(0, item)

        except Exception as e:
            logger.warning(f"Dashboard refresh suppressed: {e}", exc_info=True)
