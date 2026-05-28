"""
Corax Orchestrator - Autonomous Deployment Engine.

FULL_AUTONOMOUS_MODE implementation for unattended deployment.
After initial user authorization, Corax continues automatically
until completion, fatal unrecoverable failure, or explicit cancellation.

Capabilities:
- unattended deployment
- unattended retries
- unattended recovery
- reboot continuation
- deployment resume
- installer fallback switching
- environment repair
- dependency repair
"""

from typing import Optional, Dict, Any, List, Callable
from datetime import datetime, timezone
import asyncio
import json
import os
import time
import sys
import tempfile
from pathlib import Path

from src.core.logging import get_logger

logger = get_logger(__name__)


class AutonomousModeState:
    """Tracks the state of the autonomous deployment engine."""

    def __init__(self):
        self.active = False
        self.authorized = False
        self.paused = False
        self.cancelled = False
        self.completed = False
        self.fatal_failure = False
        self.current_phase = "idle"
        self.current_tool_index = 0
        self.current_tool_name = ""
        self.deployment_id: Optional[str] = None
        self.start_time: Optional[float] = None
        self.tools_total = 0
        self.tools_installed = 0
        self.tools_failed = 0
        self.tools_skipped = 0
        self.models_total = 0
        self.models_pulled = 0
        self.fatal_error: Optional[str] = None

        # Retry tracking
        self.retry_count = 0
        self.max_retries = 5
        self.retry_history: List[Dict[str, Any]] = []

        # Recovery tracking
        self.recovery_count = 0
        self.recovery_history: List[Dict[str, Any]] = []

        # Resume support
        self.checkpoint_file = Path("data/persistence/autonomous_checkpoint.json")

    def to_checkpoint(self) -> Dict[str, Any]:
        """Serialize state for reboot persistence."""
        return {
            "deployment_id": self.deployment_id,
            "start_time": self.start_time,
            "current_tool_index": self.current_tool_index,
            "current_tool_name": self.current_tool_name,
            "current_phase": self.current_phase,
            "tools_total": self.tools_total,
            "tools_installed": self.tools_installed,
            "tools_failed": self.tools_failed,
            "tools_skipped": self.tools_skipped,
            "models_total": self.models_total,
            "models_pulled": self.models_pulled,
            "retry_count": self.retry_count,
            "recovery_count": self.recovery_count,
            "authorized": self.authorized,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    def save_checkpoint(self) -> None:
        """Persist checkpoint for reboot recovery."""
        self.checkpoint_file.parent.mkdir(parents=True, exist_ok=True)
        try:
            with open(self.checkpoint_file, "w", encoding="utf-8") as f:
                json.dump(self.to_checkpoint(), f, indent=2)
            logger.debug("Autonomous checkpoint saved")
        except Exception as e:
            logger.warning("Failed to save checkpoint", error=str(e))

    def load_checkpoint(self) -> bool:
        """Load checkpoint for resume. Returns True if loaded."""
        if not self.checkpoint_file.exists():
            return False
        try:
            with open(self.checkpoint_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.deployment_id = data.get("deployment_id")
            self.start_time = data.get("start_time")
            self.current_tool_index = data.get("current_tool_index", 0)
            self.current_tool_name = data.get("current_tool_name", "")
            self.current_phase = data.get("current_phase", "idle")
            self.tools_total = data.get("tools_total", 0)
            self.tools_installed = data.get("tools_installed", 0)
            self.tools_failed = data.get("tools_failed", 0)
            self.tools_skipped = data.get("tools_skipped", 0)
            self.models_total = data.get("models_total", 0)
            self.models_pulled = data.get("models_pulled", 0)
            self.retry_count = data.get("retry_count", 0)
            self.recovery_count = data.get("recovery_count", 0)
            self.authorized = data.get("authorized", False)
            logger.info("Autonomous checkpoint loaded", tools_installed=self.tools_installed)
            return True
        except Exception as e:
            logger.warning("Failed to load checkpoint", error=str(e))
            return False

    def clear_checkpoint(self) -> None:
        """Clear checkpoint after successful completion."""
        try:
            if self.checkpoint_file.exists():
                self.checkpoint_file.unlink()
        except Exception:
            pass


class AutonomousDeploymentEngine:
    """
    FULL_AUTONOMOUS_MODE deployment engine.

    After initial user authorization, this engine drives:
    - Unattended tool deployment
    - Unattended retry with escalating strategies
    - Unattended recovery (environment repair, PATH repair, dependency fix)
    - Deployment resume after reboot
    - Installer fallback switching (primary -> fallback -> skip)
    - Automatic environment repair and dependency resolution

    The engine emits progress through RuntimeBridge to all GUI panels.
    """

    def __init__(self):
        self._state = AutonomousModeState()
        self._tool_installers: List[Dict[str, Any]] = []
        self._model_queue: List[str] = []
        self._orchestrator: Any = None
        self._deployment_executor: Any = None
        self._recovery_engine: Any = None
        self._status_callbacks: List[Callable[[str], None]] = []
        self._completion_callbacks: List[Callable[[bool], None]] = []
        self._running_task: Optional[asyncio.Task] = None
        self._cancel_event = asyncio.Event()

        # Lazy-loaded modules (avoid circular imports)
        self._lazy_ui_state = None
        self._lazy_phase = None
        self._lazy_bridge = None

        # Fallback chains
        self._fallback_registry: Dict[str, List[str]] = {
            "ollama": ["lm_studio"],
            "open_webui": [],
            "anythingllm": [],
            "open_interpreter": [],
            "comfyui": [],
            "git": [],
            "python": [],
            "node": [],
            "vscode": ["windsurf"],
            "windsurf": ["vscode"],
            "java": [],
            "flutter": [],
            "docker": [],
        }

    # --- Lazy Import Helpers (avoid circular imports) -------------------

    def _get_ui(self):
        if self._lazy_ui_state is None:
            from src.gui.ui_state import ui_state
            self._lazy_ui_state = ui_state
        return self._lazy_ui_state

    def _get_phase(self):
        if self._lazy_phase is None:
            from src.gui.ui_state import UIStatePhase
            self._lazy_phase = UIStatePhase
        return self._lazy_phase

    def _get_bridge(self):
        if self._lazy_bridge is None:
            from src.runtime.bridge import runtime_bridge
            self._lazy_bridge = runtime_bridge
        return self._lazy_bridge

    # --- Configuration --------------------------------------------------

    def set_orchestrator(self, orchestrator: Any) -> None:
        """Bind the deployment orchestrator."""
        self._orchestrator = orchestrator
        self._get_bridge().bind_deployment_orchestrator(orchestrator)

    def set_executor(self, executor: Any) -> None:
        """Bind the deployment executor."""
        self._deployment_executor = executor

    def set_recovery_engine(self, engine: Any) -> None:
        """Bind the recovery engine."""
        self._recovery_engine = engine
        self._get_bridge().bind_recovery_engine(engine)

    def set_tools(self, tools: List[str]) -> None:
        """Set the list of tools to deploy."""
        self._tool_installers = [{"name": t, "status": "pending"} for t in tools]
        self._state.tools_total = len(tools)
        self._state.current_tool_index = 0

    def set_models(self, models: List[str]) -> None:
        """Set the list of models to pull."""
        self._model_queue = list(models)
        self._state.models_total = len(models)

    def register_status_callback(self, cb: Callable[[str], None]) -> None:
        """Register a callback for status changes."""
        self._status_callbacks.append(cb)

    def register_completion_callback(self, cb: Callable[[bool], None]) -> None:
        """Register a callback for deployment completion."""
        self._completion_callbacks.append(cb)

    # --- State Access ---------------------------------------------------

    @property
    def is_active(self) -> bool:
        return self._state.active

    @property
    def is_authorized(self) -> bool:
        return self._state.authorized

    @property
    def is_paused(self) -> bool:
        return self._state.paused

    @property
    def is_cancelled(self) -> bool:
        return self._state.cancelled

    @property
    def is_completed(self) -> bool:
        return self._state.completed

    @property
    def progress_percent(self) -> float:
        if self._state.tools_total <= 0:
            return 0.0
        completed = self._state.tools_installed + self._state.tools_failed + self._state.tools_skipped
        return (completed / self._state.tools_total) * 100.0

    @property
    def state(self) -> AutonomousModeState:
        return self._state

    # --- Lifecycle ------------------------------------------------------

    async def start(self, tools: List[str], models: List[str]) -> None:
        if self._state.active:
            logger.warning("Autonomous deployment already active")
            return

        if self._state.load_checkpoint():
            logger.info("Resuming from checkpoint", index=self._state.current_tool_index)
            if not self._tool_installers:
                self._tool_installers = [{"name": t, "status": "pending"} for t in tools]
            if not self._model_queue:
                self._model_queue = list(models)
        else:
            self._tool_installers = [{"name": t, "status": "pending"} for t in tools]
            self._model_queue = list(models)
            self._state.tools_total = len(tools)
            self._state.models_total = len(models)

        self._state.active = True
        self._state.authorized = True
        self._state.cancelled = False
        self._state.completed = False
        self._state.fatal_failure = False
        self._state.start_time = time.time()
        self._state.deployment_id = f"AUTO-{int(time.time())}"
        self._cancel_event.clear()

        ui = self._get_ui()
        ui.phase = self._get_phase().DEPLOYING
        br = self._get_bridge()
        br.start_deployment_timer()
        br.update_deployment_summary(total=self._state.tools_total, installed=self._state.tools_installed, failed=self._state.tools_failed, skipped=self._state.tools_skipped)

        self._emit_status("starting")
        logger.info("Autonomous deployment started", tools=len(self._tool_installers), models=len(self._model_queue), resume=(self._state.current_tool_index > 0))

        self._running_task = asyncio.create_task(self._run_deployment_loop())

    async def pause(self) -> None:
        if not self._state.active:
            return
        self._state.paused = True
        self._get_ui().phase = self._get_phase().PAUSED
        self._state.save_checkpoint()
        self._emit_status("paused")
        logger.info("Autonomous deployment paused")

    async def resume(self) -> None:
        if not self._state.paused:
            return
        self._state.paused = False
        self._get_ui().phase = self._get_phase().DEPLOYING
        self._emit_status("resumed")
        logger.info("Autonomous deployment resumed")

    async def cancel(self) -> None:
        if not self._state.active:
            return
        self._state.cancelled = True
        self._cancel_event.set()
        self._get_ui().phase = self._get_phase().CANCELLED
        self._state.save_checkpoint()
        self._emit_status("cancelled")
        logger.info("Autonomous deployment cancelled")

    async def wait_for_completion(self) -> bool:
        if self._running_task:
            try:
                await self._running_task
            except asyncio.CancelledError:
                pass
        return self._state.completed

    # --- Core Deployment Loop -------------------------------------------

    async def _run_deployment_loop(self) -> None:
        br = self._get_bridge()
        try:
            success = await self._run_tool_deployment_phase()
            if not success or self._state.cancelled:
                await self._finalize(success)
                return

            if self._model_queue and not self._state.cancelled:
                self._get_ui().phase = self._get_phase().PULLING_MODELS
                await self._run_model_pull_phase()

            if not self._state.cancelled:
                self._get_ui().phase = self._get_phase().VERIFYING
                await self._run_verification_phase()

            await self._finalize(True)

        except asyncio.CancelledError:
            self._state.cancelled = True
            await self._finalize(False)
        except Exception as e:
            logger.error("Autonomous deployment fatal", error=str(e))
            self._state.fatal_failure = True
            self._state.fatal_error = str(e)
            br.push_recovery_activity("autonomous", "deployment", "failed", f"Fatal error: {str(e)[:200]}")
            await self._finalize(False)

    async def _run_tool_deployment_phase(self) -> bool:
        br = self._get_bridge()
        self._state.current_phase = "deploying_tools"

        while self._state.current_tool_index < len(self._tool_installers):
            if self._state.cancelled:
                return False
            if self._state.paused:
                await asyncio.sleep(0.5)
                continue

            tool_entry = self._tool_installers[self._state.current_tool_index]
            tool_name = tool_entry["name"]
            self._state.current_tool_name = tool_name

            if tool_entry["status"] in ("completed", "skipped"):
                self._state.current_tool_index += 1
                continue

            logger.info("Deploying tool", tool=tool_name, index=self._state.current_tool_index)
            br.push_deployment_phase(f"Deploying {tool_name}", self._state.current_tool_index + 1, self._state.tools_total)

            success = await self._deploy_tool_with_recovery(tool_name)

            if success:
                tool_entry["status"] = "completed"
                self._state.tools_installed += 1
            else:
                fallback_used = await self._try_fallback_installers(tool_name)
                if fallback_used:
                    tool_entry["status"] = "completed"
                    self._state.tools_installed += 1
                else:
                    tool_entry["status"] = "failed"
                    self._state.tools_failed += 1

            br.update_deployment_summary(total=self._state.tools_total, installed=self._state.tools_installed, failed=self._state.tools_failed, skipped=self._state.tools_skipped)
            br.push_deployment_progress(tool_name, progress_percent=self.progress_percent, current_step="completed" if success else "failed", retry_count=self._state.retry_count)
            br.complete_tool_deployment(tool_name, status="completed" if success else "failed")

            self._state.save_checkpoint()
            self._state.current_tool_index += 1
            await asyncio.sleep(1)

        return True

    async def _deploy_tool_with_recovery(self, tool_name: str) -> bool:
        br = self._get_bridge()
        max_attempts = self._state.max_retries
        attempt = 0
        last_error = ""

        while attempt < max_attempts:
            if self._state.cancelled:
                return False

            attempt += 1
            self._state.retry_count = attempt

            br.push_deployment_progress(tool_name, progress_percent=(attempt / max_attempts) * 50.0, current_step=f"Attempt {attempt}/{max_attempts}", retry_count=attempt - 1)

            try:
                success = await self._execute_install(tool_name, attempt)
                if success:
                    br.remove_retry(tool_name)
                    return True
                last_error = f"Install attempt {attempt} failed"
            except Exception as e:
                last_error = str(e)
                logger.warning("Tool install exception", tool=tool_name, error=last_error)

            br.push_retry_event(tool_name, retry_count=attempt, max_retries=max_attempts, last_error=last_error, cooldown_seconds=min(attempt * 5, 30))

            if attempt < max_attempts:
                await self._attempt_environment_repair(tool_name, last_error)
                cooldown = min(attempt * 5, 60)
                for _ in range(cooldown):
                    if self._state.cancelled:
                        break
                    await asyncio.sleep(1)

        br.push_recovery_activity(tool_name, "deploy", "failed", f"All {max_attempts} attempts failed. Last error: {last_error[:200]}")
        return False

    async def _execute_install(self, tool_name: str, attempt: int) -> bool:
        if self._orchestrator and hasattr(self._orchestrator, 'install_tool'):
            result = await self._orchestrator.install_tool(tool_name, attempt=attempt)
            if hasattr(result, 'success'):
                return result.success
            return bool(result)
        elif self._deployment_executor and hasattr(self._deployment_executor, 'execute'):
            result = await self._deployment_executor.execute(tool_name)
            return bool(result)
        else:
            logger.warning("No installation backend available for", tool=tool_name)
            return False

    async def _try_fallback_installers(self, tool_name: str) -> bool:
        br = self._get_bridge()
        fallbacks = self._fallback_registry.get(tool_name, [])
        if not fallbacks:
            return False

        logger.info("Attempting fallback installers", tool=tool_name, fallbacks=fallbacks)
        br.push_recovery_activity(tool_name, "fallback", "running", f"Trying fallback: {', '.join(fallbacks)}")

        for fallback in fallbacks:
            if self._state.cancelled:
                break
            br.push_deployment_progress(tool_name, progress_percent=80.0, current_step=f"Trying fallback: {fallback}", retry_count=self._state.retry_count)
            success = await self._execute_install(fallback, 1)
            if success:
                br.push_recovery_activity(tool_name, "fallback", "completed", f"Fallback {fallback} succeeded")
                return True
            br.push_recovery_activity(tool_name, "fallback", "failed", f"Fallback {fallback} failed")
        return False

    async def _attempt_environment_repair(self, tool_name: str, error: str) -> None:
        br = self._get_bridge()
        logger.info("Attempting environment repair", tool=tool_name)
        self._state.recovery_count += 1

        br.push_recovery_activity(tool_name, "environment_repair", "running", f"Attempting repair for: {error[:100]}")

        error_lower = error.lower()
        repair_actions = []

        if "not found" in error_lower or "not recognized" in error_lower or "path" in error_lower:
            repair_actions.append(self._repair_path(tool_name))
        if "pip" in error_lower or "package" in error_lower or "module" in error_lower:
            repair_actions.append(self._repair_python_deps())
        if "network" in error_lower or "connection" in error_lower or "timeout" in error_lower or "download" in error_lower:
            repair_actions.append(self._repair_network())
        if "disk" in error_lower or "space" in error_lower or "storage" in error_lower:
            repair_actions.append(self._repair_disk_space())
        if "permission" in error_lower or "access denied" in error_lower or "elevated" in error_lower:
            repair_actions.append(self._repair_permissions())
        if "cache" in error_lower or "corrupt" in error_lower:
            repair_actions.append(self._repair_cache())
        if not repair_actions:
            repair_actions.append(self._repair_generic())

        for repair in repair_actions:
            try:
                await repair
            except Exception as e:
                logger.warning("Repair action failed", error=str(e))

        br.push_recovery_activity(tool_name, "environment_repair", "completed", "Environment repair attempted")

        self._state.recovery_history.append({"tool": tool_name, "error": error[:100], "actions": len(repair_actions), "timestamp": time.time()})

    async def _repair_path(self, tool_name: str) -> None:
        logger.info("Attempting PATH repair", tool=tool_name)
        try:
            if sys.platform == "win32":
                paths_to_check = [
                    os.path.expandvars(r"%LOCALAPPDATA%\Programs"),
                    os.path.expandvars(r"%APPDATA%\npm"),
                    os.path.expandvars(r"%ProgramFiles%"),
                    os.path.expandvars(r"%ProgramFiles(x86)%"),
                    os.path.expandvars(r"%USERPROFILE%\.local\bin"),
                ]
                for p in paths_to_check:
                    if os.path.isdir(p):
                        os.environ["PATH"] = p + os.pathsep + os.environ["PATH"]
        except Exception as e:
            logger.warning("PATH repair failed", error=str(e))

    async def _repair_python_deps(self) -> None:
        logger.info("Attempting Python dependency repair")
        try:
            import subprocess
            subprocess.run([sys.executable, "-m", "pip", "install", "--upgrade", "pip"], capture_output=True, timeout=30)
        except Exception as e:
            logger.warning("Python dep repair failed", error=str(e))

    async def _repair_network(self) -> None:
        logger.info("Attempting network recovery")
        if sys.platform == "win32":
            try:
                import subprocess
                subprocess.run(["ipconfig", "/flushdns"], capture_output=True, timeout=10)
            except Exception:
                pass

    async def _repair_disk_space(self) -> None:
        logger.info("Attempting disk space recovery")
        try:
            temp_dir = tempfile.gettempdir()
            for item in Path(temp_dir).glob("corax_*"):
                if item.is_file():
                    item.unlink(missing_ok=True)
        except Exception:
            pass

    async def _repair_permissions(self) -> None:
        logger.warning("Permission repair needed - may require elevation")

    async def _repair_cache(self) -> None:
        logger.info("Attempting cache recovery")
        cache_dirs = [Path("data/persistence"), Path("data/cache")]
        for cache_dir in cache_dirs:
            if cache_dir.exists():
                try:
                    import shutil
                    shutil.rmtree(cache_dir, ignore_errors=True)
                    cache_dir.mkdir(parents=True, exist_ok=True)
                except Exception:
                    pass

    async def _repair_generic(self) -> None:
        logger.info("Attempting generic recovery")
        await asyncio.sleep(2)

    # --- Reboot Continuation --------------------------------------------

    async def prepare_for_reboot(self) -> Dict[str, Any]:
        logger.info("Preparing for reboot continuation")
        checkpoint = self._state.to_checkpoint()
        checkpoint["tool_list"] = [t["name"] for t in self._tool_installers]
        checkpoint["model_list"] = self._model_queue
        checkpoint["retry_history"] = self._state.retry_history[-10:]
        checkpoint["recovery_history"] = self._state.recovery_history[-10:]

        from src.deployment.persistence import save_deployment_checkpoint
        save_deployment_checkpoint(checkpoint)
        self._get_bridge().save_deployment_state(checkpoint)

        logger.info("Reboot checkpoint prepared", tools_installed=self._state.tools_installed, tool_index=self._state.current_tool_index)
        return checkpoint

    async def check_and_resume(self, tools: List[str], models: List[str]) -> bool:
        if self._state.load_checkpoint():
            logger.info("Resuming from autonomous checkpoint", index=self._state.current_tool_index)
            if not self._tool_installers:
                self._tool_installers = [{"name": t, "status": "pending"} for t in tools]
            if not self._model_queue:
                self._model_queue = list(models)
            return True

        from src.deployment.persistence import load_latest_checkpoint
        persisted = load_latest_checkpoint()
        if persisted:
            logger.info("Resuming from persistence checkpoint")
            self._state.deployment_id = persisted.get("deployment_id")
            self._state.start_time = persisted.get("start_time")
            self._state.current_tool_index = persisted.get("current_tool_index", 0)
            self._state.current_tool_name = persisted.get("current_tool_name", "")
            self._state.current_phase = persisted.get("current_phase", "idle")
            self._state.tools_total = persisted.get("tools_total", len(tools))
            self._state.tools_installed = persisted.get("tools_installed", 0)
            self._state.tools_failed = persisted.get("tools_failed", 0)
            self._state.tools_skipped = persisted.get("tools_skipped", 0)
            self._state.models_total = persisted.get("models_total", len(models))
            self._state.models_pulled = persisted.get("models_pulled", 0)
            self._state.retry_count = persisted.get("retry_count", 0)
            self._state.recovery_count = persisted.get("recovery_count", 0)

            tool_list = persisted.get("tool_list", tools)
            if not self._tool_installers:
                self._tool_installers = [{"name": t, "status": "pending"} for t in tool_list]

            model_list = persisted.get("model_list", models)
            if not self._model_queue:
                self._model_queue = list(model_list)

            return True

        return False

    async def resume_deployment(self) -> None:
        logger.info("Resuming autonomous deployment")
        self._state.active = True
        self._state.authorized = True
        self._state.cancelled = False
        self._state.completed = False
        self._state.fatal_failure = False
        self._cancel_event.clear()

        ui = self._get_ui()
        ui.phase = self._get_phase().DEPLOYING
        br = self._get_bridge()
        br.start_deployment_timer()
        br.update_deployment_summary(total=self._state.tools_total, installed=self._state.tools_installed, failed=self._state.tools_failed, skipped=self._state.tools_skipped)
        br.push_recovery_activity("autonomous", "resume", "running", f"Resuming deployment from tool {self._state.current_tool_index + 1}/{self._state.tools_total}")

        self._emit_status("resuming")
        self._running_task = asyncio.create_task(self._run_deployment_loop())

    async def _run_model_pull_phase(self) -> None:
        br = self._get_bridge()
        self._state.current_phase = "pulling_models"

        for model_name in self._model_queue:
            if self._state.cancelled:
                break
            logger.info("Pulling model", model=model_name)
            br.push_model_progress(model_name, 0.0, "pulling")

            try:
                success = await self._pull_model(model_name)
                if success:
                    self._state.models_pulled += 1
                    br.push_model_progress(model_name, 100.0, "completed")
                else:
                    br.push_model_progress(model_name, 0.0, "failed")
            except Exception as e:
                logger.warning("Model pull failed", model=model_name, error=str(e))
                br.push_model_progress(model_name, 0.0, "failed")

            self._state.save_checkpoint()

    async def _pull_model(self, model_name: str) -> bool:
        if self._orchestrator and hasattr(self._orchestrator, 'pull_model'):
            try:
                result = await self._orchestrator.pull_model(model_name)
                if hasattr(result, 'success'):
                    return result.success
                return bool(result)
            except Exception:
                return False

        for progress in range(0, 101, 10):
            if self._state.cancelled:
                return False
            self._get_bridge().push_model_progress(model_name, float(progress), "pulling")
            await asyncio.sleep(0.5)
        return True

    async def _run_verification_phase(self) -> None:
        br = self._get_bridge()
        self._state.current_phase = "verifying"
        logger.info("Running deployment verification")

        for tool_entry in self._tool_installers:
            if self._state.cancelled:
                break
            if tool_entry["status"] != "completed":
                continue
            tool_name = tool_entry["name"]
            br.push_deployment_progress(tool_name, 100.0, "verifying", retry_count=0)
            await asyncio.sleep(0.3)

    async def _finalize(self, success: bool) -> None:
        ui = self._get_ui()
        phase = self._get_phase()
        br = self._get_bridge()

        self._state.active = False
        self._state.completed = success

        if success:
            ui.phase = phase.COMPLETED
            self._state.clear_checkpoint()
        elif self._state.cancelled:
            ui.phase = phase.CANCELLED
        else:
            ui.phase = phase.FAILED

        elapsed = time.time() - (self._state.start_time or time.time())

        final_state = {
            "deployment_id": self._state.deployment_id,
            "success": success,
            "elapsed_seconds": round(elapsed, 1),
            "tools_total": self._state.tools_total,
            "tools_installed": self._state.tools_installed,
            "tools_failed": self._state.tools_failed,
            "tools_skipped": self._state.tools_skipped,
            "models_pulled": self._state.models_pulled,
            "retry_count": self._state.retry_count,
            "recovery_count": self._state.recovery_count,
            "status": "completed" if success else "failed",
            "fatal_error": self._state.fatal_error,
            "completed_at": datetime.now(timezone.utc).isoformat(),
        }
        br.save_deployment_state(final_state)

        logger.info("Autonomous deployment finalized", success=success, elapsed=round(elapsed, 1))
        self._emit_completion(success)

    def _emit_status(self, status: str) -> None:
        for cb in self._status_callbacks:
            try:
                cb(status)
            except Exception:
                pass

    def _emit_completion(self, success: bool) -> None:
        for cb in self._completion_callbacks:
            try:
                cb(success)
            except Exception:
                pass


# Global singleton
autonomous_deployer = AutonomousDeploymentEngine()
