"""
Corax Orchestrator - Application Entry Point.

Initializes the PySide6 application, runtime kernel,
and main window. Provides async event loop integration
and RuntimeBridge convergence for live state synchronization.

Convergence Flow:
1. Initialize Qt → Kernel → Bridge → Start bridge sync loop
2. Push kernel state → Bridge → UIStateManager → All panels
3. Live updates flow from Kernel/Bridge → UIStateManager → GUI
"""

import sys
import asyncio
from typing import Optional, Any

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt, QTimer

from src.core.logging import get_logger
from src.gui.main_window import MainWindow
from src.gui.ui_state import ui_state, UIStatePhase
from src.runtime.bridge import runtime_bridge
from src.runtime.state_bus import state_bus, EventType, EventPriority


logger = get_logger(__name__)


class CoraxApplication:
    """
    Corax GUI Application.

    Manages the PySide6 application lifecycle, runtime kernel
    initialization, RuntimeBridge convergence, and async event
    loop integration. All GUI panels receive live state updates
    through the bridge → UIStateManager pipeline.
    """

    def __init__(self, kernel: Any = None):
        self._kernel = kernel
        self._app: Optional[QApplication] = None
        self._window: Optional[MainWindow] = None
        self._async_loop: Optional[asyncio.AbstractEventLoop] = None
        self._convergence_started = False
        self._bridge_timer: Optional[QTimer] = None

        # Wire bridge to UI state
        self._wire_bridge_to_ui()

    def _wire_bridge_to_ui(self) -> None:
        """Wire RuntimeBridge state changes to UIStateManager notifications."""
        def on_bridge_update():
            # Bridge has new data - trigger UI repaint
            pass  # The bridge directly updates UIStateManager now
        runtime_bridge.register_ui_callback(on_bridge_update)

    def initialize(self) -> bool:
        """Initialize the application. Returns True on success."""
        try:
            # Create Qt application
            self._app = QApplication(sys.argv)
            self._app.setApplicationName("Corax Orchestrator")
            self._app.setApplicationVersion("0.1.0-alpha")
            self._app.setOrganizationName("Corax")

            # Set app attributes
            self._app.setAttribute(Qt.AA_UseHighDpiPixmaps, True)

            # Create async event loop
            try:
                self._async_loop = asyncio.get_event_loop()
            except RuntimeError:
                self._async_loop = asyncio.new_event_loop()
                asyncio.set_event_loop(self._async_loop)

            # Initialize runtime kernel if not provided
            if self._kernel is None:
                self._kernel = self._init_kernel()

            # Update UI state
            ui_state.runtime_status = "Starting"
            ui_state.system_health = "Initializing"

            # Create main window
            self._window = MainWindow(self._kernel)
            self._window.show()

            # Update UI state
            ui_state.runtime_status = "Ready"
            ui_state.system_health = "OK"

            logger.info("Corax GUI initialized successfully")
            return True

        except Exception as e:
            logger.error(f"Failed to initialize Corax GUI: {e}")
            return False

    def start_convergence(self) -> None:
        """
        Start the kernel → bridge → GUI convergence pipeline.

        This kicks off:
        1. Kernel startup lifecycle (if not already started)
        2. Bridge background sync loop
        3. Live timer for pulling bridge state → UIStateManager
        """
        if self._convergence_started:
            return
        self._convergence_started = True

        # Start RuntimeStateBus for converged event propagation
        try:
            state_bus.start()
            logger.info("RuntimeStateBus convergence started")
        except Exception as e:
            logger.warning(f"RuntimeStateBus start failed: {e}")

        # Start the kernel if available
        if self._kernel:
            try:
                from src.runtime.kernel import CoraxRuntimeKernel
                if isinstance(self._kernel, CoraxRuntimeKernel):
                    # Start kernel lifecycle
                    kernel_result = self._kernel.start()
                    if kernel_result.success:
                        logger.info("Kernel convergence completed")
                        runtime_bridge.push_health_status("system", "OK")

                        # Wire autonomous deployer
                        self._wire_autonomous_deployer()

                        # Wire deployment orchestrator from kernel
                        if self._kernel.deployment_engine:
                            runtime_bridge.bind_deployment_orchestrator(
                                self._kernel.deployment_engine
                            )
                    else:
                        logger.warning(
                            "Kernel startup had issues",
                            errors=kernel_result.errors,
                            warnings=kernel_result.warnings,
                        )
            except Exception as e:
                logger.warning(f"Kernel convergence failed: {e}")

        # Start bridge sync timer in Qt event loop
        if self._app:
            self._bridge_timer = QTimer()
            self._bridge_timer.timeout.connect(self._sync_bridge_to_ui)
            self._bridge_timer.start(200)  # 5 Hz sync rate for smooth UI updates
            logger.info("Bridge sync timer started at 5Hz")

        # Start async bridge loop
        if self._async_loop and self._async_loop.is_running():
            try:
                asyncio.ensure_future(runtime_bridge.start_bridge_loop())
            except Exception:
                pass
        elif self._async_loop and not self._async_loop.is_closed():
            try:
                self._async_loop.create_task(runtime_bridge.start_bridge_loop())
            except Exception:
                pass

    def _wire_autonomous_deployer(self) -> None:
        """Wire the autonomous deployment engine to kernel components."""
        try:
            from src.deployment.autonomous import autonomous_deployer

            # Connect to kernel components
            if self._kernel:
                if self._kernel.deployment_engine:
                    autonomous_deployer.set_orchestrator(
                        self._kernel.deployment_engine
                    )
                if self._kernel.execution_engine:
                    autonomous_deployer.set_executor(
                        self._kernel.execution_engine
                    )

            logger.info("Autonomous deployer wired to kernel")
        except Exception as e:
            logger.warning(f"Failed to wire autonomous deployer: {e}")

    def _sync_bridge_to_ui(self) -> None:
        """Sync bridge state to UI state manager (called from Qt timer)."""
        try:
            snapshot = runtime_bridge.get_snapshot()

            if not snapshot:
                return

            # Sync deployment summary
            dep = snapshot.get("deployment", {})
            ui_state.set_deployment_summary(
                total=dep.get("total", ui_state.tools_total),
                installed=dep.get("installed", ui_state.tools_installed),
                failed=dep.get("failed", ui_state.tools_failed),
                skipped=dep.get("skipped", ui_state.tools_skipped),
            )

            # Sync health
            health = snapshot.get("health", {})
            if "system" in health:
                ui_state.system_health = health["system"].get("status", ui_state.system_health)

            # Sync kernel state
            kernel_state = snapshot.get("kernel_state", {})
            if kernel_state:
                if kernel_state.get("success"):
                    ui_state.runtime_status = "Ready"
                else:
                    ui_state.runtime_status = "Error"

            # Sync recovery activities
            for activity in snapshot.get("recovery_activities", []):
                ui_state.add_repair_activity(
                    component=activity.get("component", ""),
                    action=activity.get("action", ""),
                    status=activity.get("status", "running"),
                    message=activity.get("message", ""),
                )

            # Sync retry queue
            for retry in snapshot.get("retry_queue", []):
                ui_state.add_to_retry_queue(
                    tool_name=retry.get("tool_name", ""),
                    retry_count=retry.get("retry_count", 0),
                    max_retries=retry.get("max_retries", 3),
                    last_error=retry.get("last_error", ""),
                    cooldown_seconds=retry.get("cooldown_seconds", 5),
                )
        except Exception:
            pass

    def _init_kernel(self) -> Any:
        """Initialize the runtime kernel."""
        try:
            from src.runtime.kernel import CoraxRuntimeKernel
            kernel = CoraxRuntimeKernel()
            return kernel
        except Exception as e:
            logger.warning(f"Runtime kernel initialization failed: {e}")
            return None

    def run(self) -> int:
        """Run the application main loop. Returns exit code."""
        if not self._app:
            logger.error("Application not initialized")
            return 1

        # Setup async timer to process asyncio events
        async_timer = QTimer()
        async_timer.timeout.connect(self._process_async_events)
        async_timer.start(50)  # 20 fps for async processing

        try:
            # Run Qt event loop
            exit_code = self._app.exec()
            logger.info(f"Corax GUI exited with code {exit_code}")
            return exit_code
        except Exception as e:
            logger.error(f"Error in GUI main loop: {e}")
            return 1
        finally:
            async_timer.stop()
            self._convergence_started = False
            runtime_bridge.stop_bridge()
            if self._bridge_timer:
                self._bridge_timer.stop()
            if self._async_loop and not self._async_loop.is_closed():
                try:
                    # Cancel pending tasks
                    for task in asyncio.all_tasks(self._async_loop):
                        task.cancel()
                except Exception:
                    pass
                self._async_loop.close()

    def _process_async_events(self) -> None:
        """Process pending async events safely."""
        if self._async_loop and not self._async_loop.is_closed():
            try:
                if self._async_loop.is_running():
                    self._async_loop.call_soon(lambda: None)
                elif not self._async_loop.is_running():
                    self._async_loop.call_soon(lambda: None)
                    self._async_loop.stop()
                    self._async_loop.run_forever()
            except Exception:
                pass

    def shutdown(self) -> None:
        """Shutdown the application gracefully."""
        logger.info("Shutting down Corax GUI...")
        ui_state.runtime_status = "Shutting Down"

        if self._window:
            self._window.close()

        if self._kernel:
            try:
                if hasattr(self._kernel, 'shutdown'):
                    self._kernel.shutdown()
            except Exception as e:
                logger.warning(f"Kernel shutdown error: {e}")

        # Stop RuntimeStateBus
        try:
            state_bus.stop()
        except Exception:
            pass

        self._convergence_started = False
        ui_state.runtime_status = "Stopped"
        logger.info("Corax GUI shutdown complete")


    @property
    def window(self) -> Optional[MainWindow]:
        """Get the main window."""
        return self._window

    @property
    def kernel(self) -> Any:
        """Get the runtime kernel."""
        return self._kernel
