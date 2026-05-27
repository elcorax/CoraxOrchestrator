"""
Corax Orchestrator - Reports & Diagnostics Viewer.

Searchable reports with HTML, JSON, and Markdown rendering.
Deployment history, repair history, and runtime diagnostics.

Uses the centralized UIStateManager for real-time synchronization.
"""

import json
from typing import Optional, Any, Dict, List
from datetime import datetime
from pathlib import Path

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QGroupBox, QGridLayout, QFrame, QScrollArea,
    QTextEdit, QListWidget, QListWidgetItem, QComboBox,
    QLineEdit, QSplitter, QTabWidget, QTreeWidget,
    QTreeWidgetItem,
)
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont, QColor, QBrush

from src.core.logging import get_logger
from src.gui.ui_state import ui_state

logger = get_logger(__name__)


class ReportsViewerPanel(QWidget):
    """Reports and diagnostics viewer with multiple rendering modes."""

    def __init__(self, kernel: Any = None):
        super().__init__()
        self._kernel = kernel
        self._reports_dir = Path("data/reports")
        self._reports_dir.mkdir(parents=True, exist_ok=True)

        self._setup_ui()
        self._refresh_report_list()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)

        # Search bar
        search_row = QHBoxLayout()
        self._search_input = QLineEdit()
        self._search_input.setPlaceholderText("Search reports...")
        self._search_input.textChanged.connect(self._filter_reports)
        search_row.addWidget(self._search_input, 1)

        self._format_combo = QComboBox()
        self._format_combo.addItems(["All Formats", "JSON", "HTML", "Markdown"])
        self._format_combo.currentTextChanged.connect(self._filter_reports)
        search_row.addWidget(self._format_combo)

        refresh_btn = QPushButton("Refresh")
        refresh_btn.clicked.connect(self._refresh_report_list)
        search_row.addWidget(refresh_btn)

        layout.addLayout(search_row)

        # Splitter: report list + viewer
        splitter = QSplitter(Qt.Horizontal)

        # Report list
        list_widget = QWidget()
        list_layout = QVBoxLayout(list_widget)
        list_layout.setContentsMargins(0, 0, 0, 0)

        self._report_list = QListWidget()
        self._report_list.currentRowChanged.connect(self._load_report)
        list_layout.addWidget(self._report_list)

        splitter.addWidget(list_widget)

        # Report viewer
        viewer_widget = QWidget()
        viewer_layout = QVBoxLayout(viewer_widget)
        viewer_layout.setContentsMargins(0, 0, 0, 0)

        self._viewer_tabs = QTabWidget()

        # Raw text view
        self._text_view = QTextEdit()
        self._text_view.setReadOnly(True)
        self._viewer_tabs.addTab(self._text_view, "Raw")

        # Formatted view
        self._formatted_view = QTextEdit()
        self._formatted_view.setReadOnly(True)
        self._viewer_tabs.addTab(self._formatted_view, "Formatted")

        # Tree view
        self._tree_view = QTreeWidget()
        self._tree_view.setHeaderLabels(["Key", "Value"])
        self._viewer_tabs.addTab(self._tree_view, "Tree")

        viewer_layout.addWidget(self._viewer_tabs)

        splitter.addWidget(viewer_widget)
        splitter.setSizes([250, 750])

        layout.addWidget(splitter, 1)

        # History tabs at bottom
        history_tabs = QTabWidget()

        # Deployment history
        deploy_tab = QWidget()
        deploy_layout = QVBoxLayout(deploy_tab)
        self._deploy_history = QListWidget()
        deploy_layout.addWidget(self._deploy_history)
        history_tabs.addTab(deploy_tab, "Deployment History")

        # Repair history
        repair_tab = QWidget()
        repair_layout = QVBoxLayout(repair_tab)
        self._repair_history = QListWidget()
        repair_layout.addWidget(self._repair_history)
        history_tabs.addTab(repair_tab, "Repair History")

        # Diagnostics
        diag_tab = QWidget()
        diag_layout = QVBoxLayout(diag_tab)
        self._diag_view = QTextEdit()
        self._diag_view.setReadOnly(True)
        diag_layout.addWidget(self._diag_view)
        history_tabs.addTab(diag_tab, "Runtime Diagnostics")

        layout.addWidget(history_tabs)

    def _refresh_report_list(self) -> None:
        """Refresh the report list from disk."""
        self._report_list.clear()
        if not self._reports_dir.exists():
            return

        for report_file in sorted(
            self._reports_dir.glob("*.*"), key=lambda p: p.stat().st_mtime, reverse=True
        ):
            ext = report_file.suffix.lower()
            if ext in (".json", ".html", ".md", ".txt"):
                item = QListWidgetItem(f"{report_file.stem} ({ext})")
                item.setData(Qt.UserRole, str(report_file))
                self._report_list.addItem(item)

        # Also load deployment history from runtime bridge
        self._load_deployment_history_from_bridge()

    def _load_deployment_history_from_bridge(self) -> None:
        """Load deployment history from the runtime bridge persistence layer."""
        try:
            from src.runtime.bridge import runtime_bridge
            history = runtime_bridge.load_deployment_history(max_count=20)
            self._deploy_history.clear()
            for entry in history:
                ts = entry.get("_saved_at", entry.get("timestamp", "unknown"))
                status = entry.get("status", "unknown")
                tools_total = entry.get("tools_total", 0)
                tools_installed = entry.get("tools_installed", 0)
                tools_failed = entry.get("tools_failed", 0)
                text = (
                    f"[{ts[:19]}] {status.upper()} | "
                    f"Installed: {tools_installed}/{tools_total} | "
                    f"Failed: {tools_failed}"
                )
                item = QListWidgetItem(text)
                if status == "completed":
                    item.setForeground(QColor("#a6e3a1"))
                elif status == "failed":
                    item.setForeground(QColor("#f38ba8"))
                self._deploy_history.addItem(item)

            # Also load repair history from persistence
            from src.deployment.persistence import get_repair_history
            repair_entries = get_repair_history()
            self._repair_history.clear()
            for entry in repair_entries[-50:]:
                ts = entry.get("timestamp", "unknown")
                action = entry.get("action", "unknown")
                component = entry.get("component", "unknown")
                status = entry.get("status", "unknown")
                text = f"[{ts}] {component}: {action} ({status})"
                item = QListWidgetItem(text)
                if status == "completed":
                    item.setForeground(QColor("#a6e3a1"))
                elif status == "failed":
                    item.setForeground(QColor("#f38ba8"))
                self._repair_history.addItem(item)

            # Load runtime diagnostics report
            try:
                from src.runtime.diagnostics import RuntimeDiagnostics
                diag = RuntimeDiagnostics()
                report = diag.get_latest_report()
                if report:
                    self._diag_view.setPlainText(json.dumps(report.to_dict(), indent=2))
            except Exception:
                self._diag_view.setPlainText("No runtime diagnostics available")
        except Exception as e:
            self._deploy_history.addItem(f"Error loading history: {e}")

    def _filter_reports(self) -> None:
        """Filter reports by search text and format."""
        search = self._search_input.text().lower()
        fmt = self._format_combo.currentText()

        for i in range(self._report_list.count()):
            item = self._report_list.item(i)
            text = item.text().lower()
            visible = True

            if search and search not in text:
                visible = False

            if fmt != "All Formats":
                fmt_lower = fmt.lower()
                if fmt_lower not in text:
                    visible = False

            item.setHidden(not visible)

    def _load_report(self, row: int) -> None:
        """Load and display a report."""
        if row < 0:
            return

        item = self._report_list.item(row)
        if not item:
            return

        filepath = item.data(Qt.UserRole)
        if not filepath:
            return

        try:
            content = Path(filepath).read_text(encoding="utf-8")
            ext = Path(filepath).suffix.lower()

            # Raw view
            self._text_view.setPlainText(content)

            # Formatted view
            if ext == ".json":
                try:
                    parsed = json.loads(content)
                    formatted = json.dumps(parsed, indent=2)
                    self._formatted_view.setPlainText(formatted)
                    self._populate_tree(parsed)
                except json.JSONDecodeError:
                    self._formatted_view.setPlainText(content)
                    self._tree_view.clear()
            elif ext == ".html":
                self._formatted_view.setHtml(content)
                self._tree_view.clear()
            elif ext == ".md":
                self._formatted_view.setMarkdown(content)
                self._tree_view.clear()
            else:
                self._formatted_view.setPlainText(content)
                self._tree_view.clear()

        except Exception as e:
            self._text_view.setPlainText(f"Error loading report: {e}")
            self._formatted_view.clear()
            self._tree_view.clear()

    def _populate_tree(self, data: Dict, parent: Optional[QTreeWidgetItem] = None) -> None:
        """Populate tree view from JSON data."""
        if parent is None:
            self._tree_view.clear()
            parent = self._tree_view.invisibleRootItem()

        if isinstance(data, dict):
            for key, value in data.items():
                if isinstance(value, (dict, list)):
                    item = QTreeWidgetItem([str(key), ""])
                    parent.addChild(item)
                    self._populate_tree(value, item)
                else:
                    item = QTreeWidgetItem([str(key), str(value)])
                    parent.addChild(item)
        elif isinstance(data, list):
            for i, value in enumerate(data):
                if isinstance(value, (dict, list)):
                    item = QTreeWidgetItem([f"[{i}]", ""])
                    parent.addChild(item)
                    self._populate_tree(value, item)
                else:
                    item = QTreeWidgetItem([f"[{i}]", str(value)])
                    parent.addChild(item)
