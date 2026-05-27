"""
Corax Orchestrator - Safe Mode Implementation.

In Safe Mode, every action requires explicit user approval.
No action is executed autonomously. This is the default mode
and provides maximum safety.
"""

from src.agent.modes.base import AgentMode, AgentModeType, ActionProposal, ActionRisk
from src.core.logging import get_logger

logger = get_logger(__name__)


class SafeMode(AgentMode):
    """
    Safe operation mode.

    All actions require explicit user approval before execution.
    No autonomous execution is permitted. This is the safest mode
    and is the default for new sessions.
    """

    @property
    def mode_type(self) -> AgentModeType:
        return AgentModeType.SAFE

    async def evaluate_action(self, proposal: ActionProposal) -> bool:
        """
        Evaluate action - always requires approval in safe mode.

        Args:
            proposal: The proposed action

        Returns:
            True only if explicitly approved by user
        """
        logger.info(
            "Safe mode: requesting approval for action",
            action=proposal.action_type,
            description=proposal.description,
        )

        await self._notify("action_proposed", proposal.to_dict())
        approved = await self._request_approval(proposal)

        if approved:
            proposal.approved = True
            logger.info("Action approved", action=proposal.action_id)
        else:
            proposal.rejection_reason = "Denied by user in safe mode"
            logger.info("Action denied", action=proposal.action_id)

        return approved

    async def can_execute(self, proposal: ActionProposal) -> bool:
        """
        In safe mode, no actions can be executed autonomously.

        Args:
            proposal: The proposed action

        Returns:
            Always False in safe mode
        """
        return False
