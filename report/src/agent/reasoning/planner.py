"""
Corax Orchestrator - Planner Module.

Creates execution plans by decomposing goals into ordered steps
with dependency resolution and resource allocation.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, Any, List, Optional, Set, Tuple
from uuid import uuid4

from src.core.logging import get_logger

logger = get_logger(__name__)


class ValidationSeverity(Enum):
    """Severity of a validation issue."""
    ERROR = "error"
    WARNING = "warning"


@dataclass
class ValidationError:
    """
    A validation error found during plan validation.

    Describes structural issues in a plan before execution.
    """
    code: str
    message: str
    severity: ValidationSeverity
    step_id: Optional[str] = None
    related_step_ids: Optional[List[str]] = None
    details: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message,
            "severity": self.severity.value,
            "step_id": self.step_id,
            "related_step_ids": self.related_step_ids,
            "details": self.details,
        }


@dataclass
class PlanValidationResult:
    """
    Result of plan validation.

    Contains any errors or warnings detected during structural
    validation of a plan before execution.
    """
    is_valid: bool
    errors: List[ValidationError] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "is_valid": self.is_valid,
            "errors": [e.to_dict() for e in self.errors],
        }


class PlanStepStatus(Enum):
    """Status of a plan step."""
    PENDING = "pending"
    READY = "ready"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    BLOCKED = "blocked"


@dataclass
class PlanStep:
    """
    A single step in a deployment plan.

    Steps are the atomic units of work that the agent executes.
    """
    step_id: str
    action_type: str
    description: str
    parameters: Dict[str, Any] = field(default_factory=dict)
    depends_on: List[str] = field(default_factory=list)
    status: PlanStepStatus = PlanStepStatus.PENDING
    estimated_duration: Optional[int] = None  # seconds
    required_tools: List[str] = field(default_factory=list)
    requires_admin: bool = False
    timeout: Optional[int] = None  # seconds
    retry_on_failure: bool = True
    max_retries: int = 2

    def to_dict(self) -> Dict[str, Any]:
        return {
            "step_id": self.step_id,
            "action_type": self.action_type,
            "description": self.description,
            "parameters": self.parameters,
            "depends_on": self.depends_on,
            "status": self.status.value,
            "estimated_duration": self.estimated_duration,
            "required_tools": self.required_tools,
            "requires_admin": self.requires_admin,
            "timeout": self.timeout,
        }


@dataclass
class Plan:
    """
    A complete execution plan.

    Plans are created by the planner and executed by the
    execution engine. They contain all steps needed to
    achieve a goal.
    """
    plan_id: str
    goal: str
    steps: List[PlanStep]
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    estimated_total_duration: Optional[int] = None  # seconds
    requires_admin: bool = False
    total_steps: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.total_steps = len(self.steps)

    def get_ready_steps(self) -> List[PlanStep]:
        """Get steps that are ready to execute."""
        ready = []
        for step in self.steps:
            if step.status != PlanStepStatus.PENDING:
                continue
            deps_met = all(
                self._is_step_completed(dep_id) for dep_id in step.depends_on
            )
            if deps_met:
                ready.append(step)
        return ready

    def _is_step_completed(self, step_id: str) -> bool:
        """Check if a dependency step is completed."""
        for step in self.steps:
            if step.step_id == step_id:
                return step.status == PlanStepStatus.COMPLETED
        return False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "plan_id": self.plan_id,
            "goal": self.goal,
            "steps": [s.to_dict() for s in self.steps],
            "created_at": self.created_at,
            "estimated_total_duration": self.estimated_total_duration,
            "requires_admin": self.requires_admin,
            "total_steps": self.total_steps,
        }


class Planner:
    """
    Creates execution plans by decomposing goals into steps.

    The planner analyzes goals and generates ordered sequences
    of steps with proper dependency resolution.
    """

    # Template plans for common goals
    PLAN_TEMPLATES: Dict[str, List[Dict[str, Any]]] = {
        "full_deploy": [
            {
                "action_type": "scan_system",
                "description": "Scan system hardware and software",
                "estimated_duration": 30,
            },
            {
                "action_type": "analyze_environment",
                "description": "Analyze environment readiness",
                "depends_on": ["step_0"],
                "estimated_duration": 10,
            },
            {
                "action_type": "install_tools",
                "description": "Install required development tools",
                "depends_on": ["step_1"],
                "estimated_duration": 300,
                "requires_admin": True,
            },
            {
                "action_type": "pull_models",
                "description": "Download AI models",
                "depends_on": ["step_2"],
                "estimated_duration": 600,
            },
            {
                "action_type": "generate_report",
                "description": "Generate deployment report",
                "depends_on": ["step_3"],
                "estimated_duration": 10,
            },
        ],
        "quick_scan": [
            {
                "action_type": "scan_system",
                "description": "Quick system scan",
                "estimated_duration": 15,
            },
            {
                "action_type": "generate_report",
                "description": "Generate scan report",
                "depends_on": ["step_0"],
                "estimated_duration": 5,
            },
        ],
        "install_tool": [
            {
                "action_type": "scan_system",
                "description": "Check system prerequisites",
                "estimated_duration": 10,
            },
            {
                "action_type": "install_tool",
                "description": "Install specified tool",
                "depends_on": ["step_0"],
                "estimated_duration": 120,
                "requires_admin": True,
            },
            {
                "action_type": "verify_installation",
                "description": "Verify tool installation",
                "depends_on": ["step_1"],
                "estimated_duration": 10,
            },
        ],
    }

    def create_plan(
        self,
        goal: str,
        context: Dict[str, Any],
        available_tools: Optional[List[str]] = None,
    ) -> Plan:
        """
        Create a plan to achieve a goal.

        Args:
            goal: The goal to achieve
            context: Current context (system info, mode, etc.)
            available_tools: Tools available for execution

        Returns:
            Plan with ordered steps
        """
        plan_id = str(uuid4())

        # Check if we have a template for this goal
        template_key = self._match_template(goal)
        if template_key:
            return self._create_from_template(
                plan_id=plan_id,
                goal=goal,
                template_key=template_key,
                context=context,
            )

        # Generate a custom plan
        return self._generate_custom_plan(
            plan_id=plan_id,
            goal=goal,
            context=context,
            available_tools=available_tools,
        )

    def _match_template(self, goal: str) -> Optional[str]:
        """Match a goal to a plan template."""
        goal_lower = goal.lower()

        if "full" in goal_lower and "deploy" in goal_lower:
            return "full_deploy"
        elif "scan" in goal_lower:
            return "quick_scan"
        elif "install" in goal_lower:
            return "install_tool"

        return None

    def _create_from_template(
        self,
        plan_id: str,
        goal: str,
        template_key: str,
        context: Dict[str, Any],
    ) -> Plan:
        """Create a plan from a template."""
        template = self.PLAN_TEMPLATES[template_key]
        steps = []
        total_duration = 0
        requires_admin = False

        for i, step_data in enumerate(template):
            step_id = f"step_{i}"
            step = PlanStep(
                step_id=step_id,
                action_type=step_data["action_type"],
                description=step_data["description"],
                depends_on=step_data.get("depends_on", []),
                estimated_duration=step_data.get("estimated_duration"),
                requires_admin=step_data.get("requires_admin", False),
                parameters=step_data.get("parameters", {}),
            )
            steps.append(step)

            if step.estimated_duration:
                total_duration += step.estimated_duration
            if step.requires_admin:
                requires_admin = True

        return Plan(
            plan_id=plan_id,
            goal=goal,
            steps=steps,
            estimated_total_duration=total_duration,
            requires_admin=requires_admin,
            metadata={
                "template": template_key,
                "context": context,
            },
        )

    def _generate_custom_plan(
        self,
        plan_id: str,
        goal: str,
        context: Dict[str, Any],
        available_tools: Optional[List[str]] = None,
    ) -> Plan:
        """Generate a custom plan for an arbitrary goal."""
        steps = []
        total_duration = 0
        requires_admin = False

        # Always start with a scan if not already done
        if not context.get("system_scanned"):
            scan_step = PlanStep(
                step_id="step_0",
                action_type="scan_system",
                description="Scan system to gather current state",
                estimated_duration=30,
            )
            steps.append(scan_step)
            total_duration += 30

        # Add goal-specific steps
        step_index = len(steps)
        if "install" in goal.lower():
            install_step = PlanStep(
                step_id=f"step_{step_index}",
                action_type="install_tool",
                description=f"Install: {goal}",
                depends_on=[f"step_{i}" for i in range(step_index)],
                estimated_duration=120,
                requires_admin=True,
            )
            steps.append(install_step)
            total_duration += 120
            requires_admin = True

            verify_step = PlanStep(
                step_id=f"step_{step_index + 1}",
                action_type="verify_installation",
                description="Verify installation",
                depends_on=[f"step_{step_index}"],
                estimated_duration=10,
            )
            steps.append(verify_step)
            total_duration += 10

        elif "model" in goal.lower():
            model_step = PlanStep(
                step_id=f"step_{step_index}",
                action_type="pull_model",
                description=f"Download model: {goal}",
                depends_on=[f"step_{i}" for i in range(step_index)],
                estimated_duration=300,
            )
            steps.append(model_step)
            total_duration += 300

        # Always end with a report
        report_step = PlanStep(
            step_id=f"step_{len(steps)}",
            action_type="generate_report",
            description="Generate execution report",
            depends_on=[f"step_{i}" for i in range(len(steps))],
            estimated_duration=10,
        )
        steps.append(report_step)
        total_duration += 10

        return Plan(
            plan_id=plan_id,
            goal=goal,
            steps=steps,
            estimated_total_duration=total_duration,
            requires_admin=requires_admin,
            metadata={
                "generated": "custom",
                "context": context,
            },
        )

    def validate_plan(self, plan: Plan) -> PlanValidationResult:
        """
        Validate a plan for structural issues before execution.

        Detects:
        - Circular dependencies (A -> B -> A)
        - Recursive execution chains (self-referencing steps)
        - Orphan steps (depend on non-existent steps)
        - Missing step IDs referenced in depends_on

        Args:
            plan: The plan to validate

        Returns:
            PlanValidationResult with any errors detected
        """
        errors: List[ValidationError] = []
        step_ids: Set[str] = {s.step_id for s in plan.steps}

        # Build dependency graph adjacency list
        graph: Dict[str, List[str]] = {}
        for step in plan.steps:
            graph[step.step_id] = list(step.depends_on)

        # 1. Detect orphan dependencies (non-existent step references)
        for step in plan.steps:
            for dep_id in step.depends_on:
                if dep_id not in step_ids:
                    errors.append(ValidationError(
                        code="ORPHAN_DEPENDENCY",
                        message=(
                            f"Step '{step.step_id}' depends on non-existent "
                            f"step '{dep_id}'"
                        ),
                        severity=ValidationSeverity.ERROR,
                        step_id=step.step_id,
                        related_step_ids=[dep_id],
                        details={
                            "depends_on": dep_id,
                            "valid_step_ids": sorted(step_ids),
                        },
                    ))

        # 2. Detect recursive (self-referencing) chains
        for step in plan.steps:
            if step.step_id in step.depends_on:
                errors.append(ValidationError(
                    code="SELF_REFERENCING_DEPENDENCY",
                    message=(
                        f"Step '{step.step_id}' depends on itself, "
                        f"creating a recursive execution chain"
                    ),
                    severity=ValidationSeverity.ERROR,
                    step_id=step.step_id,
                    related_step_ids=[step.step_id],
                ))

        # 3. Detect circular dependencies using DFS (Tarjan-style)
        visited: Set[str] = set()
        recursion_stack: Set[str] = set()
        cycle_path: Dict[str, List[str]] = {}

        def _dfs(node: str, path: List[str]) -> None:
            """DFS traversal recording any cycles found."""
            if node in recursion_stack:
                # Cycle detected - reconstruct the cycle path
                cycle_start_idx = path.index(node)
                cycle = path[cycle_start_idx:] + [node]
                cycle_path[node] = cycle
                return
            if node in visited:
                return

            visited.add(node)
            recursion_stack.add(node)
            path.append(node)

            for neighbor in graph.get(node, []):
                _dfs(neighbor, path)

            path.pop()
            recursion_stack.discard(node)

        for step in plan.steps:
            if step.step_id not in visited:
                _dfs(step.step_id, [])

        for _, cycle in cycle_path.items():
            errors.append(ValidationError(
                code="CIRCULAR_DEPENDENCY",
                message=(
                    f"Circular dependency detected: "
                    f"{' -> '.join(cycle)}"
                ),
                severity=ValidationSeverity.ERROR,
                related_step_ids=cycle,
                details={"cycle": cycle},
            ))

        # Remove duplicate circular dependency errors (same cycle)
        unique_cycle_errors: List[ValidationError] = []
        seen_cycles: Set[str] = set()
        for err in errors:
            if err.code == "CIRCULAR_DEPENDENCY":
                cycle_str = "->".join(sorted(err.related_step_ids or []))
                if cycle_str in seen_cycles:
                    continue
                seen_cycles.add(cycle_str)
            unique_cycle_errors.append(err)

        is_valid = len(unique_cycle_errors) == 0

        return PlanValidationResult(
            is_valid=is_valid,
            errors=unique_cycle_errors,
        )
