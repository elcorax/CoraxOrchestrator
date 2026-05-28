"""
Corax Orchestrator - Workflow Definitions.

Defines the workflow model used by the execution engine to manage
multi-step autonomous deployment tasks.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, Any, List, Optional, Callable, Awaitable

from src.core.logging import get_logger

logger = get_logger(__name__)


class WorkflowStatus(Enum):
    """Status of a workflow execution."""
    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
    WAITING_FOR_INPUT = "waiting_for_input"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    SKIPPED = "skipped"


class StepType(Enum):
    """Type of workflow step."""
    ACTION = "action"
    DECISION = "decision"
    SUBWORKFLOW = "subworkflow"
    WAIT = "wait"
    CONDITIONAL = "conditional"
    PARALLEL = "parallel"


@dataclass
class WorkflowStep:
    """
    A single step within a workflow.

    Steps can be actions, decisions, sub-workflows, or control
    flow elements like conditionals and parallel execution.
    """
    step_id: str
    name: str
    step_type: StepType = StepType.ACTION
    description: str = ""
    action_type: Optional[str] = None
    parameters: Dict[str, Any] = field(default_factory=dict)
    status: WorkflowStatus = WorkflowStatus.PENDING
    depends_on: List[str] = field(default_factory=list)
    condition: Optional[str] = None  # Expression to evaluate
    on_success: Optional[str] = None  # Next step on success
    on_failure: Optional[str] = None  # Next step on failure
    max_retries: int = 0
    retry_count: int = 0
    timeout_seconds: Optional[int] = None
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "step_id": self.step_id,
            "name": self.name,
            "step_type": self.step_type.value,
            "description": self.description,
            "action_type": self.action_type,
            "parameters": self.parameters,
            "status": self.status.value,
            "depends_on": self.depends_on,
            "condition": self.condition,
            "max_retries": self.max_retries,
            "retry_count": self.retry_count,
            "timeout_seconds": self.timeout_seconds,
            "result": self.result,
            "error": self.error,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
        }


@dataclass
class Workflow:
    """
    A complete workflow consisting of multiple steps.

    Workflows are the primary unit of autonomous execution.
    They can be created by the planner, loaded from persistence,
    or defined programmatically.
    """
    workflow_id: str
    name: str
    description: str = ""
    steps: List[WorkflowStep] = field(default_factory=list)
    status: WorkflowStatus = WorkflowStatus.PENDING
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    variables: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def add_step(self, step: WorkflowStep) -> None:
        """Add a step to the workflow."""
        self.steps.append(step)
        self.updated_at = datetime.now(timezone.utc).isoformat()

    def get_step(self, step_id: str) -> Optional[WorkflowStep]:
        """Get a step by ID."""
        for step in self.steps:
            if step.step_id == step_id:
                return step
        return None

    def get_next_pending_step(self) -> Optional[WorkflowStep]:
        """
        Get the next step that is ready to execute.

        A step is ready if:
        - It is in PENDING status
        - All dependencies are COMPLETED
        - Any conditions are met
        """
        for step in self.steps:
            if step.status != WorkflowStatus.PENDING:
                continue

            # Check dependencies
            deps_met = all(
                self.get_step(dep_id) is not None
                and self.get_step(dep_id).status == WorkflowStatus.COMPLETED
                for dep_id in step.depends_on
            )

            if deps_met:
                return step

        return None

    def get_pending_steps(self) -> List[WorkflowStep]:
        """Get all pending steps."""
        return [s for s in self.steps if s.status == WorkflowStatus.PENDING]

    def get_completed_steps(self) -> List[WorkflowStep]:
        """Get all completed steps."""
        return [s for s in self.steps if s.status == WorkflowStatus.COMPLETED]

    def get_failed_steps(self) -> List[WorkflowStep]:
        """Get all failed steps."""
        return [s for s in self.steps if s.status == WorkflowStatus.FAILED]

    def is_complete(self) -> bool:
        """Check if all steps are completed."""
        return all(
            s.status in (WorkflowStatus.COMPLETED, WorkflowStatus.SKIPPED)
            for s in self.steps
        )

    def has_failed(self) -> bool:
        """Check if any step has failed."""
        return any(s.status == WorkflowStatus.FAILED for s in self.steps)

    def progress_percentage(self) -> float:
        """Calculate workflow progress as a percentage."""
        if not self.steps:
            return 0.0
        completed = len(self.get_completed_steps())
        return (completed / len(self.steps)) * 100.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "workflow_id": self.workflow_id,
            "name": self.name,
            "description": self.description,
            "steps": [s.to_dict() for s in self.steps],
            "status": self.status.value,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "variables": self.variables,
            "error": self.error,
            "progress_percentage": self.progress_percentage(),
        }
