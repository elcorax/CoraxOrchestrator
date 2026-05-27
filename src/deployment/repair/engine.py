"""
Corax Orchestrator - Repair Engine.

Self-healing repair engine that detects and fixes common
deployment issues automatically.
"""

from typing import Dict, Any, List, Optional
import asyncio
import time

from src.deployment.repair.base import (
    RepairAction,
    RepairResult,
    RepairStatus,
)
from src.deployment.installers.base import AIInstallerBase
from src.core.logging import get_logger

logger = get_logger(__name__)


class RepairEngine:
    """
    Self-healing repair engine for AI infrastructure.

    Detects common deployment issues and executes repair
    actions to restore functionality automatically.
    """

    def __init__(self) -> None:
        self._actions: Dict[str, RepairAction] = {}
        self._installers: Dict[str, AIInstallerBase] = {}
        self._register_default_actions()

    def _register_default_actions(self) -> None:
        """Register default repair actions."""
        self._actions = {
            "restart_ollama": RepairAction(
                name="Restart Ollama Service",
                description="Restart the Ollama service to resolve API issues",
                priority=80,
                timeout=30,
            ),
            "restart_docker": RepairAction(
                name="Restart Docker Containers",
                description="Restart Docker containers for web services",
                priority=70,
                timeout=60,
            ),
            "reinstall_deps": RepairAction(
                name="Reinstall Dependencies",
                description="Reinstall Python dependencies for tools",
                priority=50,
                timeout=300,
            ),
            "fix_permissions": RepairAction(
                name="Fix File Permissions",
                description="Fix common file permission issues",
                priority=40,
                timeout=30,
            ),
            "clear_cache": RepairAction(
                name="Clear Cache",
                description="Clear temporary files and cache",
                priority=30,
                timeout=30,
            ),
            "repair_path": RepairAction(
                name="Repair PATH Variable",
                description="Detect and fix missing PATH entries for installed tools",
                priority=90,
                timeout=60,
            ),
            "repair_env_vars": RepairAction(
                name="Repair Environment Variables",
                description="Restore missing or incorrect environment variables",
                priority=85,
                timeout=30,
            ),
            "repair_partial_install": RepairAction(
                name="Repair Partial Installation",
                description="Detect and fix partially installed tools",
                priority=75,
                timeout=120,
            ),
        }


    def register_installer(self, installer: AIInstallerBase) -> None:
        """Register an installer for repair use."""
        self._installers[installer.tool_key] = installer

    def register_action(self, action: RepairAction) -> None:
        """Register a custom repair action."""
        self._actions[action.name] = action

    async def repair_tool(self, tool_key: str) -> RepairResult:
        """
        Attempt to repair a specific tool.

        Args:
            tool_key: Tool identifier to repair

        Returns:
            RepairResult indicating success/failure
        """
        installer = self._installers.get(tool_key)
        if not installer:
            return RepairResult(
                action_name=f"repair_{tool_key}",
                status=RepairStatus.NOT_APPLICABLE,
                message=f"No installer registered for {tool_key}",
            )

        logger.info("Attempting tool repair", tool=tool_key)
        start = time.time()

        try:
            # Check if tool has a repair method
            if hasattr(installer, "repair"):
                result = await installer.repair()
                duration = round((time.time() - start) * 1000, 2)

                if result.status.value == "installed":
                    return RepairResult(
                        action_name=f"repair_{tool_key}",
                        status=RepairStatus.SUCCEEDED,
                        message=f"Successfully repaired {installer.tool_name}",
                        details={"version": result.version},
                        duration_ms=duration,
                    )
                else:
                    return RepairResult(
                        action_name=f"repair_{tool_key}",
                        status=RepairStatus.FAILED,
                        message=f"Failed to repair {installer.tool_name}: {result.error}",
                        details={"error": result.error},
                        duration_ms=duration,
                    )
            else:
                # Fall back to reinstall
                result = await installer.install()
                duration = round((time.time() - start) * 1000, 2)

                if result.status.value == "installed":
                    return RepairResult(
                        action_name=f"reinstall_{tool_key}",
                        status=RepairStatus.SUCCEEDED,
                        message=f"Reinstalled {installer.tool_name}",
                        duration_ms=duration,
                    )
                else:
                    return RepairResult(
                        action_name=f"reinstall_{tool_key}",
                        status=RepairStatus.FAILED,
                        message=f"Reinstall failed: {result.error}",
                        duration_ms=duration,
                    )

        except Exception as e:
            return RepairResult(
                action_name=f"repair_{tool_key}",
                status=RepairStatus.FAILED,
                message=f"Repair failed with error: {str(e)}",
                details={"error": str(e)},
                duration_ms=round((time.time() - start) * 1000, 2),
            )

    async def run_action(self, action_name: str) -> RepairResult:
        """
        Execute a specific repair action.

        Args:
            action_name: Name of the action to execute

        Returns:
            RepairResult indicating success/failure
        """
        action = self._actions.get(action_name)
        if not action:
            return RepairResult(
                action_name=action_name,
                status=RepairStatus.NOT_APPLICABLE,
                message=f"Unknown repair action: {action_name}",
            )

        if not action.handler:
            return RepairResult(
                action_name=action_name,
                status=RepairStatus.SKIPPED,
                message="No handler registered for this action",
            )

        logger.info("Running repair action", action=action_name)
        start = time.time()

        for attempt in range(action.max_retries):
            try:
                success = await asyncio.wait_for(
                    action.handler(),
                    timeout=action.timeout,
                )
                duration = round((time.time() - start) * 1000, 2)

                if success:
                    return RepairResult(
                        action_name=action_name,
                        status=RepairStatus.SUCCEEDED,
                        message=f"Repair action '{action.name}' completed",
                        duration_ms=duration,
                        retry_count=attempt,
                    )

                logger.warning(
                    "Repair action failed, retrying",
                    action=action_name,
                    attempt=attempt + 1,
                )

            except asyncio.TimeoutError:
                logger.warning(
                    "Repair action timed out",
                    action=action_name,
                    attempt=attempt + 1,
                )
            except Exception as e:
                logger.error(
                    "Repair action error",
                    action=action_name,
                    error=str(e),
                    attempt=attempt + 1,
                )

            if attempt < action.max_retries - 1:
                await asyncio.sleep(2 ** attempt)  # Exponential backoff

        return RepairResult(
            action_name=action_name,
            status=RepairStatus.FAILED,
            message=f"Repair action '{action.name}' failed after {action.max_retries} attempts",
            duration_ms=round((time.time() - start) * 1000, 2),
            retry_count=action.max_retries,
        )

    async def run_all(self) -> List[RepairResult]:
        """Run all registered repair actions in priority order."""
        sorted_actions = sorted(
            self._actions.values(),
            key=lambda a: a.priority,
            reverse=True,
        )

        results = []
        for action in sorted_actions:
            result = await self.run_action(action.name)
            results.append(result)

        return results

    def get_actions(self) -> List[Dict[str, Any]]:
        """Get list of registered repair actions."""
        return [
            {
                "name": action.name,
                "description": action.description,
                "priority": action.priority,
                "timeout": action.timeout,
                "has_handler": action.handler is not None,
            }
            for action in self._actions.values()
        ]
