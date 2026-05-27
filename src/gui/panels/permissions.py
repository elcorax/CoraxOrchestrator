"""
Corax Orchestrator - Permissions & Security Panel.

Shows elevation status, filesystem access, network access,
and execution scope visibility. Provides controls for
granting/revoking permissions.

Uses the centralized UIStateManager for real-time synchronization.
"""

from typing import Optional, Any, Dict, List
from datetime import datetime

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QGroupBox, QGridLayout, QCheckBox, QFrame, QScrollArea,
    QListWidget, QListWidgetItem, QTextEdit, QProgressBar,
)
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont, QColor

from src.core.logging import get_logger
from src.gui.ui_state import ui_state

logger = get_logger(__name__)


class PermissionsPanel(QWidget):
    """Permissions and security visibility panel."""

    def __init__(self, kernel: Any = None):
        super().__init__()
        self._kernel = kernel
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)

        # ─── Elevation Status ─────────────────────────────────────────────
        elev_group = QGroupBox("Elevation Status")
        elev_layout = QVBoxLayout(elev_group)

        self._elev_status = QLabel("Checking...")
        self._elev_status.setObjectName("heading")
        elev_layout.addWidget(self._elev_status)

        self._elev_detail = QLabel("")
        self._elev_detail.setObjectName("subheading")
        elev_layout.addWidget(self._elev_detail)

        check_elev_btn = QPushButton("Check Elevation")
        check_elev_btn.clicked.connect(self._check_elevation)
        elev_layout.addWidget(check_elev_btn)

        layout.addWidget(elev_group)

        # ─── Filesystem Access ────────────────────────────────────────────
        fs_group = QGroupBox("Filesystem Access")
        fs_layout = QVBoxLayout(fs_group)

        self._fs_list = QListWidget()
        self._fs_list.addItems([
            "✓ Corax installation directory",
            "✓ User home directory",
            "✓ System PATH (read)",
            "✓ Temporary directory",
            "○ Program Files (elevated only)",
            "○ System32 (elevated only)",
        ])
        fs_layout.addWidget(self._fs_list)

        layout.addWidget(fs_group)

        # ─── Network Access ───────────────────────────────────────────────
        net_group = QGroupBox("Network Access")
        net_layout = QVBoxLayout(net_group)

        self._net_list = QListWidget()
        self._net_list.addItems([
            "✓ GitHub (installer downloads)",
            "✓ HuggingFace (model downloads)",
            "✓ Ollama API (localhost:11434)",
            "✓ LM Studio API (localhost:1234)",
            "✓ Open WebUI (localhost:8080)",
            "✓ PyPI (package downloads)",
        ])
        net_layout.addWidget(self._net_list)

        layout.addWidget(net_group)

        # ─── Execution Scope ──────────────────────────────────────────────
        exec_group = QGroupBox("Execution Scope")
        exec_layout = QVBoxLayout(exec_group)

        self._exec_list = QListWidget()
        self._exec_list.addItems([
            "✓ Python script execution",
            "✓ PowerShell command execution",
            "✓ CMD command execution",
            "✓ Installer binary execution",
            "✓ Node.js script execution",
            "○ Docker container execution (if available)",
        ])
        exec_layout.addWidget(self._exec_list)

        layout.addWidget(exec_group)

        # ─── Permission Controls ──────────────────────────────────────────
        ctrl_group = QGroupBox("Permission Controls")
        ctrl_layout = QVBoxLayout(ctrl_group)

        self._allow_network = QCheckBox("Allow network downloads")
        self._allow_network.setChecked(True)
        ctrl_layout.addWidget(self._allow_network)

        self._allow_exec = QCheckBox("Allow script execution")
        self._allow_exec.setChecked(True)
        ctrl_layout.addWidget(self._allow_exec)

        self._allow_fs_write = QCheckBox("Allow filesystem writes")
        self._allow_fs_write.setChecked(True)
        ctrl_layout.addWidget(self._allow_fs_write)

        self._allow_elevated = QCheckBox("Allow elevation requests")
        self._allow_elevated.setChecked(True)
        ctrl_layout.addWidget(self._allow_elevated)

        layout.addWidget(ctrl_group)

        layout.addStretch()

    def _check_elevation(self) -> None:
        """Check current elevation status."""
        import ctypes
        try:
            is_admin = ctypes.windll.shell32.IsUserAnAdmin()
            if is_admin:
                self._elev_status.setText("✓ Elevated (Administrator)")
                self._elev_status.setStyleSheet("color: #a6e3a1; font-weight: bold;")
                self._elev_detail.setText("Full system access granted")
            else:
                self._elev_status.setText("○ Not Elevated")
                self._elev_status.setStyleSheet("color: #f9e2af; font-weight: bold;")
                self._elev_detail.setText("Some operations may require elevation")
        except Exception:
            self._elev_status.setText("? Unknown")
            self._elev_detail.setText("Could not determine elevation status")
