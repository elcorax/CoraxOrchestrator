"""
Corax Orchestrator - Lifecycle Manager.

Manages the complete lifecycle of the agent runtime including state
transitions, lifecycle events, and lifecycle hooks for extensibility.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum, auto
from typing import Dict, Any, List, Optional, Callable, Awaitable, Set
from uuid import uuid4

from src.core.logging import get_logger

logger = get_logger(__name__)


class LifecycleState(Enum):
    """Possible states in the agent runtime lifecycle."""
    CREATED = "created"
    INITIALIZING = "initializing"
    IDLE = "idle"
    RUNNING = "running"
    PAUSED = "paused"
    WAITING_FOR_INPUT = "waiting_for_input"
    ERROR = "error"
    RECOVERING = "recovering"
    SHUTTING_DOWN = "shutting_down"
    TERMINATED = "terminated"


class LifecycleEvent(Enum):
    """Events that trigger lifecycle state transitions."""
    # Startup events
    INIT = "init"
    START = "start"
    READY = "ready"

    # Execution events
    EXECUTE = "execute"
    COMPLETE = "complete"
    FAIL = "fail"

    # Control events
    PAUSE = "pause"
    RESUME = "resume"
    CANCEL = "cancel"
    RESTART = "restart"

    # Input events
    INPUT_REQUIRED = "input_required"
    INPUT_RECEIVED = "input_received"

    # Recovery events
    ERROR = "error"
    RECOVER = "recover"
    RECOVERY_FAILED = "recovery_failed"

    # Shutdown events
    SHUTDOWN = "shutdown"
    TERMINATE = "terminate"
    FORCE_TERMINATE = "force_terminate"


# State transition map: (current_state, event) -> new_state
STATE_TRANSITIONS: Dict[tuple, LifecycleState] = {
    # Startup flow
    (LifecycleState.CREATED, LifecycleEvent.INIT): LifecycleState.INITIALIZING,
    (LifecycleState.INITIALIZING, LifecycleEvent.START): LifecycleState.RUNNING,
    (LifecycleState.INITIALIZING, LifecycleEvent.READY): LifecycleState.IDLE,
    (LifecycleState.INITIALIZING, LifecycleEvent.FAIL): LifecycleState.ERROR,

    # Idle -> Running
    (LifecycleState.IDLE, LifecycleEvent.EXECUTE): LifecycleState.RUNNING,
    (LifecycleState.IDLE, LifecycleEvent.SHUTDOWN): LifecycleState.SHUTTING_DOWN,

    # Running transitions
    (LifecycleState.RUNNING, LifecycleEvent.COMPLETE): LifecycleState.IDLE,
    (LifecycleState.RUNNING, LifecycleEvent.FAIL): LifecycleState.ERROR,
    (LifecycleState.RUNNING, LifecycleEvent.PAUSE): LifecycleState.PAUSED,
    (LifecycleState.RUNNING, LifecycleEvent.CANCEL): LifecycleState.IDLE,
    (LifecycleState.RUNNING, LifecycleEvent.INPUT_REQUIRED): LifecycleState.WAITING_FOR_INPUT,

    # Paused transitions
    (LifecycleState.PAUSED, LifecycleEvent.RESUME): LifecycleState.RUNNING,
    (LifecycleState.PAUSED, LifecycleEvent.CANCEL): LifecycleState.IDLE,
    (LifecycleState.PAUSED, LifecycleEvent.SHUTDOWN): LifecycleState.SHUTTING_DOWN,

    # Waiting for input transitions
    (LifecycleState.WAITING_FOR_INPUT, LifecycleEvent.INPUT_RECEIVED): LifecycleState.RUNNING,
    (LifecycleState.WAITING_FOR_INPUT, LifecycleEvent.CANCEL): LifecycleState.IDLE,

    # Error/Recovery transitions
    (LifecycleState.ERROR, LifecycleEvent.RECOVER): LifecycleState.RECOVERING,
    (LifecycleState.ERROR, LifecycleEvent.CANCEL): LifecycleState.IDLE,
    (LifecycleState.ERROR, LifecycleEvent.SHUTDOWN): LifecycleState.SHUTTING_DOWN,
    (LifecycleState.RECOVERING, LifecycleEvent.READY): LifecycleState.IDLE,
    (LifecycleState.RECOVERING, LifecycleEvent.RECOVERY_FAILED): LifecycleState.ERROR,
    (LifecycleState.RECOVERING, LifecycleEvent.SHUTDOWN): LifecycleState.SHUTTING_DOWN,

    # Shutdown transitions
    (LifecycleState.SHUTTING_DOWN, LifecycleEvent.TERMINATE): LifecycleState.TERMINATED,
    (LifecycleState.SHUTTING_DOWN, LifecycleEvent.FORCE_TERMINATE): LifecycleState.TERMINATED,
    (LifecycleState.SHUTTING_DOWN, LifecycleEvent.FAIL): LifecycleState.ERROR,

    # Direct transitions (from any state)
    (LifecycleState.CREATED, LifecycleEvent.TERMINATE): LifecycleState.TERMINATED,
    (LifecycleState.IDLE, LifecycleEvent.TERMINATE): LifecycleState.TERMINATED,
    (LifecycleState.RUNNING, LifecycleEvent.TERMINATE): LifecycleState.TERMINATED,
    (LifecycleState.PAUSED, LifecycleEvent.TERMINATE): LifecycleState.TERMINATED,
    (LifecycleState.ERROR, LifecycleEvent.TERMINATE): LifecycleState.TERMINATED,
    (LifecycleState.RECOVERING, LifecycleEvent.TERMINATE): LifecycleState.TERMINATED,
    (LifecycleState.WAITING_FOR_INPUT, LifecycleEvent.TERMINATE): LifecycleState.TERMINATED,
}


@dataclass
class LifecycleTransition:
    """Record of a lifecycle state transition."""
    from_state: LifecycleState
    to_state: LifecycleState
    event: LifecycleEvent
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    reason: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "from_state": self.from_state.value,
            "to_state": self.to_state.value,
            "event": self.event.value,
            "timestamp": self.timestamp,
            "reason": self.reason,
        }


class LifecycleManager:
    """
    Manages the agent runtime lifecycle with state machine semantics.

    Features:
    - Formal state machine with validated transitions
    - Lifecycle event hooks for extensibility
    - Transition history for auditing
    - Forced state transitions for error recovery
    - Concurrent state change safety
    """

    def __init__(self, initial_state: LifecycleState = LifecycleState.CREATED) -> None:
        self._state: LifecycleState = initial_state
        self._transitions: List[LifecycleTransition] = []
        self._hooks: Dict[LifecycleEvent, List[Callable[..., Awaitable[None]]]] = {}
        self._state_hooks: Dict[LifecycleState, List[Callable[..., Awaitable[None]]]] = {}
        self._locked: bool = False

        logger.info("Lifecycle manager initialized", state=self._state.value)

    @property
    def state(self) -> LifecycleState:
        """Get the current lifecycle state."""
        return self._state

    @property
    def state_name(self) -> str:
        """Get the current state name as a string."""
        return self._state.value

    @property
    def is_active(self) -> bool:
        """Check if the runtime is in an active state."""
        return self._state in (
            LifecycleState.RUNNING,
            LifecycleState.PAUSED,
            LifecycleState.WAITING_FOR_INPUT,
            LifecycleState.RECOVERING,
        )

    @property
    def is_running(self) -> bool:
        """Check if the runtime is currently executing."""
        return self._state == LifecycleState.RUNNING

    @property
    def is_idle(self) -> bool:
        """Check if the runtime is idle."""
        return self._state == LifecycleState.IDLE

    @property
    def is_terminated(self) -> bool:
        """Check if the runtime has been terminated."""
        return self._state == LifecycleState.TERMINATED

    @property
    def can_execute(self) -> bool:
        """Check if the runtime can accept execution requests."""
        return self._state in (LifecycleState.IDLE, LifecycleState.RUNNING)

    async def transition(
        self,
        event: LifecycleEvent,
        reason: str = "",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> LifecycleState:
        """
        Attempt a lifecycle state transition.

        Args:
            event: The event triggering the transition
            reason: Human-readable reason for the transition
            metadata: Additional context for the transition

        Returns:
            The new lifecycle state

        Raises:
            ValueError: If the transition is not valid
        """
        if self._locked and event != LifecycleEvent.FORCE_TERMINATE:
            raise ValueError(
                f"Cannot transition from {self._state.value} via {event.value}: "
                f"lifecycle is locked"
            )

        key = (self._state, event)
        new_state = STATE_TRANSITIONS.get(key)

        if new_state is None:
            raise ValueError(
                f"Invalid transition: {self._state.value} -> {event.value}. "
                f"Valid events from {self._state.value}: "
                f"{[e.value for s, e in STATE_TRANSITIONS if s == self._state]}"
            )

        old_state = self._state
        self._state = new_state

        transition = LifecycleTransition(
            from_state=old_state,
            to_state=new_state,
            event=event,
            reason=reason,
            metadata=metadata or {},
        )
        self._transitions.append(transition)

        logger.info(
            "Lifecycle transition",
            from_state=old_state.value,
            to_state=new_state.value,
            event=event.value,
            reason=reason,
        )

        # Fire event hooks
        await self._fire_event_hooks(event, transition)

        # Fire state hooks
        await self._fire_state_hooks(new_state, transition)

        return new_state

    async def force_transition(
        self,
        target_state: LifecycleState,
        reason: str = "Forced transition",
    ) -> LifecycleState:
        """
        Force a state transition regardless of validity.

        This should only be used for emergency recovery scenarios.

        Args:
            target_state: The state to force-enter
            reason: Reason for the forced transition

        Returns:
            The new lifecycle state
        """
        old_state = self._state
        self._state = target_state

        transition = LifecycleTransition(
            from_state=old_state,
            to_state=target_state,
            event=LifecycleEvent.RECOVER,
            reason=reason,
            metadata={"forced": True},
        )
        self._transitions.append(transition)

        logger.warning(
            "Forced lifecycle transition",
            from_state=old_state.value,
            to_state=target_state.value,
            reason=reason,
        )

        await self._fire_state_hooks(target_state, transition)
        return target_state

    def on_event(
        self,
        event: LifecycleEvent,
        hook: Callable[..., Awaitable[None]],
    ) -> None:
        """
        Register a hook that fires when a specific event occurs.

        Args:
            event: The event to hook into
            hook: Async callback receiving (transition) as argument
        """
        if event not in self._hooks:
            self._hooks[event] = []
        self._hooks[event].append(hook)

    def on_state(
        self,
        state: LifecycleState,
        hook: Callable[..., Awaitable[None]],
    ) -> None:
        """
        Register a hook that fires when entering a specific state.

        Args:
            state: The state to hook into
            hook: Async callback receiving (transition) as argument
        """
        if state not in self._state_hooks:
            self._state_hooks[state] = []
        self._state_hooks[state].append(hook)

    def lock(self) -> None:
        """Lock the lifecycle to prevent transitions."""
        self._locked = True
        logger.debug("Lifecycle locked")

    def unlock(self) -> None:
        """Unlock the lifecycle to allow transitions."""
        self._locked = False
        logger.debug("Lifecycle unlocked")

    def get_transition_history(
        self,
        limit: Optional[int] = None,
    ) -> List[LifecycleTransition]:
        """
        Get the lifecycle transition history.

        Args:
            limit: Maximum number of transitions to return

        Returns:
            List of LifecycleTransition records
        """
        history = list(self._transitions)
        if limit:
            history = history[-limit:]
        return history

    def get_transition_count(self) -> int:
        """Get the total number of transitions."""
        return len(self._transitions)

    def can_transition_to(self, state: LifecycleState) -> bool:
        """Check if a transition to the given state is valid."""
        return any(
            (self._state, event) in STATE_TRANSITIONS
            and STATE_TRANSITIONS[(self._state, event)] == state
            for event in LifecycleEvent
        )

    def valid_events(self) -> List[LifecycleEvent]:
        """Get all valid events from the current state."""
        return [
            event
            for event in LifecycleEvent
            if (self._state, event) in STATE_TRANSITIONS
        ]

    def to_dict(self) -> Dict[str, Any]:
        """Serialize lifecycle state to dictionary."""
        return {
            "current_state": self._state.value,
            "is_active": self.is_active,
            "is_running": self.is_running,
            "is_idle": self.is_idle,
            "is_terminated": self.is_terminated,
            "can_execute": self.can_execute,
            "total_transitions": len(self._transitions),
            "locked": self._locked,
            "valid_events": [e.value for e in self.valid_events()],
            "last_transition": (
                self._transitions[-1].to_dict() if self._transitions else None
            ),
        }

    async def _fire_event_hooks(
        self,
        event: LifecycleEvent,
        transition: LifecycleTransition,
    ) -> None:
        """Fire all hooks registered for a specific event."""
        hooks = self._hooks.get(event, [])
        for hook in hooks:
            try:
                await hook(transition)
            except Exception as e:
                logger.error(
                    "Lifecycle event hook failed",
                    event=event.value,
                    error=str(e),
                )

    async def _fire_state_hooks(
        self,
        state: LifecycleState,
        transition: LifecycleTransition,
    ) -> None:
        """Fire all hooks registered for a specific state."""
        hooks = self._state_hooks.get(state, [])
        for hook in hooks:
            try:
                await hook(transition)
            except Exception as e:
                logger.error(
                    "Lifecycle state hook failed",
                    state=state.value,
                    error=str(e),
                )
