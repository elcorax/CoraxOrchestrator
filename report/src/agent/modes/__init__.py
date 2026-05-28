"""
Corax Orchestrator - Agent Mode Implementations.

Defines the three agent operation modes:
- Safe: Requires explicit user approval for every action
- Assisted: Auto-executes safe actions, asks for risky ones
- Autonomous: Full autonomy within configured boundaries
"""

from src.agent.modes.base import AgentMode, AgentModeType
from src.agent.modes.safe_mode import SafeMode
from src.agent.modes.assisted_mode import AssistedMode
from src.agent.modes.autonomous_mode import AutonomousMode

__all__ = [
    "AgentMode",
    "AgentModeType",
    "SafeMode",
    "AssistedMode",
    "AutonomousMode",
]
