"""
Tests for agent mode implementations.

Tests the three agent modes:
- Safe mode: all actions require approval
- Assisted mode: safe actions auto-approved
- Autonomous mode: full autonomy within boundaries
"""

import pytest
from unittest.mock import AsyncMock

from src.agent.modes.base import (
    AgentMode,
    AgentModeType,
    ActionProposal,
    ActionRisk,
)
from src.agent.modes.safe_mode import SafeMode
from src.agent.modes.assisted_mode import AssistedMode
from src.agent.modes.autonomous_mode import AutonomousMode


@pytest.fixture
def safe_mode() -> SafeMode:
    return SafeMode()


@pytest.fixture
def assisted_mode() -> AssistedMode:
    return AssistedMode()


@pytest.fixture
def autonomous_mode() -> AutonomousMode:
    return AutonomousMode()


@pytest.fixture
def safe_proposal() -> ActionProposal:
    return ActionProposal(
        action_id="test_1",
        action_type="scan_system",
        description="Scan system hardware",
        risk=ActionRisk.LOW,
    )


@pytest.fixture
def risky_proposal() -> ActionProposal:
    return ActionProposal(
        action_id="test_2",
        action_type="install_tool",
        description="Install development tools",
        risk=ActionRisk.HIGH,
        requires_admin=True,
        modifies_system=True,
    )


class TestSafeMode:
    """Tests for SafeMode - all actions require approval."""

    @pytest.mark.asyncio
    async def test_safe_mode_type(self, safe_mode: SafeMode):
        assert safe_mode.mode_type == AgentModeType.SAFE

    @pytest.mark.asyncio
    async def test_safe_mode_requires_approval(
        self, safe_mode: SafeMode, safe_proposal: ActionProposal
    ):
        """In safe mode, even safe actions require approval."""
        can_execute = await safe_mode.can_execute(safe_proposal)
        assert can_execute is False

    @pytest.mark.asyncio
    async def test_safe_mode_approval_callback_approved(
        self, safe_mode: SafeMode, safe_proposal: ActionProposal
    ):
        """When approval callback returns True, action is approved."""
        mock_callback = AsyncMock(return_value=True)
        safe_mode.set_approval_callback(mock_callback)

        result = await safe_mode.evaluate_action(safe_proposal)
        assert result is True
        assert safe_proposal.approved is True
        mock_callback.assert_called_once_with(safe_proposal)

    @pytest.mark.asyncio
    async def test_safe_mode_approval_callback_denied(
        self, safe_mode: SafeMode, safe_proposal: ActionProposal
    ):
        """When approval callback returns False, action is denied."""
        mock_callback = AsyncMock(return_value=False)
        safe_mode.set_approval_callback(mock_callback)

        result = await safe_mode.evaluate_action(safe_proposal)
        assert result is False
        assert safe_proposal.approved is False
        assert safe_proposal.rejection_reason is not None

    @pytest.mark.asyncio
    async def test_safe_mode_no_callback(
        self, safe_mode: SafeMode, safe_proposal: ActionProposal
    ):
        """Without callback, actions are denied by default."""
        result = await safe_mode.evaluate_action(safe_proposal)
        assert result is False


class TestAssistedMode:
    """Tests for AssistedMode - safe actions auto-approved."""

    @pytest.mark.asyncio
    async def test_assisted_mode_type(self, assisted_mode: AssistedMode):
        assert assisted_mode.mode_type == AgentModeType.ASSISTED

    @pytest.mark.asyncio
    async def test_assisted_auto_approves_safe_actions(
        self, assisted_mode: AssistedMode, safe_proposal: ActionProposal
    ):
        """Safe actions are auto-approved in assisted mode."""
        result = await assisted_mode.evaluate_action(safe_proposal)
        assert result is True
        assert safe_proposal.auto_approved is True

    @pytest.mark.asyncio
    async def test_assisted_requires_approval_for_risky(
        self, assisted_mode: AssistedMode, risky_proposal: ActionProposal
    ):
        """Risky actions require approval in assisted mode."""
        mock_callback = AsyncMock(return_value=True)
        assisted_mode.set_approval_callback(mock_callback)

        result = await assisted_mode.evaluate_action(risky_proposal)
        assert result is True
        assert risky_proposal.auto_approved is False
        mock_callback.assert_called_once_with(risky_proposal)

    @pytest.mark.asyncio
    async def test_assisted_can_execute_safe(
        self, assisted_mode: AssistedMode, safe_proposal: ActionProposal
    ):
        """can_execute returns True for safe actions."""
        assert await assisted_mode.can_execute(safe_proposal) is True

    @pytest.mark.asyncio
    async def test_assisted_cannot_execute_risky(
        self, assisted_mode: AssistedMode, risky_proposal: ActionProposal
    ):
        """can_execute returns False for risky actions."""
        assert await assisted_mode.can_execute(risky_proposal) is False

    @pytest.mark.asyncio
    async def test_assisted_safe_action_types(
        self, assisted_mode: AssistedMode
    ):
        """Known safe action types are auto-approved."""
        for action_type in assisted_mode.SAFE_ACTION_TYPES:
            proposal = ActionProposal(
                action_id=f"test_{action_type}",
                action_type=action_type,
                description=f"Test {action_type}",
                risk=ActionRisk.MEDIUM,
            )
            assert await assisted_mode.can_execute(proposal) is True


