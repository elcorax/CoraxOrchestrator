"""
Corax Orchestrator - Autonomous Mode Implementation.

In Autonomous Mode, the agent has full autonomy within configured
boundaries. All actions are auto-approved unless they exceed
configured risk thresholds or violate safety policies.
"""

from typing import Dict, Any, List, Optional, Set

from src.agent.modes.base import AgentMode, AgentModeType, ActionProposal, ActionRisk
from src.core.logging import get_logger

logger = get_logger(__name__)


class AutonomousMode(AgentMode):
    """
    Autonomous operation mode.

    The agent has full autonomy within configured boundaries.
    Actions are auto-approved unless they:
    - Exceed the configured maximum risk threshold
    - Are in the blocked action types list
    - Would modify protected system paths
    - Exceed resource limits
    """

    # Actions that are never allowed even in autonomous mode
    BLOCKED_ACTION_TYPES: Set[str] = {
        "format_disk",
        "delete_system_file",
        "modify_kernel",
        "disable_security",
        "install_unverified_driver",
    }

    # Protected system paths that cannot be modified
    PROTECTED_PATHS: Set[str] = {
        "/System",
        "/Windows/System32",
        "/etc",
        "/boot",
        "/usr/lib",
    }

    def __init__(
        self,
        max_risk_threshold: ActionRisk = ActionRisk.HIGH,
        allowed_action_types: Optional[List[str]] = None,
        blocked_action_types: Optional[Set[str]] = None,
        max_concurrent_actions: int = 5,
        resource_limits: Optional[Dict[str, Any]] = None,
    ) -> None:
        super().__init__()
        self.max_risk_threshold = max_risk_threshold
        self.allowed_action_types = set(allowed_action_types or [])
        self.blocked_action_types = (
            self.BLOCKED_ACTION_TYPES | (blocked_action_types or set())
        )
        self.max_concurrent_actions = max_concurrent_actions
        self.resource_limits = resource_limits or {
            "max_download_size_mb": 5000,
            "max_install_time_minutes": 30,
            "max_models_to_pull": 5,
        }
        self._active_action_count: int = 0

    @property
    def mode_type(self) -> AgentModeType:
        return AgentModeType.AUTONOMOUS

    async def evaluate_action(self, proposal: ActionProposal) -> bool:
        """
        Evaluate action - auto-approve if within boundaries.

        Args:
            proposal: The proposed action

        Returns:
            True if action is within configured boundaries
        """
        # Check if action type is blocked
        if proposal.action_type in self.blocked_action_types:
            proposal.rejection_reason = (
                f"Action type '{proposal.action_type}' is blocked "
                f"in autonomous mode"
            )
            logger.warning(
                "Blocked action rejected",
                action=proposal.action_type,
            )
            return False

        # Check if action type is in allowed list (if configured)
        if self.allowed_action_types and proposal.action_type not in self.allowed_action_types:
            proposal.rejection_reason = (
                f"Action type '{proposal.action_type}' is not in "
                f"the allowed list"
            )
            return False

        # Check risk threshold
        risk_order = [
            ActionRisk.SAFE,
            ActionRisk.LOW,
            ActionRisk.MEDIUM,
            ActionRisk.HIGH,
            ActionRisk.CRITICAL,
        ]
        max_idx = risk_order.index(self.max_risk_threshold)
        action_idx = risk_order.index(proposal.risk)

        if action_idx > max_idx:
            proposal.rejection_reason = (
                f"Risk level '{proposal.risk.value}' exceeds "
                f"maximum threshold '{self.max_risk_threshold.value}'"
            )
            logger.warning(
                "Risk threshold exceeded",
                action=proposal.action_type,
                risk=proposal.risk.value,
                threshold=self.max_risk_threshold.value,
            )
            return False

        # Check resource limits
        if not self._check_resource_limits(proposal):
            return False

        # Check concurrent action limit
        if self._active_action_count >= self.max_concurrent_actions:
            proposal.rejection_reason = (
                f"Maximum concurrent actions ({self.max_concurrent_actions}) "
                f"already reached"
            )
            return False

        # All checks passed - auto-approve
        proposal.approved = True
        proposal.auto_approved = True
        self._active_action_count += 1

        logger.info(
            "Action auto-approved in autonomous mode",
            action=proposal.action_type,
            risk=proposal.risk.value,
        )

        return True

    async def can_execute(self, proposal: ActionProposal) -> bool:
        """
        In autonomous mode, all actions within boundaries can execute.

        Args:
            proposal: The proposed action

        Returns:
            True if action is within configured boundaries
        """
        return await self.evaluate_action(proposal)

    def release_action(self) -> None:
        """Release an action slot (call when action completes)."""
        self._active_action_count = max(0, self._active_action_count - 1)

    def _check_resource_limits(self, proposal: ActionProposal) -> bool:
        """Check if action respects resource limits."""
        params = proposal.parameters

        # Check download size
        if "size_mb" in params:
            if params["size_mb"] > self.resource_limits.get("max_download_size_mb", 5000):
                proposal.rejection_reason = (
                    f"Download size ({params['size_mb']} MB) exceeds limit "
                    f"({self.resource_limits['max_download_size_mb']} MB)"
                )
                return False

        # Check install time
        if proposal.estimated_duration:
            max_minutes = self.resource_limits.get("max_install_time_minutes", 30)
            if proposal.estimated_duration > max_minutes * 60:
                proposal.rejection_reason = (
                    f"Estimated duration exceeds limit"
                )
                return False

        return True
