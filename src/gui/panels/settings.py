"""
Corax Orchestrator - Settings Panel.

Deployment paths, retry settings, timeout settings,
cache settings, recovery settings, and autonomous mode settings.

Uses the centralized UIStateManager for real-time synchronization.
"""

from typing import Optional, Any, Dict
from pathlib import Path

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QGroupBox, QGridLayout, QCheckBox, QFrame, QScrollArea,
    QLineEdit, QSpinBox, QDoubleSpinBox, QFileDialog,
    QTabWidget, QFormLayout, QMessageBox,
)
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont, QColor

from src.core.logging import get_logger
from src.gui.ui_state import ui_state

logger = get_logger(__name__)


class SettingsPanel(QWidget):
    """Settings panel for deployment configuration."""

    def __init__(self, kernel: Any = None):
        super().__init__()
        self._kernel = kernel
        self._settings: Dict[str, Any] = {}
        self._load_settings()

        self._setup_ui()

    def _load_settings(self) -> None:
        """Load settings from config."""
        try:
            from src.core.config import config
            self._settings = config.get_all() if hasattr(config, 'get_all') else {}
        except Exception:
            self._settings = {}

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)

        tabs = QTabWidget()

        # ─── Deployment Paths ─────────────────────────────────────────────
        paths_tab = QWidget()
        paths_layout = QFormLayout(paths_tab)

        self._install_dir = QLineEdit(
            self._settings.get("deployment", {}).get("install_dir", "C:\\Corax")
        )
        browse_install = QPushButton("Browse...")
        browse_install.clicked.connect(
            lambda: self._browse_dir(self._install_dir)
        )
        install_row = QHBoxLayout()
        install_row.addWidget(self._install_dir)
        install_row.addWidget(browse_install)
        paths_layout.addRow("Install Directory:", install_row)

        self._cache_dir = QLineEdit(
            self._settings.get("deployment", {}).get("cache_dir", "C:\\Corax\\cache")
        )
        browse_cache = QPushButton("Browse...")
        browse_cache.clicked.connect(
            lambda: self._browse_dir(self._cache_dir)
        )
        cache_row = QHBoxLayout()
        cache_row.addWidget(self._cache_dir)
        cache_row.addWidget(browse_cache)
        paths_layout.addRow("Cache Directory:", cache_row)

        self._data_dir = QLineEdit(
            self._settings.get("deployment", {}).get("data_dir", "C:\\Corax\\data")
        )
        browse_data = QPushButton("Browse...")
        browse_data.clicked.connect(
            lambda: self._browse_dir(self._data_dir)
        )
        data_row = QHBoxLayout()
        data_row.addWidget(self._data_dir)
        data_row.addWidget(browse_data)
        paths_layout.addRow("Data Directory:", data_row)

        self._log_dir = QLineEdit(
            self._settings.get("deployment", {}).get("log_dir", "C:\\Corax\\logs")
        )
        browse_log = QPushButton("Browse...")
        browse_log.clicked.connect(
            lambda: self._browse_dir(self._log_dir)
        )
        log_row = QHBoxLayout()
        log_row.addWidget(self._log_dir)
        log_row.addWidget(browse_log)
        paths_layout.addRow("Log Directory:", log_row)

        tabs.addTab(paths_tab, "Paths")

        # ─── Retry Settings ───────────────────────────────────────────────
        retry_tab = QWidget()
        retry_layout = QFormLayout(retry_tab)

        self._max_retries = QSpinBox()
        self._max_retries.setRange(1, 20)
        self._max_retries.setValue(
            self._settings.get("retry", {}).get("max_retries", 3)
        )
        retry_layout.addRow("Max Retries:", self._max_retries)

        self._retry_delay = QSpinBox()
        self._retry_delay.setRange(1, 300)
        self._retry_delay.setSuffix(" seconds")
        self._retry_delay.setValue(
            self._settings.get("retry", {}).get("delay_seconds", 5)
        )
        retry_layout.addRow("Retry Delay:", self._retry_delay)

        self._retry_backoff = QDoubleSpinBox()
        self._retry_backoff.setRange(1.0, 10.0)
        self._retry_backoff.setSingleStep(0.5)
        self._retry_backoff.setValue(
            self._settings.get("retry", {}).get("backoff_multiplier", 2.0)
        )
        retry_layout.addRow("Backoff Multiplier:", self._retry_backoff)

        self._cooldown_period = QSpinBox()
        self._cooldown_period.setRange(0, 600)
        self._cooldown_period.setSuffix(" seconds")
        self._cooldown_period.setValue(
            self._settings.get("retry", {}).get("cooldown_period", 30)
        )
        retry_layout.addRow("Cooldown Period:", self._cooldown_period)

        tabs.addTab(retry_tab, "Retry")

        # ─── Timeout Settings ─────────────────────────────────────────────
        timeout_tab = QWidget()
        timeout_layout = QFormLayout(timeout_tab)

        self._install_timeout = QSpinBox()
        self._install_timeout.setRange(30, 3600)
        self._install_timeout.setSuffix(" seconds")
        self._install_timeout.setValue(
            self._settings.get("timeout", {}).get("install", 300)
        )
        timeout_layout.addRow("Install Timeout:", self._install_timeout)

        self._download_timeout = QSpinBox()
        self._download_timeout.setRange(30, 7200)
        self._download_timeout.setSuffix(" seconds")
        self._download_timeout.setValue(
            self._settings.get("timeout", {}).get("download", 600)
        )
        timeout_layout.addRow("Download Timeout:", self._download_timeout)

        self._model_pull_timeout = QSpinBox()
        self._model_pull_timeout.setRange(60, 86400)
        self._model_pull_timeout.setSuffix(" seconds")
        self._model_pull_timeout.setValue(
            self._settings.get("timeout", {}).get("model_pull", 3600)
        )
        timeout_layout.addRow("Model Pull Timeout:", self._model_pull_timeout)

        self._verification_timeout = QSpinBox()
        self._verification_timeout.setRange(10, 600)
        self._verification_timeout.setSuffix(" seconds")
        self._verification_timeout.setValue(
            self._settings.get("timeout", {}).get("verification", 60)
        )
        timeout_layout.addRow("Verification Timeout:", self._verification_timeout)

        tabs.addTab(timeout_tab, "Timeouts")

        # ─── Cache Settings ───────────────────────────────────────────────
        cache_tab = QWidget()
        cache_layout = QFormLayout(cache_tab)

        self._enable_cache = QCheckBox("Enable Installer Cache")
        self._enable_cache.setChecked(
            self._settings.get("cache", {}).get("enabled", True)
        )
        cache_layout.addRow("", self._enable_cache)

        self._cache_ttl = QSpinBox()
        self._cache_ttl.setRange(1, 365)
        self._cache_ttl.setSuffix(" days")
        self._cache_ttl.setValue(
            self._settings.get("cache", {}).get("ttl_days", 7)
        )
        cache_layout.addRow("Cache TTL:", self._cache_ttl)

        self._max_cache_size = QSpinBox()
        self._max_cache_size.setRange(1, 500)
        self._max_cache_size.setSuffix(" GB")
        self._max_cache_size.setValue(
            self._settings.get("cache", {}).get("max_size_gb", 50)
        )
        cache_layout.addRow("Max Cache Size:", self._max_cache_size)

        clear_cache_btn = QPushButton("Clear Cache Now")
        clear_cache_btn.clicked.connect(self._clear_cache)
        cache_layout.addRow("", clear_cache_btn)

        tabs.addTab(cache_tab, "Cache")

        # ─── Recovery Settings ────────────────────────────────────────────
        recovery_tab = QWidget()
        recovery_layout = QFormLayout(recovery_tab)

        self._enable_checkpoints = QCheckBox("Enable Checkpoint Persistence")
        self._enable_checkpoints.setChecked(
            self._settings.get("recovery", {}).get("checkpoints", True)
        )
        recovery_layout.addRow("", self._enable_checkpoints)

        self._enable_reboot_resume = QCheckBox("Enable Reboot Resume")
        self._enable_reboot_resume.setChecked(
            self._settings.get("recovery", {}).get("reboot_resume", True)
        )
        recovery_layout.addRow("", self._enable_reboot_resume)

        self._enable_path_repair = QCheckBox("Enable PATH Repair")
        self._enable_path_repair.setChecked(
            self._settings.get("recovery", {}).get("path_repair", True)
        )
        recovery_layout.addRow("", self._enable_path_repair)

        self._enable_venv_repair = QCheckBox("Enable Venv Repair")
        self._enable_venv_repair.setChecked(
            self._settings.get("recovery", {}).get("venv_repair", True)
        )
        recovery_layout.addRow("", self._enable_venv_repair)

        self._max_recovery_attempts = QSpinBox()
        self._max_recovery_attempts.setRange(1, 20)
        self._max_recovery_attempts.setValue(
            self._settings.get("recovery", {}).get("max_attempts", 5)
        )
        recovery_layout.addRow("Max Recovery Attempts:", self._max_recovery_attempts)

        tabs.addTab(recovery_tab, "Recovery")

        # ─── Autonomous Mode ──────────────────────────────────────────────
        auto_tab = QWidget()
        auto_layout = QFormLayout(auto_tab)

        self._auto_confirm = QCheckBox("Auto-confirm Installations")
        self._auto_confirm.setChecked(
            self._settings.get("autonomous", {}).get("auto_confirm", False)
        )
        auto_layout.addRow("", self._auto_confirm)

        self._auto_elevate = QCheckBox("Auto-elevate When Needed")
        self._auto_elevate.setChecked(
            self._settings.get("autonomous", {}).get("auto_elevate", False)
        )
        auto_layout.addRow("", self._auto_elevate)

        self._auto_retry = QCheckBox("Auto-retry Failed Operations")
        self._auto_retry.setChecked(
            self._settings.get("autonomous", {}).get("auto_retry", True)
        )
        auto_layout.addRow("", self._auto_retry)

        self._auto_recover = QCheckBox("Auto-recover From Failures")
        self._auto_recover.setChecked(
            self._settings.get("autonomous", {}).get("auto_recover", True)
        )
        auto_layout.addRow("", self._auto_recover)

        self._max_auto_retries = QSpinBox()
        self._max_auto_retries.setRange(1, 20)
        self._max_auto_retries.setValue(
            self._settings.get("autonomous", {}).get("max_retries", 5)
        )
        auto_layout.addRow("Max Auto Retries:", self._max_auto_retries)

        tabs.addTab(auto_tab, "Autonomous")

        layout.addWidget(tabs)

        # ─── Save Button ──────────────────────────────────────────────────
        save_btn = QPushButton("Save Settings")
        save_btn.setObjectName("primary")
        save_btn.clicked.connect(self._save_settings)
        layout.addWidget(save_btn)

    def _browse_dir(self, line_edit: QLineEdit) -> None:
        """Open directory browser."""
        dir_path = QFileDialog.getExistingDirectory(
            self, "Select Directory", line_edit.text()
        )
        if dir_path:
            line_edit.setText(dir_path)

    def _clear_cache(self) -> None:
        """Clear the installer cache."""
        cache_path = Path(self._cache_dir.text())
        if cache_path.exists():
            import shutil
            for item in cache_path.iterdir():
                if item.is_file():
                    item.unlink()
                elif item.is_dir():
                    shutil.rmtree(item)
            QMessageBox.information(self, "Cache Cleared", "Cache has been cleared.")
        else:
            QMessageBox.warning(self, "No Cache", "Cache directory does not exist.")

    def _save_settings(self) -> None:
        """Save settings to config."""
        try:
            from src.core.config import config

            settings = {
                "deployment": {
                    "install_dir": self._install_dir.text(),
                    "cache_dir": self._cache_dir.text(),
                    "data_dir": self._data_dir.text(),
                    "log_dir": self._log_dir.text(),
                },
                "retry": {
                    "max_retries": self._max_retries.value(),
                    "delay_seconds": self._retry_delay.value(),
                    "backoff_multiplier": self._retry_backoff.value(),
                    "cooldown_period": self._cooldown_period.value(),
                },
                "timeout": {
                    "install": self._install_timeout.value(),
                    "download": self._download_timeout.value(),
                    "model_pull": self._model_pull_timeout.value(),
                    "verification": self._verification_timeout.value(),
                },
                "cache": {
                    "enabled": self._enable_cache.isChecked(),
                    "ttl_days": self._cache_ttl.value(),
                    "max_size_gb": self._max_cache_size.value(),
                },
                "recovery": {
                    "checkpoints": self._enable_checkpoints.isChecked(),
                    "reboot_resume": self._enable_reboot_resume.isChecked(),
                    "path_repair": self._enable_path_repair.isChecked(),
                    "venv_repair": self._enable_venv_repair.isChecked(),
                    "max_attempts": self._max_recovery_attempts.value(),
                },
                "autonomous": {
                    "auto_confirm": self._auto_confirm.isChecked(),
                    "auto_elevate": self._auto_elevate.isChecked(),
                    "auto_retry": self._auto_retry.isChecked(),
                    "auto_recover": self._auto_recover.isChecked(),
                    "max_retries": self._max_auto_retries.value(),
                },
            }

            if hasattr(config, 'update'):
                config.update(settings)
            if hasattr(config, 'save'):
                config.save()

            QMessageBox.information(self, "Settings Saved", "Settings have been saved successfully.")
        except Exception as e:
            QMessageBox.warning(self, "Save Failed", f"Failed to save settings: {e}")
