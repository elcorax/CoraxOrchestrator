"""
Corax Orchestrator — Deployment Visibility Dashboard Validation.

Validates:
- create_phase_progress calculation
- create_health_indicator generation
- create_risk_indicator generation
- calculate_throughput metrics
- estimate_completion ETA
- create_retry_summary
- create_recovery_summary
- create_snapshot with overall status
- get_status_string one-liner
- get_health_summary
- get_risk_summary
- get_progress_summary
"""

import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

from src.deployment.hardening import DeploymentVisibilityDashboard


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


print("=== DeploymentVisibilityDashboard Validation ===\n")

dash = DeploymentVisibilityDashboard()

# =============================================================
# 1. Phase Progress
# =============================================================
print("1. Phase Progress")
phase = dash.create_phase_progress("install_tools", "running", 3, 10, current_step="ollama")
assert_eq("phase_name", phase.phase_name, "install_tools")
assert_eq("status", phase.status, "running")
assert_eq("progress_pct", int(phase.progress_pct), 30)  # 3/10 = 30%
assert_eq("current_step", phase.current_step, "ollama")
assert_eq("completed_steps", phase.completed_steps, 3)
assert_eq("total_steps", phase.total_steps, 10)
print(f"    progress={phase.progress_pct}%  steps={phase.completed_steps}/{phase.total_steps}")
print()

# =============================================================
# 2. Health Indicator
# =============================================================
print("2. Health Indicator")
hi = dash.create_health_indicator("ollama_installer", "healthy")
assert_eq("component", hi.component, "ollama_installer")
assert_eq("status", hi.status, "healthy")
print(f"    {hi.component}: {hi.status}")
print()

# =============================================================
# 3. Risk Indicator
# =============================================================
print("3. Risk Indicator")
ri = dash.create_risk_indicator("low_disk", "high", "Only 2GB free", "Free up disk space")
assert_eq("risk", ri.risk, "low_disk")
assert_eq("level", ri.level, "high")
print(f"    {ri.risk}: {ri.level}")
print()

# =============================================================
# 4. Throughput
# =============================================================
print("4. Throughput")
tp = dash.calculate_throughput(10, 60.0)  # 10 items in 60s = 10/min
assert_true("rate > 0", tp["rate_per_minute"] > 0)
assert_eq("rate_per_minute (10/60s)", round(tp["rate_per_minute"], 1), 10.0)
print(f"    {tp['rate_per_minute']} {tp['item_name']}/minute")
print()

# =============================================================
# 5. ETA
# =============================================================
print("5. ETA")
eta = dash.estimate_completion(100, 25, 50.0)  # 25/100 in 50s
assert_eq("remaining_steps", eta["remaining_steps"], 75)
assert_eq("progress_pct", eta["progress_pct"], 25.0)
assert_true("estimated_remaining_seconds > 0", eta.get("estimated_remaining_seconds", 0) > 0)
print(f"    {eta['progress_pct']}% complete, ~{eta.get('estimated_remaining_seconds', 0):.0f}s remaining")
print()

# =============================================================
# 6. Retry Summary
# =============================================================
print("6. Retry Summary")
records = [
    {"step_name": "ollama", "attempt": 1, "success": False},
    {"step_name": "ollama", "attempt": 2, "success": True},
    {"step_name": "git", "attempt": 1, "success": False},
]
rs = dash.create_retry_summary(records)
assert_eq("total_retries", rs["total_retries"], 3)
assert_eq("steps_with_retries", rs["steps_with_retries"], 2)
print(f"    {rs['summary']}")
print()

# =============================================================
# 7. Recovery Summary
# =============================================================
print("7. Recovery Summary")
recov_history = [
    {"step_name": "step_a", "decision": {"should_retry": True}},
    {"step_name": "step_b", "decision": {"should_retry": False}},
]
recov_summary = dash.create_recovery_summary(
    recovery_active=True,
    safe_mode_active=False,
    recovery_history=recov_history,
)
assert_eq("total_recovery_attempts", recov_summary["total_recovery_attempts"], 2)
assert_eq("status_label (recovery active)", recov_summary["status_label"], "RECOVERY ACTIVE")
print(f"    {recov_summary['status_label']}  rate={recov_summary['recovery_rate']}")
print()

# =============================================================
# 8. Full Snapshot
# =============================================================
print("8. Full Snapshot")
phases = [
    dash.create_phase_progress("phase_1", "completed", 5, 5),
    dash.create_phase_progress("phase_2", "running", 2, 5),
]
snap = dash.create_snapshot("deploy-001", phases)
assert_eq("overall_status (running)", snap.overall_status, "running")
assert_eq("retry_count default", snap.retry_count, 0)
assert_true("elapsed_seconds >= 0", snap.elapsed_seconds >= 0)
print(f"    status={snap.overall_status}  id={snap.deployment_id}")
print()

# =============================================================
# 9. Status String
# =============================================================
print("9. Status String")
status_str = dash.get_status_string(snap)
assert_true("status string is non-empty", len(status_str) > 0)
print(f"    {status_str}")
print()

# =============================================================
# 10. Health Summary
# =============================================================
print("10. Health Summary")
health_summary = dash.get_health_summary(snap)
assert_true("status in health summary", "status" in health_summary)
print(f"    health={health_summary['status']}  components={health_summary['components']}")
print()

# =============================================================
# 11. Risk Summary
# =============================================================
print("11. Risk Summary")
risk_summary = dash.get_risk_summary(snap)
assert_true("level in risk summary", "level" in risk_summary)
print(f"    risk_level={risk_summary['level']}  active={risk_summary['active_risks']}")
print()

# =============================================================
# 12. Progress Summary
# =============================================================
print("12. Progress Summary")
progress = dash.get_progress_summary(snap)
assert_true("progress_pct > 0", progress["progress_pct"] > 0)
print(f"    progress={progress['progress_pct']}%  steps={progress['completed_steps']}/{progress['total_steps']}")
print()

# =============================================================
# 13. Snapshot History
# =============================================================
print("13. Snapshot History")
history = dash.get_snapshot_history()
assert_true("history has entries", len(history) > 0)
assert_eq("latest snapshot ID", history[-1]["deployment_id"], "deploy-001")
print(f"    history entries: {len(history)}")
print()

# =============================================================
# 14. Empty dashboard state
# =============================================================
print("14. Empty dashboard state")
dash2 = DeploymentVisibilityDashboard()
status_empty = dash2.get_status_string()
assert_eq("empty status string", status_empty, "NO DEPLOYMENT DATA")
print(f"    empty state: {status_empty}")
print()

print("=== DeploymentVisibilityDashboard Validation COMPLETE ===")
