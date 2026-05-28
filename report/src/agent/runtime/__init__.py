"""
Corax Orchestrator - Agent Runtime Package.

The runtime package provides the core execution infrastructure for the
autonomous agent system. It manages the complete lifecycle of agent
operations including session management, execution loops, and lifecycle
events.

Architecture:
    runtime/
    ├── __init__.py          # Package exports
    ├── engine.py            # Core execution engine with lifecycle
    ├── loop.py              # Autonomous execution loop
    ├── lifecycle.py         # Lifecycle event management
    ├── scheduler.py         # Task scheduling and prioritization
    └── recovery.py          # Runtime recovery and restart support
"""

from src.agent.runtime.engine import RuntimeEngine
from src.agent.runtime.loop import ExecutionLoop
from src.agent.runtime.lifecycle import LifecycleManager, LifecycleEvent, LifecycleState
from src.agent.runtime.scheduler import TaskScheduler, ScheduledTask, TaskPriority
from src.agent.runtime.recovery import RuntimeRecovery, RecoveryPoint

__all__ = [
    "RuntimeEngine",
    "ExecutionLoop",
    "LifecycleManager",
    "LifecycleEvent",
    "LifecycleState",
    "TaskScheduler",
    "ScheduledTask",
    "TaskPriority",
    "RuntimeRecovery",
    "RecoveryPoint",
]
