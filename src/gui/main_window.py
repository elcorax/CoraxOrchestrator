"""
Corax Orchestrator - Main Window.

Central application window with tabbed navigation to all panels.
Integrates with the runtime kernel and centralized UI state.
"""

from typing import Optional, Any
import os

from PySide6.QtWidgets import (
    QMainWindow, QTabWidget, QStatusBar, QLabel,
    QMenuBar, QMenu, QMessageBox, QApplication,
)
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QAction, QFont

from src.core.logging import get_logger
from src.gui.ui_state import ui_state, UIStatePhase
from src.gui.panels import (
    DashboardPanel,
    DeploymentProgressPanel,
    ToolSelectionPanel,
    DeploymentControlPanel,
    PermissionsPanel,
    ReportsViewerPanel,
    RuntimeMonitorPanel,
    ConsoleViewerPanel,
    SettingsPanel,
)

logger = get_logger(__name__)


class MainWindow(QMainWindow):
    """Corax Orchestrator main application window."""

    def __init__(self, kernel: Any = None):
        super().__init__()
        self._kernel = kernel
        self._status_timer = QTimer()
        self._status_timer.timeout.connect(self._update_status_bar)

        self._setup_window()
        self._setup_menu()
        self._setup_tabs()
        self._setup_status_bar()

        self._status_timer.start(2000)

    def _setup_window(self) -> None:
        """Configure the main window."""
        self.setWindowTitle("Corax Orchestrator - Internal Alpha")
        self.setMinimumSize(1280, 800)
        self.resize(1600, 1000)

        # Apply Corax dark theme stylesheet
        self.setStyleSheet("""
            QMainWindow {
                background-color: #1e1e2e;
            }
            QWidget {
                background-color: #1e1e2e;
                color: #cdd6f4;
                font-family: 'Segoe UI', 'Arial', sans-serif;
            }
            QGroupBox {
                border: 1px solid #313244;
                border-radius: 6px;
                margin-top: 12px;
                padding-top: 16px;
                font-weight: bold;
                color: #cdd6f4;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                subcontrol-position: top left;
                padding: 2px 8px;
                color: #89b4fa;
            }
            QPushButton {
                background-color: #313244;
                border: 1px solid #45475a;
                border-radius: 4px;
                padding: 6px 16px;
                color: #cdd6f4;
                min-height: 24px;
            }
            QPushButton:hover {
                background-color: #45475a;
                border-color: #585b70;
            }
            QPushButton:pressed {
                background-color: #585b70;
            }
            QPushButton#primary {
                background-color: #89b4fa;
                color: #1e1e2e;
                font-weight: bold;
            }
            QPushButton#primary:hover {
                background-color: #74c7ec;
            }
            QPushButton#danger {
                background-color: #f38ba8;
                color: #1e1e2e;
                font-weight: bold;
            }
            QPushButton#danger:hover {
                background-color: #eba0ac;
            }
            QTabWidget::pane {
                border: 1px solid #313244;
                background-color: #1e1e2e;
            }
            QTabBar::tab {
                background-color: #181825;
                color: #cdd6f4;
                padding: 8px 16px;
                border: 1px solid #313244;
                border-bottom: none;
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
                margin-right: 2px;
            }
            QTabBar::tab:selected {
                background-color: #1e1e2e;
                color: #89b4fa;
                border-bottom: 2px solid #89b4fa;
            }
            QTabBar::tab:hover {
                background-color: #313244;
            }
            QProgressBar {
                border: 1px solid #313244;
                border-radius: 4px;
                text-align: center;
                color: #cdd6f4;
                background-color: #181825;
            }
            QProgressBar::chunk {
                background-color: #89b4fa;
                border-radius: 3px;
            }
            QListWidget {
                border: 1px solid #313244;
                border-radius: 4px;
                background-color: #181825;
                alternate-background-color: #1e1e2e;
            }
            QListWidget::item:selected {
                background-color: #313244;
                color: #89b4fa;
            }
            QTreeWidget {
                border: 1px solid #313244;
                border-radius: 4px;
                background-color: #181825;
                alternate-background-color: #1e1e2e;
            }
            QTreeWidget::item:selected {
                background-color: #313244;
                color: #89b4fa;
            }
            QTableWidget {
                border: 1px solid #313244;
                border-radius: 4px;
                background-color: #181825;
                alternate-background-color: #1e1e2e;
                gridline-color: #313244;
            }
            QTableWidget::item:selected {
                background-color: #313244;
                color: #89b4fa;
            }
            QHeaderView::section {
                background-color: #181825;
                color: #cdd6f4;
                border: 1px solid #313244;
                padding: 4px;
            }
            QTextEdit {
                border: 1px solid #313244;
                border-radius: 4px;
                background-color: #181825;
                color: #cdd6f4;
            }
            QLineEdit {
                border: 1px solid #313244;
                border-radius: 4px;
                padding: 4px 8px;
                background-color: #181825;
                color: #cdd6f4;
            }
            QComboBox {
                border: 1px solid #313244;
                border-radius: 4px;
                padding: 4px 8px;
                background-color: #181825;
                color: #cdd6f4;
            }
            QComboBox::drop-down {
                border: none;
            }
            QComboBox QAbstractItemView {
                background-color: #181825;
                color: #cdd6f4;
                selection-background-color: #313244;
            }
            QCheckBox {
                spacing: 8px;
            }
            QCheckBox::indicator {
                width: 16px;
                height: 16px;
                border: 1px solid #45475a;
                border-radius: 3px;
                background-color: #181825;
            }
            QCheckBox::indicator:checked {
                background-color: #89b4fa;
                border-color: #89b4fa;
            }
            QRadioButton {
                spacing: 8px;
            }
            QRadioButton::indicator {
                width: 16px;
                height: 16px;
                border: 1px solid #45475a;
                border-radius: 8px;
                background-color: #181825;
            }
            QRadioButton::indicator:checked {
                background-color: #89b4fa;
                border-color: #89b4fa;
            }
            QSpinBox, QDoubleSpinBox {
                border: 1px solid #313244;
                border-radius: 4px;
                padding: 4px;
                background-color: #181825;
                color: #cdd6f4;
            }
            QStatusBar {
                background-color: #181825;
                color: #a6adc8;
                border-top: 1px solid #313244;
            }
            QMenuBar {
                background-color: #181825;
                color: #cdd6f4;
                border-bottom: 1px solid #313244;
            }
            QMenuBar::item:selected {
                background-color: #313244;
            }
            QMenu {
                background-color: #181825;
                color: #cdd6f4;
                border: 1px solid #313244;
            }
            QMenu::item:selected {
                background-color: #313244;
            }
            QScrollBar:vertical {
                background-color: #181825;
                width: 10px;
                border: none;
            }
            QScrollBar::handle:vertical {
                background-color: #45475a;
                border-radius: 5px;
                min-height: 20px;
            }
            QScrollBar::handle:vertical:hover {
                background-color: #585b70;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
            }
            QScrollBar:horizontal {
                background-color: #181825;
                height: 10px;
                border: none;
            }
            QScrollBar::handle:horizontal {
                background-color: #45475a;
                border-radius: 5px;
                min-width: 20px;
            }
            QScrollBar::handle:horizontal:hover {
                background-color: #585b70;
            }
            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
                width: 0px;
            }
            QSplitter::handle {
                background-color: #313244;
                width: 2px;
            }
            QLabel#heading {
                font-size: 16px;
                font-weight: bold;
                color: #cdd6f4;
            }
            QLabel#subheading {
                font-size: 12px;
                color: #a6adc8;
            }
            QLabel#status_ok {
                font-size: 14px;
                font-weight: bold;
                color: #a6e3a1;
            }
            QLabel#status_warn {
                font-size: 14px;
                font-weight: bold;
                color: #f9e2af;
            }
            QLabel#status_error {
                font-size: 14px;
                font-weight: bold;
                color: #f38ba8;
            }
        """)

    def _setup_menu(self) -> None:
        """Setup the menu bar."""
        menubar = self.menuBar()

        # File menu
        file_menu = menubar.addMenu("File")
        exit_action = QAction("Exit", self)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        # View menu
        view_menu = menubar.addMenu("View")
        for i, name in enumerate([
            "Dashboard", "Deployment Progress", "Tool Selection",
            "Deployment Control", "Permissions", "Reports",
            "Runtime Monitor", "Console", "Settings",
        ]):
            action = QAction(name, self)
            action.triggered.connect(lambda checked, idx=i: self._switch_to_tab(idx))
            view_menu.addAction(action)

        # Tools menu
        tools_menu = menubar.addMenu("Tools")
        scan_action = QAction("Run System Scan", self)
        scan_action.triggered.connect(self._run_scan)
        tools_menu.addAction(scan_action)

        diag_action = QAction("Run Diagnostics", self)
        diag_action.triggered.connect(self._run_diagnostics)
        tools_menu.addAction(diag_action)

        # Help menu
        help_menu = menubar.addMenu("Help")
        about_action = QAction("About Corax", self)
        about_action.triggered.connect(self._show_about)
        help_menu.addAction(about_action)

    def _setup_tabs(self) -> None:
        """Setup the tabbed panel layout."""
        self._tabs = QTabWidget()
        self._tabs.setTabPosition(QTabWidget.North)
        self._tabs.setDocumentMode(True)

        self._panels = {
            "dashboard": DashboardPanel(self._kernel),
            "deployment_progress": DeploymentProgressPanel(self._kernel),
            "tool_selection": ToolSelectionPanel(self._kernel),
            "deployment_control": DeploymentControlPanel(self._kernel),
            "permissions": PermissionsPanel(self._kernel),
            "reports": ReportsViewerPanel(self._kernel),
            "runtime_monitor": RuntimeMonitorPanel(self._kernel),
            "console_viewer": ConsoleViewerPanel(self._kernel),
            "settings": SettingsPanel(self._kernel),
        }

        self._tabs.addTab(self._panels["dashboard"], "📊 Dashboard")
        self._tabs.addTab(self._panels["deployment_progress"], "📈 Progress")
        self._tabs.addTab(self._panels["tool_selection"], "🔧 Tools")
        self._tabs.addTab(self._panels["deployment_control"], "🎮 Control")
        self._tabs.addTab(self._panels["permissions"], "🔒 Permissions")
        self._tabs.addTab(self._panels["reports"], "📋 Reports")
        self._tabs.addTab(self._panels["runtime_monitor"], "🖥 Monitor")
        self._tabs.addTab(self._panels["console_viewer"], "📜 Console")
        self._tabs.addTab(self._panels["settings"], "⚙ Settings")

        self.setCentralWidget(self._tabs)

    def _setup_status_bar(self) -> None:
        """Setup the status bar."""
        self._status_bar = QStatusBar()
        self.setStatusBar(self._status_bar)

        # Corax branding - always visible left side
        brand_font = QFont()
        brand_font.setPointSize(9)
        brand_font.setBold(True)
        self._brand_label = QLabel("🔷 Corax")
        self._brand_label.setFont(brand_font)
        self._brand_label.setStyleSheet("color: #89b4fa;")
        self._status_bar.addWidget(self._brand_label)

        self._status_bar.addWidget(QLabel("|"))

        self._phase_label = QLabel("Phase: Idle")
        self._status_bar.addWidget(self._phase_label)

        self._status_bar.addPermanentWidget(QLabel("|"))

        self._deploy_status = QLabel("Deployment: Not Started")
        self._status_bar.addPermanentWidget(self._deploy_status)

        self._status_bar.addPermanentWidget(QLabel("|"))

        self._health_status = QLabel("Health: Unknown")
        self._status_bar.addPermanentWidget(self._health_status)

        self._status_bar.addPermanentWidget(QLabel("|"))

        self._corax_tag = QLabel("CORAX LIMITED")
        self._corax_tag.setStyleSheet("color: #585b70; font-size: 9px;")
        self._status_bar.addPermanentWidget(self._corax_tag)

    def _update_status_bar(self) -> None:
        """Update status bar from centralized UI state."""
        try:
            if hasattr(self, '_phase_label') and self._phase_label:
                self._phase_label.setText(f"Phase: {ui_state.phase.value}")
            if hasattr(self, '_deploy_status') and self._deploy_status:
                self._deploy_status.setText(f"Deployment: {ui_state.deployment_status}")
            if hasattr(self, '_health_status') and self._health_status:
                self._health_status.setText(f"Health: {ui_state.system_health}")
        except Exception:
            pass

    def _switch_to_tab(self, index: int) -> None:
        """Switch to a specific tab."""
        if 0 <= index < self._tabs.count():
            self._tabs.setCurrentIndex(index)

    def _run_scan(self) -> None:
        """Run a system scan from the dashboard."""
        self._switch_to_tab(0)
        dashboard = self._panels.get("dashboard")
        if dashboard:
            dashboard.run_scan()

    def _run_diagnostics(self) -> None:
        """Run runtime diagnostics."""
        try:
            from src.runtime.diagnostics import run_diagnostics
            result = run_diagnostics()
            logger.info(f"Diagnostics completed: {result}")
        except Exception as e:
            logger.error(f"Diagnostics failed: {e}")

    def _show_about(self) -> None:
        """Show about dialog with Corax branding."""
        from PySide6.QtWidgets import QDialog, QVBoxLayout, QLabel, QPushButton
        from PySide6.QtGui import QPixmap, QFont
        from PySide6.QtCore import Qt
        
        dialog = QDialog(self)
        dialog.setWindowTitle("About Corax Orchestrator")
        dialog.setFixedSize(480, 420)
        dialog.setStyleSheet(self.styleSheet())
        
        layout = QVBoxLayout(dialog)
        layout.setSpacing(12)
        
        # Logo
        logo_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "..", "assets", "branding", "corax_raven.png")
        if os.path.exists(logo_path):
            pixmap = QPixmap(logo_path)
            if not pixmap.isNull():
                logo_label = QLabel()
                logo_label.setPixmap(pixmap.scaled(96, 96, Qt.KeepAspectRatio, Qt.SmoothTransformation))
                logo_label.setAlignment(Qt.AlignCenter)
                layout.addWidget(logo_label)
        
        # Title
        title = QLabel("Corax Orchestrator")
        title_font = QFont()
        title_font.setPointSize(18)
        title_font.setBold(True)
        title.setFont(title_font)
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("color: #89b4fa;")
        layout.addWidget(title)
        
        # Version
        version = QLabel("Internal Alpha · v0.1.0")
        version.setAlignment(Qt.AlignCenter)
        version.setStyleSheet("color: #a6adc8; font-size: 11px;")
        layout.addWidget(version)
        
        # Separator
        sep = QLabel("━" * 40)
        sep.setAlignment(Qt.AlignCenter)
        sep.setStyleSheet("color: #313244;")
        layout.addWidget(sep)
        
        # Description
        desc = QLabel(
            "An intelligent AI workstation deployment\n"
            "and orchestration system.\n\n"
            "Built with PySide6, asyncio, and\n"
            "a lot of determination."
        )
        desc.setAlignment(Qt.AlignCenter)
        desc.setStyleSheet("color: #cdd6f4; font-size: 12px;")
        layout.addWidget(desc)
        
        # Company info
        sep2 = QLabel("━" * 40)
        sep2.setAlignment(Qt.AlignCenter)
        sep2.setStyleSheet("color: #313244;")
        layout.addWidget(sep2)
        
        company = QLabel(
            '<a href="https://elcorax.com/" style="color: #89b4fa;">'
            'CORAX LIMITED</a>'
        )
        company.setAlignment(Qt.AlignCenter)
        company.setOpenExternalLinks(True)
        layout.addWidget(company)
        
        email = QLabel(
            '<a href="mailto:info@elcorax.com" style="color: #89b4fa;">'
            'info@elcorax.com</a>'
        )
        email.setAlignment(Qt.AlignCenter)
        email.setOpenExternalLinks(True)
        layout.addWidget(email)
        
        # Copyright
        copyright_label = QLabel("© 2026 CORAX LIMITED")
        copyright_label.setAlignment(Qt.AlignCenter)
        copyright_label.setStyleSheet("color: #585b70; font-size: 9px;")
        layout.addWidget(copyright_label)
        
        layout.addStretch()
        
        # Close button
        close_btn = QPushButton("Close")
        close_btn.setObjectName("primary")
        close_btn.clicked.connect(dialog.accept)
        layout.addWidget(close_btn)
        
        dialog.exec()

    def closeEvent(self, event) -> None:
        """Handle window close event."""
        self._status_timer.stop()
        event.accept()
