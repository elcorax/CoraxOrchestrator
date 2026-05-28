"""
Corax Orchestrator - Assisted Mode Implementation.

In Assisted Mode, safe actions are auto-approved while risky
actions require user approval. This provides a balance between
automation and safety.
"""

from src.agent.modes.base import AgentMode, AgentModeType, ActionProposal, ActionRisk
from src.core.logging import get_logger

logger = get_logger(__name__)


class AssistedMode(AgentMode):
    """
    Assisted operation mode.

    Safe and low-risk actions are auto-approved. Medium and
    high-risk actions require user approval. Critical actions
    always require explicit approval regardless of risk level.
    """

    # Actions that are always considered safe to auto-execute
    SAFE_ACTION_TYPES = {
        "read_file",
        "list_directory",
        "check_version",
        "query_status",
        "scan_system",
        "analyze_environment",
        "list_tools",
        "search_tools",
        "get_config",
        "check_connectivity",
    }

    @property
    def mode_type(self) -> AgentModeType:
        return AgentModeType.ASSISTED

    async def evaluate_action(self, proposal: ActionProposal) -> bool:
        """
        Evaluate action - auto-approve safe actions, ask for risky ones.

        Args:
            proposal: The proposed action

        Returns:
            True if action should proceed
        """
        # Check if we can auto-execute
        if await self.can_execute(proposal):
            proposal.approved = True
            proposal.auto_approved = True
            logger.info(
                "Action auto-approved in assisted mode",
                action=proposal.action_type,
                risk=proposal.risk.value,
            )
            return True

        # Request approval for risky actions
        logger.info(
            "Assisted mode: requesting approval for action",
            action=proposal.action_type,
            risk=proposal.risk.value,
            description=proposal.description,
        )

        await self._notify("action_proposed", proposal.to_dict())
        approved = await self._request_approval(proposal)

        if approved:
            proposal.approved = True
            logger.info("Action approved", action=proposal.action_id)
        else:
            proposal.rejection_reason = "Denied by user in assisted mode"
            logger.info("Action denied", action=proposal.action_id)

        return approved

    async def can_execute(self, proposal: ActionProposal) -> bool:
        """
        Check if action can be auto-executed.

        Auto-executes if:
        - Action type is in the safe list, OR
        - Risk is SAFE or LOW, AND
        - Action doesn't require admin, AND
        - Action doesn't modify the system

        Args:
            proposal: The proposed action

        Returns:
            True if action can be auto-executed
        """
        # Check if it's a known safe action type
        if proposal.action_type in self.SAFE_ACTION_TYPES:
            return True

        # Check risk level
        if proposal.risk in (ActionRisk.SAFE, ActionRisk.LOW):
            # Don't auto-execute if it requires admin or modifies system
            if not proposal.requires_admin and not proposal.modifies_system:
                return True

        return False
