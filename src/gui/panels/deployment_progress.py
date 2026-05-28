"""
Corax Orchestrator - Deployment Progress Panel.

Real-time deployment visualization with progress bars,
per-tool progress, estimated remaining time, elapsed time,
operation IDs, phase indicators, and current commands.

Uses the centralized UIStateManager for real-time synchronization.
"""

import asyncio
import time
from typing import Optional, Dict, Any, List
from datetime import datetime

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QGroupBox, QGridLayout, QProgressBar, QFrame, QScrollArea,
    QTextEdit, QListWidget, QListWidgetItem, QTableWidget,
    QTableWidgetItem, QHeaderView,
)
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont, QColor

from src.core.logging import get_logger
from src.gui.ui_state import ui_state, UIStatePhase

logger = get_logger(__name__)


class DeploymentProgressPanel(QWidget):
    """Real-time deployment progress visualization."""

    def __init__(self, kernel: Any = None):
        super().__init__()
        self._kernel = kernel
        self._deploying = False
        self._start_time: Optional[float] = None
        self._refresh_timer = QTimer()
        self._refresh_timer.timeout.connect(self._update_display)

        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)

        # Overall progress
        overall_group = QGroupBox("Overall Progress")
        overall_layout = QVBoxLayout(overall_group)

        progress_row = QHBoxLayout()
        self._overall_bar = QProgressBar()
        self._overall_bar.setRange(0, 100)
        self._overall_bar.setValue(0)
        progress_row.addWidget(self._overall_bar, 1)

        self._percent_label = QLabel("0%")
        self._percent_label.setObjectName("heading")
        progress_row.addWidget(self._percent_label)

        overall_layout.addLayout(progress_row)

        # Time info
        time_row = QHBoxLayout()
        self._elapsed_label = QLabel("Elapsed: --")
        time_row.addWidget(self._elapsed_label)
        self._remaining_label = QLabel("Remaining: --")
        time_row.addWidget(self._remaining_label)
        self._phase_label = QLabel("Phase: --")
        self._phase_label.setObjectName("subheading")
        time_row.addWidget(self._phase_label)
        time_row.addStretch()
        overall_layout.addLayout(time_row)

        # Deployment summary
        summary_row = QHBoxLayout()
        self._total_label = QLabel("Total: 0")
        summary_row.addWidget(self._total_label)
        self._installed_label = QLabel("Installed: 0")
        self._installed_label.setStyleSheet("color: #a6e3a1;")
        summary_row.addWidget(self._installed_label)
        self._failed_label = QLabel("Failed: 0")
        self._failed_label.setStyleSheet("color: #f38ba8;")
        summary_row.addWidget(self._failed_label)
        self._skipped_label = QLabel("Skipped: 0")
        self._skipped_label.setStyleSheet("color: #f9e2af;")
        summary_row.addWidget(self._skipped_label)
        summary_row.addStretch()
        overall_layout.addLayout(summary_row)

        layout.addWidget(overall_group)

        # Active operations table
        ops_group = QGroupBox("Active Operations")
        ops_layout = QVBoxLayout(ops_group)
        self._ops_table = QTableWidget()
        self._ops_table.setColumnCount(7)
        self._ops_table.setHorizontalHeaderLabels([
            "Tool", "Phase", "Progress", "Elapsed", "Command", "Retries", "Status"
        ])
        self._ops_table.horizontalHeader().setStretchLastSection(True)
        self._ops_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self._ops_table.setSelectionBehavior(QTableWidget.SelectRows)
        self._ops_table.setEditTriggers(QTableWidget.NoEditTriggers)
        ops_layout.addWidget(self._ops_table)
        layout.addWidget(ops_group, 1)

        # Current command
        cmd_group = QGroupBox("Current Command")
        cmd_layout = QVBoxLayout(cmd_group)
        self._cmd_display = QTextEdit()
        self._cmd_display.setReadOnly(True)
        self._cmd_display.setMaximumHeight(60)
        cmd_layout.addWidget(self._cmd_display)
        layout.addWidget(cmd_group)

        # Operation log
        log_group = QGroupBox("Operation Log")
        log_layout = QVBoxLayout(log_group)
        self._log_list = QListWidget()
        log_layout.addWidget(self._log_list)
        layout.addWidget(log_group, 1)

        # Control buttons
        btn_row = QHBoxLayout()
        self._deploy_btn = QPushButton("Start Deployment")
        self._deploy_btn.setObjectName("primary")
        self._deploy_btn.clicked.connect(self.run_deployment)
        btn_row.addWidget(self._deploy_btn)

        self._cancel_btn = QPushButton("Cancel")
        self._cancel_btn.setObjectName("danger")
        self._cancel_btn.setEnabled(False)
        btn_row.addWidget(self._cancel_btn)

        btn_row.addStretch()
        layout.addLayout(btn_row)

    def run_deployment(self) -> None:
        """Start deployment."""
        if self._deploying:
            return
        self._deploying = True
        self._deploy_btn.setEnabled(False)
        self._cancel_btn.setEnabled(True)
        self._start_time = time.time()
        self._refresh_timer.start(1000)
        self._add_log("Deployment started")
        ui_state.start_deployment_timer()
        ui_state.phase = UIStatePhase.DEPLOYING

        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.ensure_future(self._do_deploy())
            else:
                loop.run_until_complete(self._do_deploy())
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(self._do_deploy())

    async def _do_deploy(self) -> None:
        """Execute deployment."""
        try:
            from src.modules.task_orchestrator import TaskOrchestrator
            orch = TaskOrchestrator()
            orch.on_progress(self._on_progress)

            task = await orch.run_deployment(
                tools=["ollama", "lm_studio", "open_webui"],
                models=[],
            )

            self._overall_bar.setValue(100)
            self._percent_label.setText("100%")
            self._add_log(f"Deployment completed: {task.progress.status.value}")
            ui_state.phase = UIStatePhase.COMPLETED
            ui_state.deployment_status = "Completed"
        except Exception as e:
            self._add_log(f"Deployment failed: {e}")
            ui_state.phase = UIStatePhase.FAILED
            ui_state.deployment_status = "Failed"
        finally:
            self._deploying = False
            self._deploy_btn.setEnabled(True)
            self._cancel_btn.setEnabled(False)
            self._refresh_timer.stop()

    def _on_progress(self, progress) -> None:
        """Handle progress updates - crash-safe."""
        try:
            pct = getattr(progress, 'progress_percent', 0)
            step = getattr(progress, 'current_step', '')
            status = getattr(progress, 'status', None)

            if hasattr(self, '_overall_bar') and self._overall_bar:
                self._overall_bar.setValue(int(pct))
            if hasattr(self, '_percent_label') and self._percent_label:
                self._percent_label.setText(f"{pct:.0f}%")
            if hasattr(self, '_phase_label') and self._phase_label:
                self._phase_label.setText(f"Phase: {step}")

            if status:
                self._add_log(f"[{status}] {step} ({pct:.0f}%)")
        except Exception as e:
            logger.warning(f"Progress update suppressed: {e}")

    def _update_display(self) -> None:
        """Update display from centralized UI state."""
        try:
            # Update elapsed time
            elapsed = ui_state.deployment_elapsed
            if hasattr(self, '_elapsed_label') and self._elapsed_label:
                self._elapsed_label.setText(f"Elapsed: {elapsed:.0f}s")

            # Update estimated remaining
            remaining = ui_state.estimated_remaining
            if hasattr(self, '_remaining_label') and self._remaining_label:
                if remaining > 0:
                    self._remaining_label.setText(f"Remaining: {remaining:.0f}s")
                else:
                    self._remaining_label.setText("Remaining: --")

            # Update phase
            if hasattr(self, '_phase_label') and self._phase_label:
                self._phase_label.setText(f"Phase: {ui_state.phase.value}")

            # Update deployment summary
            if hasattr(self, '_total_label') and self._total_label:
                self._total_label.setText(f"Total: {ui_state.tools_total}")
            if hasattr(self, '_installed_label') and self._installed_label:
                self._installed_label.setText(f"Installed: {ui_state.tools_installed}")
            if hasattr(self, '_failed_label') and self._failed_label:
                self._failed_label.setText(f"Failed: {ui_state.tools_failed}")
            if hasattr(self, '_skipped_label') and self._skipped_label:
                self._skipped_label.setText(f"Skipped: {ui_state.tools_skipped}")

            # Update active operations table
            if hasattr(self, '_ops_table') and self._ops_table:
                ops = ui_state.get_active_operations()
                self._ops_table.setRowCount(len(ops))
                for row, op in enumerate(ops):
                    self._ops_table.setItem(row, 0, QTableWidgetItem(op.tool_name))
                    self._ops_table.setItem(row, 1, QTableWidgetItem(op.phase))
                    progress_item = QTableWidgetItem(f"{op.progress_percent:.0f}%")
                    self._ops_table.setItem(row, 2, progress_item)
                    self._ops_table.setItem(row, 3, QTableWidgetItem(f"{op.elapsed_seconds:.0f}s"))
                    self._ops_table.setItem(row, 4, QTableWidgetItem(op.current_command[:40] if op.current_command else ""))
                    retry_text = f"{op.retry_count}/{op.max_retries}" if op.retry_count > 0 else ""
                    self._ops_table.setItem(row, 5, QTableWidgetItem(retry_text))
                    status_item = QTableWidgetItem(op.status)
                    if op.status == "failed":
                        status_item.setForeground(QColor("#f38ba8"))
                    elif op.status == "completed":
                        status_item.setForeground(QColor("#a6e3a1"))
                    self._ops_table.setItem(row, 6, status_item)

            # Update current command from first active operation
            if hasattr(self, '_cmd_display') and self._cmd_display:
                if ops:
                    self._cmd_display.setText(ops[0].current_command)
                else:
                    self._cmd_display.clear()
        except Exception as e:
            logger.warning(f"DeploymentProgress display update suppressed: {e}")

    def _add_log(self, text: str) -> None:
        """Add log entry."""
        item = QListWidgetItem(f"[{datetime.now().strftime('%H:%M:%S')}] {text}")
        self._log_list.insertItem(0, item)
        while self._log_list.count() > 100:
            self._log_list.takeItem(self._log_list.count() - 1)
