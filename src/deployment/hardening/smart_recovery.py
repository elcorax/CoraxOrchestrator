"""
Corax Orchestrator — Smart Recovery Engine Module (Priority 2).

Provides autonomous recovery logic:
- Failure classification routing
- Smart retry selection (bounded)
- Cooldown windows and backoff
- Repeated-failure suppression
- Unstable dependency quarantine
- Recovery escalation logic
- Graceful degradation
- Structured diagnostics

Requirements:
- Bounded retries only (no infinite loops)
- Never crash deployment
- Always produce structured diagnostics
"""

from typing import Dict, Any, List, Optional, Tuple, Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
import json
import os
import time
import traceback

from src.core.logging import get_logger
from src.deployment.operations import FailureCategory
from src.deployment.hardening.failure_classifier import (
    InstallerFailureClassifier,
    FailureAnalysisResult,
    RepairScript,
)

logger = get_logger(__name__)


# ------------------------------------------------------------------
# Data Types
# ------------------------------------------------------------------

@dataclass
class RetryBudget:
    """Bounded retry budget for a deployment session."""
    max_total_retries: int = 10
    max_retries_per_step: int = 3
    total_retries_used: int = 0
    step_retries_used: Dict[str, int] = field(default_factory=dict)
    cooldown_active: bool = False
    cooldown_until: Optional[datetime] = None

    def can_retry(self, step_name: str) -> Tuple[bool, str]:
        """Check if retry is allowed within budget."""
        if self.cooldown_active and self.cooldown_until:
            if datetime.now(timezone.utc) < self.cooldown_until:
                return False, "Global cooldown active"
            self.cooldown_active = False
            self.cooldown_until = None

        if self.total_retries_used >= self.max_total_retries:
            return False, f"Total retry budget exhausted ({self.max_total_retries})"

        step_used = self.step_retries_used.get(step_name, 0)
        if step_used >= self.max_retries_per_step:
            return False, (
                f"Step '{step_name}' retry budget exhausted "
                f"({self.max_retries_per_step})"
            )

        return True, ""

    def record_retry(self, step_name: str) -> None:
        """Record that a retry was used."""
        self.total_retries_used += 1
        self.step_retries_used[step_name] = (
            self.step_retries_used.get(step_name, 0) + 1
        )

    def activate_cooldown(self, seconds: int = 30) -> None:
        """Activate global retry cooldown."""
        self.cooldown_active = True
        self.cooldown_until = datetime.now(timezone.utc) + timedelta(seconds=seconds)
        logger.info(f"Retry cooldown activated for {seconds}s")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "max_total_retries": self.max_total_retries,
            "max_retries_per_step": self.max_retries_per_step,
            "total_retries_used": self.total_retries_used,
            "total_remaining": self.max_total_retries - self.total_retries_used,
            "step_retries_used": dict(self.step_retries_used),
            "cooldown_active": self.cooldown_active,
            "cooldown_until": self.cooldown_until.isoformat() if self.cooldown_until else None,
        }


class EscalationLevel:
    """Escalation levels for recovery actions."""
    NONE = "none"
    RETRY = "retry"
    BACKOFF = "backoff"
    COOLDOWN = "cooldown"
    QUARANTINE = "quarantine"
    SAFE_MODE = "safe_mode"
    OPERATOR = "operator"
    ABORT = "abort"


@dataclass
class RecoveryAction:
    """A single recovery action to take."""
    level: str  # EscalationLevel
    action: str  # Human-readable description
    delay_seconds: float = 0.0
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "level": self.level,
            "action": self.action,
            "delay_seconds": self.delay_seconds,
            "details": self.details,
        }


