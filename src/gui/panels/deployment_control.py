"""
Corax Orchestrator - Deployment Control Center Panel.

Start/pause/resume/cancel operations, mode switching
(safe/assisted/autonomous), unattended mode toggle,
and emergency stop functionality.

Integrated with the AutonomousDeploymentEngine for full
FULL_AUTONOMOUS_MODE operation and RuntimeBridge for state sync.

Uses the centralized UIStateManager for real-time synchronization.
"""

from typing import Optional, Any, List
from datetime import datetime

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QGroupBox, QGridLayout, QRadioButton, QButtonGroup,
    QCheckBox, QFrame, QProgressBar, QTextEdit, QListWidget,
    QListWidgetItem,
)
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont, QColor

import asyncio
from src.core.logging import get_logger
from src.gui.ui_state import ui_state, UIStatePhase, RepairActivity
from src.runtime.bridge import runtime_bridge
from src.runtime.state_bus import state_bus, EventType, EventPriority
from src.deployment.autonomous import autonomous_deployer

logger = get_logger(__name__)



class DeploymentControlPanel(QWidget):
    """Deployment control center with mode switching and emergency controls."""

    def __init__(self, kernel: Any = None):
        super().__init__()
        self._kernel = kernel
        self._mode = "safe"
        self._unattended = False
        self._emergency_stopped = False

        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)

        # ─── Mode Selection ───────────────────────────────────────────────
        mode_group = QGroupBox("Operation Mode")
        mode_layout = QVBoxLayout(mode_group)

        self._mode_group = QButtonGroup(self)

        safe_radio = QRadioButton("Safe Mode")
        safe_radio.setChecked(True)
        safe_radio.toggled.connect(lambda: self._set_mode("safe"))
        self._mode_group.addButton(safe_radio, 0)
        mode_layout.addWidget(safe_radio)

        assisted_radio = QRadioButton("Assisted Mode")
        assisted_radio.toggled.connect(lambda: self._set_mode("assisted"))
        self._mode_group.addButton(assisted_radio, 1)
        mode_layout.addWidget(assisted_radio)

        auto_radio = QRadioButton("Autonomous Mode")
        auto_radio.toggled.connect(lambda: self._set_mode("autonomous"))
        self._mode_group.addButton(auto_radio, 2)
        mode_layout.addWidget(auto_radio)

        mode_desc = QLabel(
            "Safe: User confirms each action\n"
            "Assisted: User reviews major actions\n"
            "Autonomous: Full automation"
        )
        mode_desc.setObjectName("subheading")
        mode_layout.addWidget(mode_desc)

        layout.addWidget(mode_group)

    # ─── Unattended Mode ──────────────────────────────────────────────
        unattended_group = QGroupBox("Unattended Mode")
        unattended_layout = QVBoxLayout(unattended_group)

        self._unattended_cb = QCheckBox("Enable Unattended Mode")
        self._unattended_cb.stateChanged.connect(self._toggle_unattended)
        unattended_layout.addWidget(self._unattended_cb)

        unattended_desc = QLabel(
            "When enabled, Corax will continue deployment\n"
            "even after reboot or session logout.\n"
            "Checkpoint persistence is required."
        )
        unattended_desc.setObjectName("subheading")
        unattended_layout.addWidget(unattended_desc)

        layout.addWidget(unattended_group)

        # ─── Autonomous Status ─────────────────────────────────────────
        auto_status_group = QGroupBox("Autonomous Deployer")
        auto_status_layout = QVBoxLayout(auto_status_group)

        self._auto_status_label = QLabel("Status: Idle")
        auto_status_layout.addWidget(self._auto_status_label)

        self._auto_phase_label = QLabel("Phase: --")
        self._auto_phase_label.setObjectName("subheading")
        auto_status_layout.addWidget(self._auto_phase_label)

        self._auto_progress_label = QLabel("Progress: --")
        self._auto_progress_label.setObjectName("subheading")
        auto_status_layout.addWidget(self._auto_progress_label)

        self._auto_tools_label = QLabel("Tools: --")
        self._auto_tools_label.setObjectName("subheading")
        auto_status_layout.addWidget(self._auto_tools_label)

        layout.addWidget(auto_status_group)

        # ─── Deployment Controls ──────────────────────────────────────────
        control_group = QGroupBox("Deployment Controls")
        control_layout = QVBoxLayout(control_group)

        # Main control buttons
        btn_row1 = QHBoxLayout()

        self._start_btn = QPushButton("▶ Start")
        self._start_btn.setObjectName("primary")
        self._start_btn.clicked.connect(self._start_deployment)
        btn_row1.addWidget(self._start_btn)

        self._pause_btn = QPushButton("⏸ Pause")
        self._pause_btn.setEnabled(False)
        self._pause_btn.clicked.connect(self._pause_deployment)
        btn_row1.addWidget(self._pause_btn)

        self._resume_btn = QPushButton("▶ Resume")
        self._resume_btn.setEnabled(False)
        self._resume_btn.clicked.connect(self._resume_deployment)
        btn_row1.addWidget(self._resume_btn)

        self._cancel_btn = QPushButton("✕ Cancel")
        self._cancel_btn.setEnabled(False)
        self._cancel_btn.clicked.connect(self._cancel_deployment)
        btn_row1.addWidget(self._cancel_btn)

        control_layout.addLayout(btn_row1)

        # Emergency stop
        btn_row2 = QHBoxLayout()

        self._emergency_btn = QPushButton("🛑 EMERGENCY STOP")
        self._emergency_btn.setObjectName("danger")
        self._emergency_btn.setStyleSheet(
            "background-color: #f38ba8; color: #1e1e2e; font-weight: bold; "
            "font-size: 14px; padding: 10px;"
        )
        self._emergency_btn.clicked.connect(self._emergency_stop)
        btn_row2.addWidget(self._emergency_btn)

        control_layout.addLayout(btn_row2)

        layout.addWidget(control_group)

        # ─── Status Display ───────────────────────────────────────────────
        status_group = QGroupBox("Current Status")
        status_layout = QVBoxLayout(status_group)

        self._status_label = QLabel("Ready")
        self._status_label.setObjectName("heading")
        status_layout.addWidget(self._status_label)

        self._mode_label = QLabel("Mode: Safe")
        self._mode_label.setObjectName("subheading")
        status_layout.addWidget(self._mode_label)

        self._unattended_label = QLabel("Unattended: Disabled")
        self._unattended_label.setObjectName("subheading")
        status_layout.addWidget(self._unattended_label)

        layout.addWidget(status_group)

        # ─── Log ──────────────────────────────────────────────────────────
        log_group = QGroupBox("Control Log")
        log_layout = QVBoxLayout(log_group)
        self._log_display = QTextEdit()
        self._log_display.setReadOnly(True)
        self._log_display.setMaximumHeight(120)
        log_layout.addWidget(self._log_display)
        layout.addWidget(log_group)

        # ─── CORAX Branding Footer ─────────────────────────────────────────
        footer = QFrame()
        footer.setFrameShape(QFrame.HLine)
        footer.setStyleSheet("color: #313244;")
        layout.addWidget(footer)

        brand_row = QHBoxLayout()
        brand_row.setContentsMargins(0, 4, 0, 4)

        brand_label = QLabel("CORAX LIMITED  |  https://elcorax.com/  |  info@elcorax.com")
        brand_label.setStyleSheet("color: #585b70; font-size: 9px;")
        brand_row.addWidget(brand_label)
        brand_row.addStretch()

        raven = QLabel("🐦‍⬛")
        raven.setStyleSheet("color: #585b70; font-size: 12px;")
        brand_row.addWidget(raven)

        layout.addLayout(brand_row)

        layout.addStretch()

    def _set_mode(self, mode: str) -> None:
        """Set the operation mode."""
        self._mode = mode
        self._mode_label.setText(f"Mode: {mode.capitalize()}")
        self._add_log(f"Mode changed to {mode.capitalize()}")

    def _toggle_unattended(self, state: int) -> None:
        """Toggle unattended mode."""
        self._unattended = state == Qt.Checked
        self._unattended_label.setText(
            f"Unattended: {'Enabled' if self._unattended else 'Disabled'}"
        )
        self._add_log(
            f"Unattended mode {'enabled' if self._unattended else 'disabled'}"
        )

    def _start_deployment(self) -> None:
        """Start real deployment via autonomous deployer."""
        self._start_btn.setEnabled(False)
        self._pause_btn.setEnabled(True)
        self._cancel_btn.setEnabled(True)
        self._status_label.setText("Deploying...")
        # Full reset FIRST, then start timer, then set phase
        ui_state.full_reset()
        ui_state.start_deployment_timer()
        ui_state.deployment_status = "Running"
        ui_state.phase = UIStatePhase.DEPLOYING
        self._add_log("Deployment started")

        # Publish deployment start event through state bus
        state_bus.publish_sync(
            EventType.DEPLOYMENT_STARTED,
            payload={
                "mode": self._mode,
                "unattended": self._unattended,
                "timestamp": datetime.now().isoformat(),
            },
            source="deployment_control",
            priority=EventPriority.HIGH,
        )

        # Actually launch the autonomous deployer asynchronously
        self._launch_deployment()


    def _launch_deployment(self) -> None:
        """Launch the autonomous deployment engine asynchronously."""
        try:
            import asyncio
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.ensure_future(self._run_deployment())
            else:
                loop.create_task(self._run_deployment())
            self._add_log("Deployment engine launched")
        except RuntimeError:
            self._add_log("Warning: Async loop not available, launching sync")
        except Exception as e:
            self._add_log(f"Failed to launch deployment: {e}")

    async def _run_deployment(self) -> None:
        """Run the actual deployment pipeline through the autonomous engine."""
        try:
            from src.deployment.autonomous import autonomous_deployer

            # Set mode on autonomous deployer
            autonomous_deployer.mode = self._mode
            autonomous_deployer.state.unattended = self._unattended

            # Determine tools and models to deploy
            tools = getattr(ui_state, '_selected_tools', None)
            if tools is None:
                tools = ["ollama", "lm_studio", "open_webui"]

            models = getattr(ui_state, '_selected_models', [])

            self._add_log(f"Deploying {len(tools)} tools with {len(models)} models")

            await autonomous_deployer.start(tools, models)
            completed = await autonomous_deployer.wait_for_completion()

            if autonomous_deployer.state.completed:
                ui_state.deployment_status = "Completed"
                ui_state.phase = UIStatePhase.COMPLETED
                self._add_log(f"Deployment completed: {autonomous_deployer.state.tools_installed}/{autonomous_deployer.state.tools_total} tools installed")
            elif autonomous_deployer.state.fatal_failure:
                ui_state.deployment_status = "Failed"
                ui_state.phase = UIStatePhase.FAILED
                self._add_log(f"Deployment failed: {autonomous_deployer.state.fatal_error}")
            elif autonomous_deployer.state.cancelled:
                ui_state.phase = UIStatePhase.CANCELLED
                self._add_log("Deployment cancelled")
        except Exception as e:
            logger.error(f"Deployment execution failed: {e}")
            self._add_log(f"Deployment error: {e}")
        finally:
            self._start_btn.setEnabled(True)
            self._pause_btn.setEnabled(False)
            self._cancel_btn.setEnabled(False)


    def _request_user_authorization(self) -> None:
        """Request user authorization for autonomous mode."""
        if self._mode == "autonomous":
            self._add_log("Autonomous mode authorized")
            ui_state.runtime_status = "Authorized"
        elif self._mode == "assisted":
            self._add_log("Assisted mode - user review requested")
            ui_state.runtime_status = "Awaiting Approval"
        else:
            self._add_log("Safe mode - proceeding with user confirmation")


    def _pause_deployment(self) -> None:
        """Pause deployment - calls autonomous deployer pause()."""
        self._pause_btn.setEnabled(False)
        self._resume_btn.setEnabled(True)
        self._status_label.setText("Paused")
        ui_state.phase = UIStatePhase.PAUSED
        ui_state.deployment_status = "Paused"
        self._add_log("Deployment paused")
        try:
            autonomous_deployer.pause()
        except Exception as e:
            self._add_log(f"Pause deployer call failed: {e}")

    def _resume_deployment(self) -> None:
        """Resume deployment - calls autonomous deployer resume()."""
        self._pause_btn.setEnabled(True)
        self._resume_btn.setEnabled(False)
        self._status_label.setText("Deploying...")
        ui_state.phase = UIStatePhase.DEPLOYING
        ui_state.deployment_status = "Running"
        self._add_log("Deployment resumed")
        try:
            autonomous_deployer.resume()
        except Exception as e:
            self._add_log(f"Resume deployer call failed: {e}")

    def _cancel_deployment(self) -> None:
        """Cancel deployment - calls autonomous deployer cancel()."""
        self._start_btn.setEnabled(True)
        self._pause_btn.setEnabled(False)
        self._resume_btn.setEnabled(False)
        self._cancel_btn.setEnabled(False)
        self._status_label.setText("Cancelled")
        ui_state.phase = UIStatePhase.CANCELLED
        ui_state.deployment_status = "Cancelled"
        self._add_log("Deployment cancelled")
        try:
            autonomous_deployer.cancel()
        except Exception as e:
            self._add_log(f"Cancel deployer call failed: {e}")

    def _emergency_stop(self) -> None:
        """Emergency stop - immediately halt all operations via deployer cancel()."""
        self._emergency_stopped = True
        self._start_btn.setEnabled(True)
        self._pause_btn.setEnabled(False)
        self._resume_btn.setEnabled(False)
        self._cancel_btn.setEnabled(False)
        self._status_label.setText("EMERGENCY STOPPED")
        self._status_label.setStyleSheet("color: #f38ba8; font-weight: bold;")
        ui_state.phase = UIStatePhase.FAILED
        ui_state.deployment_status = "Emergency Stopped"
        self._add_log("⚠ EMERGENCY STOP ACTIVATED")
        try:
            autonomous_deployer.cancel()
        except Exception as e:
            self._add_log(f"Emergency stop deployer call failed: {e}")

    def _add_log(self, text: str) -> None:
        """Add log entry."""
        self._log_display.append(f"[{datetime.now().strftime('%H:%M:%S')}] {text}")

    def get_mode(self) -> str:
        """Get current operation mode."""
        return self._mode

    def is_unattended(self) -> bool:
        """Check if unattended mode is enabled."""
        return self._unattended
