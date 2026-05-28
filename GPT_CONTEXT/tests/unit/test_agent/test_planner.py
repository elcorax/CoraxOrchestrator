"""
Tests for planner validation - execution cycle detection.

Tests cover:
- Valid execution graph validation
- Circular dependency rejection
- Orphan operation rejection
- Self-referencing (recursive) chain detection
- Retry-safe validation (no false positives on valid retry steps)
"""

import pytest
from uuid import uuid4

from src.agent.reasoning.planner import (
    Planner,
    Plan,
    PlanStep,
    ValidationSeverity,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def planner() -> Planner:
    return Planner()


def _make_step(
    step_id: str,
    action_type: str = "scan_system",
    depends_on: list = None,
) -> PlanStep:
    return PlanStep(
        step_id=step_id,
        action_type=action_type,
        description=f"Step {step_id}",
        depends_on=depends_on or [],
    )


def _make_plan(steps: list) -> Plan:
    return Plan(
        plan_id=str(uuid4()),
        goal="test goal",
        steps=steps,
    )


# ---------------------------------------------------------------------------
# Valid execution graph
# ---------------------------------------------------------------------------

class TestValidExecutionGraph:
    """A plan with a valid DAG must pass validation."""

    def test_no_dependencies_passes(self, planner: Planner):
        """Steps with no dependencies at all should pass."""
        plan = _make_plan([
            _make_step("step_a"),
            _make_step("step_b"),
            _make_step("step_c"),
        ])
        result = planner.validate_plan(plan)
        assert result.is_valid is True
        assert len(result.errors) == 0

    def test_linear_chain_passes(self, planner: Planner):
        """A -> B -> C linear chain should pass."""
        plan = _make_plan([
            _make_step("step_a", depends_on=[]),
            _make_step("step_b", depends_on=["step_a"]),
            _make_step("step_c", depends_on=["step_b"]),
        ])
        result = planner.validate_plan(plan)
        assert result.is_valid is True
        assert len(result.errors) == 0

    def test_diamond_dag_passes(self, planner: Planner):
        """Diamond-shaped DAG should pass."""
        plan = _make_plan([
            _make_step("step_root", depends_on=[]),
            _make_step("step_left", depends_on=["step_root"]),
            _make_step("step_right", depends_on=["step_root"]),
            _make_step("step_leaf", depends_on=["step_left", "step_right"]),
        ])
        result = planner.validate_plan(plan)
        assert result.is_valid is True
        assert len(result.errors) == 0

    def test_multiple_roots_passes(self, planner: Planner):
        """Multiple root steps with no dependencies should pass."""
        plan = _make_plan([
            _make_step("step_root_a"),
            _make_step("step_root_b"),
            _make_step("step_leaf", depends_on=["step_root_a", "step_root_b"]),
        ])
        result = planner.validate_plan(plan)
        assert result.is_valid is True


# ---------------------------------------------------------------------------
# Circular dependency rejection
# ---------------------------------------------------------------------------

class TestCircularDependencyRejection:
    """Cycles in the dependency graph must be rejected."""

    def test_direct_cycle_rejected(self, planner: Planner):
        """A -> B -> A should be rejected."""
        plan = _make_plan([
            _make_step("step_a", depends_on=["step_b"]),
            _make_step("step_b", depends_on=["step_a"]),
        ])
        result = planner.validate_plan(plan)
        assert result.is_valid is False
        codes = {e.code for e in result.errors}
        assert "CIRCULAR_DEPENDENCY" in codes

    def test_self_loop_rejected_as_recursive(self, planner: Planner):
        """A -> A (self-loop) should be rejected as self-referencing."""
        plan = _make_plan([
            _make_step("step_a", depends_on=["step_a"]),
        ])
        result = planner.validate_plan(plan)
        assert result.is_valid is False
        codes = {e.code for e in result.errors}
        assert "SELF_REFERENCING_DEPENDENCY" in codes

    def test_longer_cycle_rejected(self, planner: Planner):
        """A -> B -> C -> A should be rejected."""
        plan = _make_plan([
            _make_step("step_a", depends_on=["step_c"]),
            _make_step("step_b", depends_on=["step_a"]),
            _make_step("step_c", depends_on=["step_b"]),
        ])
        result = planner.validate_plan(plan)
        assert result.is_valid is False
        codes = {e.code for e in result.errors}
        assert "CIRCULAR_DEPENDENCY" in codes

    def test_cycle_with_extra_branches_rejected(self, planner: Planner):
        """Graph with both a cycle and valid branches should be rejected."""
        plan = _make_plan([
            _make_step("step_a", depends_on=["step_b"]),
            _make_step("step_b", depends_on=["step_c"]),
            _make_step("step_c", depends_on=["step_a"]),  # cycle: a->b->c->a
            _make_step("step_d", depends_on=["step_a"]),  # valid leaf from cycle
        ])
        result = planner.validate_plan(plan)
        assert result.is_valid is False
        codes = {e.code for e in result.errors}
        assert "CIRCULAR_DEPENDENCY" in codes


# ---------------------------------------------------------------------------
# Orphan operation rejection
# ---------------------------------------------------------------------------

class TestOrphanOperationRejection:
    """Steps that depend on non-existent steps must be rejected."""

    def test_orphan_dependency_rejected(self, planner: Planner):
        """Step depending on non-existent step should be rejected."""
        plan = _make_plan([
            _make_step("step_a", depends_on=["step_missing"]),
        ])
        result = planner.validate_plan(plan)
        assert result.is_valid is False
        codes = {e.code for e in result.errors}
        assert "ORPHAN_DEPENDENCY" in codes

    def test_multiple_orphans_rejected(self, planner: Planner):
        """Multiple orphan dependencies should all be reported."""
        plan = _make_plan([
            _make_step("step_a", depends_on=["missing_1", "missing_2"]),
        ])
        result = planner.validate_plan(plan)
        assert result.is_valid is False
        orphan_errors = [e for e in result.errors if e.code == "ORPHAN_DEPENDENCY"]
        assert len(orphan_errors) == 2

    def test_mixed_valid_and_orphan_rejected(self, planner: Planner):
        """Plan with valid deps and one orphan should still be rejected."""
        plan = _make_plan([
            _make_step("step_a"),
            _make_step("step_b", depends_on=["step_a", "step_missing"]),
        ])
        result = planner.validate_plan(plan)
        assert result.is_valid is False
        codes = {e.code for e in result.errors}
        assert "ORPHAN_DEPENDENCY" in codes


# ---------------------------------------------------------------------------
# Retry-safe validation
# ---------------------------------------------------------------------------

class TestRetrySafeValidation:
    """
    Validation must not produce false positives for valid patterns
    that may appear in retry or recovery scenarios.
    """

    def test_retry_step_same_action_type_passes(self, planner: Planner):
        """
        A retry step with the same action type but no dependency
        cycle should pass validation.
        """
        plan = _make_plan([
            _make_step("step_install", action_type="install_tool"),
            _make_step("step_verify", action_type="verify_installation",
                        depends_on=["step_install"]),
            _make_step("step_retry", action_type="install_tool",
                        depends_on=["step_verify"]),
        ])
        result = planner.validate_plan(plan)
        assert result.is_valid is True

    def test_parallel_recovery_steps_passes(self, planner: Planner):
        """Parallel recovery steps with no cycles should pass."""
        plan = _make_plan([
            _make_step("step_primary", action_type="install_tool"),
            _make_step("step_fallback", action_type="install_tool",
                        depends_on=["step_primary"]),
            _make_step("step_report", action_type="generate_report",
                        depends_on=["step_primary", "step_fallback"]),
        ])
        result = planner.validate_plan(plan)
        assert result.is_valid is True

    def test_empty_plan_passes(self, planner: Planner):
        """A plan with no steps should pass."""

        plan = Plan(
            plan_id=str(uuid4()),
            goal="empty",
            steps=[],
        )
        result = planner.validate_plan(plan)
        assert result.is_valid is True
        assert len(result.errors) == 0

    def test_no_duplicate_cycle_errors(self, planner: Planner):
        """A single cycle must not produce duplicate cycle errors."""
        plan = _make_plan([
            _make_step("step_a", depends_on=["step_b"]),
            _make_step("step_b", depends_on=["step_a"]),
        ])
        result = planner.validate_plan(plan)
        circular_errors = [
            e for e in result.errors
            if e.code == "CIRCULAR_DEPENDENCY"
        ]
        # Should only have one circular dependency error for this single cycle
        assert len(circular_errors) == 1


# ---------------------------------------------------------------------------
# Validation error properties
# ---------------------------------------------------------------------------

class TestValidationErrorProperties:
    """Validation errors must carry correct metadata."""

    def test_orphan_error_has_correct_fields(self, planner: Planner):
        """Orphan dependency error must include step_id and related_step_ids."""
        plan = _make_plan([
            _make_step("step_a", depends_on=["step_ghost"]),
        ])
        result = planner.validate_plan(plan)
        assert len(result.errors) == 1
        err = result.errors[0]
        assert err.code == "ORPHAN_DEPENDENCY"
        assert err.step_id == "step_a"
        assert err.related_step_ids == ["step_ghost"]
        assert err.details is not None
        assert "valid_step_ids" in err.details

    def test_circular_error_has_cycle_path(self, planner: Planner):
        """Circular dependency error must include the cycle path."""
        plan = _make_plan([
            _make_step("step_a", depends_on=["step_b"]),
            _make_step("step_b", depends_on=["step_a"]),
        ])
        result = planner.validate_plan(plan)
        circular = [e for e in result.errors if e.code == "CIRCULAR_DEPENDENCY"]
        assert len(circular) == 1
        err = circular[0]
        assert err.details is not None
        assert "cycle" in err.details
        cycle = err.details["cycle"]
        assert len(cycle) >= 3  # e.g. ["a", "b", "a"] or ["b", "a", "b"]

    def test_self_referencing_error_has_correct_fields(self, planner: Planner):
        """Self-referencing error must include step_id."""
        plan = _make_plan([
            _make_step("step_a", depends_on=["step_a"]),
        ])
        result = planner.validate_plan(plan)
        self_ref = [
            e for e in result.errors
            if e.code == "SELF_REFERENCING_DEPENDENCY"
        ]
        assert len(self_ref) == 1
        err = self_ref[0]
        assert err.step_id == "step_a"
        assert err.severity == ValidationSeverity.ERROR
