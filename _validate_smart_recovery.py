"""
Corax Orchestrator — Smart Recovery Engine Validation.

Validates:
- RetryBudget bounds and cooldown
- evaluate_failure with classified errors
- EscalationLevel progression
- Quarantine management
- Recovery history and state summary
- Safe mode activation
"""

import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

from src.deployment.hardening import SmartRecoveryEngine, RetryBudget, EscalationLevel


def assert_eq(name, actual, expected):
    if actual == expected:
        print(f"  PASS: {name}")
    else:
        print(f"  FAIL: {name} — expected {expected!r}, got {actual!r}")


def assert_true(name, value):
    if value:
        print(f"  PASS: {name}")
    else:
        print(f"  FAIL: {name} — expected True")


def assert_false(name, value):
    if not value:
        print(f"  PASS: {name}")
    else:
        print(f"  FAIL: {name} — expected False")


print("=== SmartRecoveryEngine Validation ===\n")

# =============================================================
# 1. RetryBudget
# =============================================================
print("1. RetryBudget bounds")
budget = RetryBudget()
ok, msg = budget.can_retry("step_a")
assert_true("can_retry initial", ok)

budget.record_retry("step_a")
budget.record_retry("step_a")
budget.record_retry("step_a")
ok, msg = budget.can_retry("step_a")
assert_false("step budget exhausted after 3", ok)
print(f"    msg={msg}")
assert_eq("total_retries_used", budget.total_retries_used, 3)

# Cooldown
budget.activate_cooldown(seconds=1)
ok, msg = budget.can_retry("step_b")
assert_false("cooldown blocks retry", ok)
print()

# =============================================================
# 2. EscalationLevel constants
# =============================================================
print("2. EscalationLevel constants")
assert_eq("NONE", EscalationLevel.NONE, "none")
assert_eq("RETRY", EscalationLevel.RETRY, "retry")
assert_eq("BACKOFF", EscalationLevel.BACKOFF, "backoff")
assert_eq("COOLDOWN", EscalationLevel.COOLDOWN, "cooldown")
assert_eq("QUARANTINE", EscalationLevel.QUARANTINE, "quarantine")
assert_eq("SAFE_MODE", EscalationLevel.SAFE_MODE, "safe_mode")
assert_eq("OPERATOR", EscalationLevel.OPERATOR, "operator")
assert_eq("ABORT", EscalationLevel.ABORT, "abort")
print()

# =============================================================
# 3. SmartRecoveryEngine — evaluate_failure with real Exception
# =============================================================
print("3. evaluate_failure basic")
engine = SmartRecoveryEngine()

# Simulate a network error
error = ConnectionError("Failed to connect to host")
decision = engine.evaluate_failure("download_model", error, {"tool_key": "ollama"})
print(f"    should_retry={decision.should_retry}")
print(f"    retry_delay={decision.retry_delay}s")
print(f"    escalation_level={decision.escalation_level}")
print(f"    actions={len(decision.actions)}")
assert_true("should retry temporary failure", decision.should_retry)
assert_true("retry_delay > 0", decision.retry_delay > 0)
print()

# =============================================================
# 4. Consecutive failures trigger escalation
# =============================================================
print("4. Consecutive failure escalation")
engine2 = SmartRecoveryEngine()
for i in range(5):
    err = ConnectionError(f"Attempt {i+1} failed")
    d = engine2.evaluate_failure("flaky_step", err)

print(f"    After 5 consecutive failures:")
print(f"    should_retry={d.should_retry}")
print(f"    escalation_level={d.escalation_level}")
print(f"    safe_mode={d.safe_mode_activated}")
print(f"    operator_notified={d.operator_notified}")
state = engine2.get_state_summary()
print(f"    consecutive_failures={state['step_consecutive_failures']}")
print()

# =============================================================
# 5. Quarantine after threshold
# =============================================================
print("5. Quarantine activation")
engine3 = SmartRecoveryEngine()
for i in range(engine3.QUARANTINE_THRESHOLD):
    err = ConnectionError(f"Quarantine test {i+1}")
    engine3.evaluate_failure("quarantine_me", err)

state3 = engine3.get_state_summary()
assert_true("step quarantined", "quarantine_me" in state3["quarantined_steps"])
print(f"    quarantined steps: {list(state3['quarantined_steps'].keys())}")
rec_history = engine3.get_recovery_history()
assert_true("recovery history recorded", len(rec_history) > 0)
print()

# =============================================================
# 6. Record success clears quarantine
# =============================================================
print("6. record_success clears quarantine")
engine3.record_success("quarantine_me")
state3b = engine3.get_state_summary()
assert_false("quarantine cleared on success", "quarantine_me" in state3b["quarantined_steps"])
print()

# =============================================================
# 7. Reset
# =============================================================
print("7. Reset")
engine3.reset()
state3c = engine3.get_state_summary()
assert_eq("retry budget reset", state3c["retry_budget"]["total_retries_used"], 0)
assert_eq("quarantine cleared after reset", len(state3c["quarantined_steps"]), 0)
assert_false("safe mode reset", engine3.is_safe_mode())
print()

# =============================================================
# 8. Retry budget exhaustion escalation
# =============================================================
print("8. Budget exhaustion escalation")
engine4 = SmartRecoveryEngine()
engine4._retry_budget = RetryBudget(max_total_retries=2)
error = ConnectionError("Budget test")
d1 = engine4.evaluate_failure("exhaust", error)
d2 = engine4.evaluate_failure("exhaust", error)
d3 = engine4.evaluate_failure("exhaust", error)
assert_false("budget exhausted blocks retry", d3.should_retry)
print(f"    decision 3 escalation={d3.escalation_level}")
print()

print("=== SmartRecoveryEngine Validation COMPLETE ===")
