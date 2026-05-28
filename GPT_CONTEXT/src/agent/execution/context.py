"""
Corax Orchestrator - Execution Context.

Provides the execution context for workflow steps, including
variable storage, tool access, and environment information.
"""

from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Set
from datetime import datetime, timezone

from src.core.logging import get_logger

logger = get_logger(__name__)


@dataclass
class ExecutionContext:
    """
    Execution context for a running workflow.

    Provides:
    - Variable storage (scoped to workflow)
    - Tool access references
    - Environment information
    - Step result caching
    - Configuration access
    """

    workflow_id: str
    variables: Dict[str, Any] = field(default_factory=dict)
    step_results: Dict[str, Any] = field(default_factory=dict)
    environment: Dict[str, Any] = field(default_factory=dict)
    configuration: Dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def set_variable(self, name: str, value: Any) -> None:
        """Set a workflow variable."""
        self.variables[name] = value
        logger.debug("Variable set", name=name, workflow=self.workflow_id)

    def get_variable(self, name: str, default: Any = None) -> Any:
        """Get a workflow variable."""
        return self.variables.get(name, default)

    def store_step_result(self, step_id: str, result: Any) -> None:
        """Store the result of a completed step."""
        self.step_results[step_id] = result

    def get_step_result(self, step_id: str) -> Any:
        """Get the result of a completed step."""
        return self.step_results.get(step_id)

    def get_environment_value(self, key: str, default: Any = None) -> Any:
        """Get an environment value."""
        return self.environment.get(key, default)

    def get_config(self, key: str, default: Any = None) -> Any:
        """Get a configuration value."""
        return self.configuration.get(key, default)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "workflow_id": self.workflow_id,
            "variables": self.variables,
            "environment": self.environment,
            "created_at": self.created_at,
        }
