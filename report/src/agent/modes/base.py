"""
Corax Orchestrator - Agent Mode Base Classes.

Defines the abstract base for agent operation modes and the
enumeration of available mode types.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Any, List, Optional, Callable, Awaitable

from src.core.logging import get_logger

logger = get_logger(__name__)


class AgentModeType(Enum):
    """Available agent operation modes."""
    SAFE = "safe"
    ASSISTED = "assisted"
    AUTONOMOUS = "autonomous"


class ActionRisk(Enum):
    """Risk classification for agent actions."""
    SAFE = "safe"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class ActionProposal:
    """
    A proposed action that the agent wants to take.

    The mode determines whether this action requires user approval
    before execution.
    """
    action_id: str
    action_type: str
    description: str
    risk: ActionRisk
    tool: Optional[str] = None
    parameters: Dict[str, Any] = field(default_factory=dict)
    rationale: str = ""
    estimated_duration: Optional[int] = None  # seconds
    requires_admin: bool = False
    modifies_system: bool = False
    affects_network: bool = False
    approved: bool = False
    auto_approved: bool = False
    rejection_reason: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "action_id": self.action_id,
            "action_type": self.action_type,
            "description": self.description,
            "risk": self.risk.value,
            "tool": self.tool,
            "parameters": self.parameters,
            "rationale": self.rationale,
            "estimated_duration": self.estimated_duration,
            "requires_admin": self.requires_admin,
            "modifies_system": self.modifies_system,
            "affects_network": self.affects_network,
            "approved": self.approved,
            "auto_approved": self.auto_approved,
            "rejection_reason": self.rejection_reason,
        }


class AgentMode(ABC):
    """
    Abstract base class for agent operation modes.

    Each mode implements a different level of autonomy:
    - Safe: All actions require explicit approval
    - Assisted: Safe actions auto-approved, risky actions ask
    - Autonomous: Full autonomy within configured boundaries
    """

    def __init__(self) -> None:
        self._approval_callback: Optional[
            Callable[[ActionProposal], Awaitable[bool]]
        ] = None
        self._notification_callback: Optional[
            Callable[[str, Dict[str, Any]], Awaitable[None]]
        ] = None

    @property
    @abstractmethod
    def mode_type(self) -> AgentModeType:
        """Get the type of this mode."""
        ...

    @abstractmethod
    async def evaluate_action(self, proposal: ActionProposal) -> bool:
        """
        Evaluate whether an action should be executed.

        Args:
            proposal: The proposed action to evaluate

        Returns:
            True if the action should proceed
        """
        ...

    @abstractmethod
    async def can_execute(self, proposal: ActionProposal) -> bool:
        """
        Check if the agent can execute this action autonomously.

        Args:
            proposal: The proposed action

        Returns:
            True if the agent can execute without user input
        """
        ...

    def set_approval_callback(
        self, callback: Callable[[ActionProposal], Awaitable[bool]]
    ) -> None:
        """Set callback for user approval requests."""
        self._approval_callback = callback

    def set_notification_callback(
        self, callback: Callable[[str, Dict[str, Any]], Awaitable[None]]
    ) -> None:
        """Set callback for user notifications."""
        self._notification_callback = callback

    async def _request_approval(self, proposal: ActionProposal) -> bool:
        """
        Request user approval for an action.

        Args:
            proposal: The action requiring approval

        Returns:
            True if approved
        """
        if self._approval_callback:
            return await self._approval_callback(proposal)
        # No callback configured - deny by default
        logger.warning(
            "No approval callback configured, denying action",
            action=proposal.action_type,
        )
        return False

    async def _notify(
        self, event: str, data: Dict[str, Any]
    ) -> None:
        """Send a notification to the user."""
        if self._notification_callback:
            await self._notification_callback(event, data)

    def _classify_risk(self, proposal: ActionProposal) -> ActionRisk:
        """Classify the risk level of an action."""
        if proposal.requires_admin or proposal.modifies_system:
            return ActionRisk.HIGH
        if proposal.affects_network:
            return ActionRisk.MEDIUM
        return ActionRisk.LOW