class TestAutonomousMode:
    """Tests for AutonomousMode - full autonomy within boundaries."""

    @pytest.mark.asyncio
    async def test_autonomous_mode_type(self, autonomous_mode: AutonomousMode):
        assert autonomous_mode.mode_type == AgentModeType.AUTONOMOUS

    @pytest.mark.asyncio
    async def test_autonomous_auto_approves_safe(
        self, autonomous_mode: AutonomousMode, safe_proposal: ActionProposal
    ):
        """Safe actions are auto-approved in autonomous mode."""
        result = await autonomous_mode.evaluate_action(safe_proposal)
        assert result is True
        assert safe_proposal.auto_approved is True

    @pytest.mark.asyncio
    async def test_autonomous_blocks_high_risk(
        self, autonomous_mode: AutonomousMode
    ):
        """Actions exceeding risk threshold are blocked."""
        critical_proposal = ActionProposal(
            action_id="test_critical",
            action_type="format_disk",
            description="Format system disk",
            risk=ActionRisk.CRITICAL,
        )
        result = await autonomous_mode.evaluate_action(critical_proposal)
        assert result is False
        assert critical_proposal.rejection_reason is not None

    @pytest.mark.asyncio
    async def test_autonomous_blocks_blocked_types(
        self, autonomous_mode: AutonomousMode
    ):
        """Blocked action types are rejected."""
        for action_type in autonomous_mode.BLOCKED_ACTION_TYPES:
            proposal = ActionProposal(
                action_id=f"test_blocked_{action_type}",
                action_type=action_type,
                description=f"Blocked: {action_type}",
                risk=ActionRisk.HIGH,
            )
            result = await autonomous_mode.evaluate_action(proposal)
            assert result is False

    @pytest.mark.asyncio
    async def test_autonomous_respects_allowed_list(
        self, autonomous_mode: AutonomousMode
    ):
        """Only allowed action types are permitted when list is set."""
        limited_mode = AutonomousMode(
            allowed_action_types=["scan_system", "check_version"]
        )

        allowed = ActionProposal(
            action_id="test_allowed",
            action_type="scan_system",
            description="Scan system",
            risk=ActionRisk.LOW,
        )
        assert await limited_mode.evaluate_action(allowed) is True

        denied = ActionProposal(
            action_id="test_denied",
            action_type="install_tool",
            description="Install tool",
            risk=ActionRisk.LOW,
        )
        assert await limited_mode.evaluate_action(denied) is False

    @pytest.mark.asyncio
    async def test_autonomous_concurrent_limit(
        self, autonomous_mode: AutonomousMode
    ):
        """Concurrent action limit is enforced."""
        # Fill up the action slots
        autonomous_mode._active_action_count = autonomous_mode.max_concurrent_actions

        proposal = ActionProposal(
            action_id="test_concurrent",
            action_type="scan_system",
            description="Scan system",
            risk=ActionRisk.LOW,
        )
        result = await autonomous_mode.evaluate_action(proposal)
        assert result is False

    @pytest.mark.asyncio
    async def test_autonomous_release_action(
        self, autonomous_mode: AutonomousMode
    ):
        """release_action decrements the active count."""
        autonomous_mode._active_action_count = 3
        autonomous_mode.release_action()
        assert autonomous_mode._active_action_count == 2

    @pytest.mark.asyncio
    async def test_autonomous_resource_limits(
        self, autonomous_mode: AutonomousMode
    ):
        """Resource limits are enforced."""
        oversized = ActionProposal(
            action_id="test_oversized",
            action_type="download_model",
            description="Download large model",
            risk=ActionRisk.MEDIUM,
            parameters={"size_mb": 10000},  # Exceeds 5000 MB limit
        )
        result = await autonomous_mode.evaluate_action(oversized)
        assert result is False
