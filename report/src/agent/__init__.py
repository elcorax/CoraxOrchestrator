"""
Corax Orchestrator - Agent Runtime Layer.

The Agent Runtime provides autonomous execution capabilities for the
Corax Orchestrator. It manages the complete lifecycle of autonomous
deployment tasks including reasoning, planning, execution, recovery,
and AI model integration.

Architecture:
    AgentRuntime (main orchestrator)
    ├── RuntimeEngine (central runtime orchestrator)
    │   ├── LifecycleManager (state machine)
    │   ├── ExecutionLoop (goal-driven execution)
    │   ├── TaskScheduler (priority-based scheduling)
    │   └── RuntimeRecovery (crash recovery)
    ├── AgentModes (safe / assisted / autonomous)
    ├── ExecutionEngine (task execution lifecycle)
    ├── ReasoningEngine (planning & decision-making)
    ├── ToolExecutor (tool invocation)
    ├── AIProviders (LM Studio, Ollama, OpenAI)
    ├── Conversation (history, context, messages)
    ├── SessionManager (session lifecycle)
    └── AgentState (persistent state management)
"""

import importlib.util
import sys
from pathlib import Path

# Import AgentRuntime from the sibling runtime.py module
# (not from the runtime/ package, to avoid naming conflict)
_runtime_file = str(Path(__file__).resolve().parent / "runtime.py")
_spec = importlib.util.spec_from_file_location("src.agent._runtime_mod", _runtime_file)
_runtime_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_runtime_mod)
AgentRuntime = _runtime_mod.AgentRuntime

from src.agent.runtime.engine import RuntimeEngine, RuntimeConfig
from src.agent.runtime.lifecycle import LifecycleManager, LifecycleState, LifecycleEvent
from src.agent.runtime.scheduler import TaskScheduler, TaskPriority, ScheduledTask
from src.agent.runtime.recovery import RuntimeRecovery, RecoveryPoint
from src.agent.runtime.loop import ExecutionLoop
from src.agent.modes.base import AgentMode, AgentModeType
from src.agent.execution.engine import ExecutionEngine
from src.agent.reasoning.engine import ReasoningEngine
from src.agent.state import AgentState
from src.agent.session import SessionManager, AgentSession
from src.agent.providers.base import AIProvider, ProviderConfig, ModelInfo, CompletionResult
from src.agent.providers.registry import ProviderRegistry
from src.agent.conversation.history import ConversationHistory, ConversationEntry
from src.agent.conversation.context import ContextManager, ContextWindow
from src.agent.conversation.messages import Message, MessageRole

__all__ = [
    "AgentRuntime",
    "RuntimeEngine",
    "RuntimeConfig",
    "LifecycleManager",
    "LifecycleState",
    "LifecycleEvent",
    "TaskScheduler",
    "TaskPriority",
    "ScheduledTask",
    "RuntimeRecovery",
    "RecoveryPoint",
    "ExecutionLoop",
    "AgentMode",
    "AgentModeType",
    "ExecutionEngine",
    "ReasoningEngine",
    "AgentState",
    "SessionManager",
    "AgentSession",
    "AIProvider",
    "ProviderConfig",
    "ModelInfo",
    "CompletionResult",
    "ProviderRegistry",
    "ConversationHistory",
    "ConversationEntry",
    "ContextManager",
    "ContextWindow",
    "Message",
    "MessageRole",
]