@dataclass
class RecoveryDecision:
    """Decision made by the smart recovery engine."""
    should_retry: bool = False
    retry_delay: float = 0.0
    escalation_level: str = EscalationLevel.NONE
    actions: List[RecoveryAction] = field(default_factory=list)
    step_quarantined: bool = False
    safe_mode_activated: bool = False
    operator_notified: bool = False
    errors: List[str] = field(default_factory=list)
    diagnostics: Dict[str, Any] = field(default_factory=dict)
    duration_ms: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "should_retry": self.should_retry,
            "retry_delay": self.retry_delay,
            "escalation_level": self.escalation_level,
            "actions": [a.to_dict() for a in self.actions],
            "step_quarantined": self.step_quarantined,
            "safe_mode_activated": self.safe_mode_activated,
            "operator_notified": self.operator_notified,
            "errors": self.errors,
            "diagnostics": self.diagnostics,
        }


# ------------------------------------------------------------------
# Smart Recovery Engine
# ------------------------------------------------------------------

class SmartRecoveryEngine:
    """
    Autonomous recovery engine with smart retry and escalation.

    Features:
    - Failure classification routing (via failure_classifier)
    - Smart retry selection with bounded budgets
    - Cooldown windows to prevent retry storms
    - Repeated-failure suppression and quarantine
    - Unstable dependency quarantine
    - Recovery escalation (retry -> backoff -> cooldown -> safe mode -> operator)
    - Structured diagnostics for every decision
    """

    # Quarantine: steps that fail repeatedly get quarantined
    QUARANTINE_THRESHOLD = 3  # failures before quarantine
    QUARANTINE_DURATION_SECONDS = 120  # how long quarantine lasts

    # Cooldown parameters
    COOLDOWN_BASE_SECONDS = 15
    COOLDOWN_MAX_SECONDS = 120

    def __init__(
        self,
        failure_classifier: Optional[InstallerFailureClassifier] = None,
    ):
        self._failure_classifier = failure_classifier or InstallerFailureClassifier()
        self._retry_budget = RetryBudget()
        self._quarantined_steps: Dict[str, datetime] = {}
        self._step_failure_counts: Dict[str, int] = {}
        self._step_consecutive_failures: Dict[str, int] = {}
        self._recovery_history: List[Dict[str, Any]] = []
        self._safe_mode: bool = False
        self._last_recovery_time: Optional[datetime] = None

    # ------------------------------------------------------------------
    # Core Recovery Decision
    # ------------------------------------------------------------------

    def evaluate_failure(
        self,
        step_name: str,
        error: Exception,
        failure_context: Optional[Dict[str, Any]] = None,
    ) -> RecoveryDecision:
        """
        Evaluate a failure and determine the best recovery action.

        This is the main entry point. It classifies the failure,
        checks budgets and quarantines, then returns a decision.

        Args:
            step_name: Name of the failing deployment step
            error: The exception that occurred
            failure_context: Optional context (tool_key, session_id, etc.)

        Returns:
            RecoveryDecision with retry/delay/escalation info
        """
        start = time.time()
        decision = RecoveryDecision()

        try:
            # 1. Classify the failure
            # Extract error details for the classifier
            error_msg = str(error)
            context = failure_context or {}
            tool_key = context.get("tool_key", "unknown")
            failure_result = self._failure_classifier.analyze(
                tool_key=tool_key,
                exit_code=context.get("exit_code", -1),
                stderr=error_msg,
                error_message=error_msg,
                context=context,
            )

            decision.diagnostics["failure_analysis"] = failure_result.to_dict()
            decision.diagnostics["failure_category"] = failure_result.failure_category

            # 2. Update failure tracking
            self._step_failure_counts[step_name] = (
                self._step_failure_counts.get(step_name, 0) + 1
            )
            self._step_consecutive_failures[step_name] = (
                self._step_consecutive_failures.get(step_name, 0) + 1
            )

            # 3. Check quarantine
            if self._is_quarantined(step_name):
                decision.should_retry = False
                decision.escalation_level = EscalationLevel.QUARANTINE
                decision.actions.append(RecoveryAction(
                    level=EscalationLevel.QUARANTINE,
                    action=f"Step '{step_name}' is quarantined. Skipping.",
                    details={"quarantine_duration_remaining": self._quarantine_remaining(step_name)},
                ))
                decision.diagnostics["quarantine_remaining"] = self._quarantine_remaining(step_name)
                decision.duration_ms = (time.time() - start) * 1000
                self._record_recovery(step_name, decision)
                return decision

            # 4. Auto-quarantine if threshold exceeded (check BEFORE retry budget)
            if self._step_consecutive_failures[step_name] >= self.QUARANTINE_THRESHOLD:
                self._quarantine_step(step_name)
                decision.step_quarantined = True
                decision.should_retry = False
                decision.escalation_level = EscalationLevel.QUARANTINE
                decision.actions.append(RecoveryAction(
                    level=EscalationLevel.QUARANTINE,
                    action=f"Step '{step_name}' quarantined after {self.QUARANTINE_THRESHOLD} consecutive failures",
                ))
                decision.duration_ms = (time.time() - start) * 1000
                self._record_recovery(step_name, decision)
                return decision

            # 5. Check retry budget
            can_retry, budget_msg = self._retry_budget.can_retry(step_name)
            if not can_retry:
                decision.should_retry = False
                decision.errors.append(budget_msg)
                decision.diagnostics["budget_exhausted"] = True

                # Escalate
                escalation = self._determine_escalation(
                    step_name, failure_result
                )
                decision.escalation_level = escalation
                decision.actions.append(RecoveryAction(
                    level=escalation,
                    action=f"Retry budget exhausted: {budget_msg}",
                ))

                if escalation == EscalationLevel.SAFE_MODE:
                    self._safe_mode = True
                    decision.safe_mode_activated = True
                elif escalation == EscalationLevel.OPERATOR:
                    decision.operator_notified = True

                decision.duration_ms = (time.time() - start) * 1000
                self._record_recovery(step_name, decision)
                return decision

            # 6. Determine retry strategy based on failure category
            retry_strategy = self._select_retry_strategy(step_name, failure_result)
            decision.should_retry = retry_strategy["should_retry"]
            decision.retry_delay = retry_strategy["delay_seconds"]

            if decision.should_retry:
                # Record the retry in budget
                self._retry_budget.record_retry(step_name)

                # Apply cooldown if needed
                if retry_strategy.get("use_cooldown", False):
                    self._retry_budget.activate_cooldown(
                        seconds=retry_strategy.get("cooldown_seconds", 30)
                    )

                decision.actions.append(RecoveryAction(
                    level=EscalationLevel.RETRY,
                    action=(
                        f"Retrying step '{step_name}' "
                        f"in {decision.retry_delay:.0f}s "
                        f"(budget: {self._retry_budget.total_retries_used}/"
                        f"{self._retry_budget.max_total_retries})"
                    ),
                    details={
                        "delay": decision.retry_delay,
                        "budget_remaining": (
                            self._retry_budget.max_total_retries
                            - self._retry_budget.total_retries_used
                        ),
                        "consecutive_failures": self._step_consecutive_failures[step_name],
                    },
                ))
            else:
                # Non-retryable failure
                escalation = self._determine_escalation(
                    step_name, failure_result
                )
                decision.escalation_level = escalation
                decision.actions.append(RecoveryAction(
                    level=escalation,
                    action=f"Non-retryable failure: {failure_result.failure_category}",
                ))

                if escalation == EscalationLevel.SAFE_MODE:
                    self._safe_mode = True
                    decision.safe_mode_activated = True
                elif escalation == EscalationLevel.OPERATOR:
                    decision.operator_notified = True

        except Exception as e:
            # Never let the recovery engine itself crash
            decision.errors.append(f"Recovery engine internal error: {e}")
            decision.should_retry = False
            decision.escalation_level = EscalationLevel.SAFE_MODE
            self._safe_mode = True
            decision.safe_mode_activated = True
            logger.error(f"SmartRecoveryEngine internal error: {e}")

        decision.duration_ms = (time.time() - start) * 1000
        self._record_recovery(step_name, decision)
        return decision

    def record_success(self, step_name: str) -> None:
        """Record a successful step execution (resets consecutive failures)."""
        self._step_consecutive_failures[step_name] = 0
        # Clear from quarantine on success
        if step_name in self._quarantined_steps:
            del self._quarantined_steps[step_name]
            logger.info(f"Step '{step_name}' removed from quarantine (success)")

    # ------------------------------------------------------------------
    # Retry Strategy Selection
    # ------------------------------------------------------------------

    def _select_retry_strategy(
        self, step_name: str, failure_result: FailureAnalysisResult
    ) -> Dict[str, Any]:
        """
        Select the best retry strategy based on failure classification.

        Returns dict with:
            should_retry: bool
            delay_seconds: float
            use_cooldown: bool
            cooldown_seconds: int
        """
        category = failure_result.failure_category

        # Temporary failures (network, timeout) -> retry with backoff
        if category in (FailureCategory.TEMPORARY, FailureCategory.TIMEOUT, FailureCategory.NETWORK):
            consecutive = self._step_consecutive_failures.get(step_name, 0)
            delay = min(
                self.COOLDOWN_BASE_SECONDS * (2 ** (consecutive)),
                self.COOLDOWN_MAX_SECONDS,
            )
            return {
                "should_retry": True,
                "delay_seconds": delay,
                "use_cooldown": consecutive >= 2,
                "cooldown_seconds": int(delay * 2),
            }

        # Permission failures -> limited retries, then escalate
        if category == FailureCategory.PERMISSION:
            consecutive = self._step_consecutive_failures.get(step_name, 0)
            if consecutive < 2:
                return {
                    "should_retry": True,
                    "delay_seconds": 2.0,
                    "use_cooldown": False,
                    "cooldown_seconds": 0,
                }
            else:
                return {
                    "should_retry": False,
                    "delay_seconds": 0,
                    "use_cooldown": False,
                    "cooldown_seconds": 0,
                }

        # Dependency failures -> retry with longer backoff
        if category == FailureCategory.DEPENDENCY:
            return {
                "should_retry": True,
                "delay_seconds": 10.0,
                "use_cooldown": True,
                "cooldown_seconds": 30,
            }

        # Disk space -> retry once (might be freed), then escalate
        if category == FailureCategory.DISK_SPACE:
            return {
                "should_retry": True,
                "delay_seconds": 5.0,
                "use_cooldown": False,
                "cooldown_seconds": 0,
            }

        # Corruption -> retry once with fresh download
        if category == FailureCategory.CORRUPTION:
            return {
                "should_retry": True,
                "delay_seconds": 3.0,
                "use_cooldown": False,
                "cooldown_seconds": 0,
            }

        # Compatibility -> no retry, escalate immediately
        if category == FailureCategory.COMPATIBILITY:
            return {
                "should_retry": False,
                "delay_seconds": 0,
                "use_cooldown": False,
                "cooldown_seconds": 0,
            }

        # Unknown -> retry once conservatively
        return {
            "should_retry": True,
            "delay_seconds": 5.0,
            "use_cooldown": True,
            "cooldown_seconds": 30,
        }

    # ------------------------------------------------------------------
    # Escalation Logic
    # ------------------------------------------------------------------

    def _determine_escalation(
        self,
        step_name: str,
        failure_result: FailureAnalysisResult,
    ) -> str:
        """
        Determine escalation level when retry is not possible.

        Progression: none -> retry -> backoff -> cooldown -> safe_mode -> operator -> abort
        """
        consecutive = self._step_consecutive_failures.get(step_name, 0)
        total_failures = self._step_failure_counts.get(step_name, 0)

        # Multiple failures across steps -> safe mode
        total_steps_with_failures = len([
            s for s, c in self._step_failure_counts.items() if c > 0
        ])
        if total_steps_with_failures >= 3 and self._safe_mode:
            return EscalationLevel.OPERATOR

        # Consecutive failures escalate
        if consecutive >= 5:
            return EscalationLevel.ABORT
        elif consecutive >= 4:
            return EscalationLevel.OPERATOR
        elif consecutive >= 3:
            return EscalationLevel.SAFE_MODE
        elif consecutive >= 2:
            return EscalationLevel.COOLDOWN

        # By failure category
        if failure_result.failure_category in (FailureCategory.COMPATIBILITY, FailureCategory.PERMISSION):
            return EscalationLevel.OPERATOR
        elif failure_result.failure_category == FailureCategory.DISK_SPACE:
            return EscalationLevel.SAFE_MODE
        elif failure_result.failure_category == FailureCategory.CORRUPTION:
            return EscalationLevel.COOLDOWN

        return EscalationLevel.RETRY

    # ------------------------------------------------------------------
    # Quarantine Management
    # ------------------------------------------------------------------

    def _is_quarantined(self, step_name: str) -> bool:
        """Check if a step is currently quarantined."""
        if step_name not in self._quarantined_steps:
            return False
        expiry = self._quarantined_steps[step_name]
        if datetime.now(timezone.utc) < expiry:
            return True
        # Quarantine expired
        del self._quarantined_steps[step_name]
        self._step_consecutive_failures[step_name] = 0
        logger.info(f"Quarantine expired for step '{step_name}'")
        return False

    def _quarantine_remaining(self, step_name: str) -> float:
        """Get remaining quarantine time in seconds."""
        if step_name not in self._quarantined_steps:
            return 0.0
        remaining = (
            self._quarantined_steps[step_name] - datetime.now(timezone.utc)
        ).total_seconds()
        return max(0.0, remaining)

    def _quarantine_step(self, step_name: str) -> None:
        """Add a step to quarantine."""
        expiry = datetime.now(timezone.utc) + timedelta(
            seconds=self.QUARANTINE_DURATION_SECONDS
        )
        self._quarantined_steps[step_name] = expiry
        logger.warning(
            f"Step '{step_name}' quarantined for "
            f"{self.QUARANTINE_DURATION_SECONDS}s"
        )

    # ------------------------------------------------------------------
    # Diagnostics & State
    # ------------------------------------------------------------------

    def _record_recovery(
        self, step_name: str, decision: RecoveryDecision
    ) -> None:
        """Record a recovery attempt in history."""
        self._recovery_history.append({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "step_name": step_name,
            "decision": decision.to_dict(),
        })
        self._last_recovery_time = datetime.now(timezone.utc)

    def get_recovery_history(
        self, max_records: int = 50
    ) -> List[Dict[str, Any]]:
        """Get recovery history, newest first."""
        return list(reversed(self._recovery_history[-max_records:]))

    def get_state_summary(self) -> Dict[str, Any]:
        """Get a summary of the current recovery engine state."""
        return {
            "safe_mode": self._safe_mode,
            "retry_budget": self._retry_budget.to_dict(),
            "quarantined_steps": {
                step: expiry.isoformat()
                for step, expiry in self._quarantined_steps.items()
            },
            "step_failure_counts": dict(self._step_failure_counts),
            "step_consecutive_failures": dict(self._step_consecutive_failures),
            "total_recovery_attempts": len(self._recovery_history),
            "last_recovery_time": (
                self._last_recovery_time.isoformat()
                if self._last_recovery_time else None
            ),
        }

    def get_retry_budget_remaining(self) -> int:
        """Get remaining retry budget."""
        return (
            self._retry_budget.max_total_retries
            - self._retry_budget.total_retries_used
        )

    def reset(self) -> None:
        """Reset the recovery engine state for a new session."""
        self._retry_budget = RetryBudget()
        self._quarantined_steps.clear()
        self._step_failure_counts.clear()
        self._step_consecutive_failures.clear()
        self._safe_mode = False
        logger.info("SmartRecoveryEngine reset for new session")

    def is_safe_mode(self) -> bool:
        """Check if the engine has activated safe mode."""
        return self._safe_mode
