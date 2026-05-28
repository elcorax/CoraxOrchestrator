"""
Corax Orchestrator — Deployment Intelligence Validation.

Validates:
- calculate_health_score() with empty and populated data
- calculate_installer_reliability() with various histories
- detect_bottlenecks() with timing data
- generate_retry_heatmap() with retry records
- calculate_failure_statistics() with failure records
- assess_environment_risk() with check results
- generate_full_report() comprehensive
"""

import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

from src.deployment.hardening import DeploymentIntelligence

def assert_eq(name, actual, expected):
    if actual == expected:
        print(f"  PASS: {name}")
    else:
        print(f"  FAIL: {name} — expected {expected!r}, got {actual!r}")

def assert_gt(name, actual, threshold):
    if actual > threshold:
        print(f"  PASS: {name} ({actual} > {threshold})")
    else:
        print(f"  FAIL: {name} — {actual} not > {threshold}")

print("=== DeploymentIntelligence Validation ===\n")

di = DeploymentIntelligence()

# 1. calculate_health_score with empty data
print("1. calculate_health_score (empty)")
hs = di.calculate_health_score([])
assert_eq("health.grade with empty data", hs.grade, "A")
assert_eq("health.score with empty data", hs.score, 1.0)
print()

# 2. calculate_health_score with mixed results
print("2. calculate_health_score (mixed data)")
results = [
    {"success": True, "duration_ms": 5000},
    {"success": True, "duration_ms": 10000},
    {"success": False, "duration_ms": 15000},
    {"success": True, "duration_ms": 5000},
]
hs = di.calculate_health_score(results)
print(f"  score={hs.score:.3f} grade={hs.grade}")
print(f"  insights={len(hs.insights)}")
assert_gt("health score > 0.5", hs.score, 0.5)
print()

# 3. calculate_installer_reliability
print("3. calculate_installer_reliability")
history = [
    {"success": True, "duration_ms": 10000},
    {"success": True, "duration_ms": 12000},
    {"success": True, "duration_ms": 8000},
    {"success": False, "duration_ms": 5000},
    {"success": True, "duration_ms": 11000},
]
ir = di.calculate_installer_reliability("ollama", history)
assert_eq("tool_key", ir.tool_key, "ollama")
assert_eq("total_attempts", ir.total_attempts, 5)
assert_eq("success_count", ir.success_count, 4)
assert_eq("is_unstable (5 attempts, 80%)", ir.is_unstable, False)
print(f"  success_rate={ir.success_rate:.2f}")
print(f"  recommendation={ir.recommendation[:50]}...")
print()

# 4. calculate_installer_reliability — unstable
print("4. calculate_installer_reliability (unstable)")
bad_history = [
    {"success": False, "duration_ms": 5000},
    {"success": False, "duration_ms": 5000},
    {"success": False, "duration_ms": 5000},
    {"success": True, "duration_ms": 5000},
    {"success": False, "duration_ms": 5000},
]
ir2 = di.calculate_installer_reliability("bad_tool", bad_history)
assert_eq("is_unstable (bad)", ir2.is_unstable, True)
print(f"  success_rate={ir2.success_rate:.2f}")
print()

# 5. detect_bottlenecks
print("5. detect_bottlenecks")
timings = {
    "download": [5000, 6000, 5500],
    "extract": [35000, 40000, 38000],  # >30s average = bottleneck
    "install": [2000, 3000, 2500],
}
bottlenecks = di.detect_bottlenecks(timings)
print(f"  bottlenecks found: {len(bottlenecks)}")
for b in bottlenecks:
    print(f"    {b['step']}: {b['type']} ({b['severity']}) avg={b['avg_duration_ms']}ms")
assert_gt("at least 1 bottleneck", len(bottlenecks), 0)
print()

# 6. generate_retry_heatmap
print("6. generate_retry_heatmap")
retry_records = [
    {"step_name": "ollama_install", "attempt": 1, "success": False},
    {"step_name": "ollama_install", "attempt": 2, "success": False},
    {"step_name": "ollama_install", "attempt": 3, "success": True},
    {"step_name": "git_clone", "attempt": 1, "success": False},
    {"step_name": "git_clone", "attempt": 2, "success": True},
]
heatmap = di.generate_retry_heatmap(retry_records)
assert_eq("total_records", heatmap["total_records"], 5)
print(f"  heatmap steps: {list(heatmap['heatmap'].keys())}")
print(f"  hotspots: {len(heatmap['hotspots'])}")
print()

# 7. calculate_failure_statistics
print("7. calculate_failure_statistics")
failures = [
    {"failure_category": "network", "tool_key": "ollama", "timestamp": "2026-01-01T00:00:00"},
    {"failure_category": "network", "tool_key": "ollama", "timestamp": "2026-01-01T01:00:00"},
    {"failure_category": "disk_space", "tool_key": "python", "timestamp": "2026-01-01T02:00:00"},
]
fs = di.calculate_failure_statistics(failures)
assert_eq("total_failures", fs["total_failures"], 3)
assert_eq("most_common_category", fs["most_common_category"], "network")
print()

# 8. assess_environment_risk
print("8. assess_environment_risk")
check_results = [
    {"check_name": "ollama", "passed": True, "errors": [], "warnings": [], "recommendations": []},
    {"check_name": "disk", "passed": False, "errors": ["Low disk space"], "warnings": [], "recommendations": ["Free up space"]},
]
risk = di.assess_environment_risk(check_results)
assert_gt("risk_score > 0", risk["risk_score"], 0)
print(f"  risk_level={risk['risk_level']}")
print(f"  indicators: {len(risk['indicators'])}")
print()

# 9. generate_full_report
print("9. generate_full_report")
report = di.generate_full_report(
    deployment_results=results,
    retry_records=retry_records,
    failure_records=failures,
    step_timings=timings,
)
assert_gt("health score in report", report["health_score"]["score"], 0.5)
assert_eq("bottlenecks in report", len(report["bottlenecks"]), 1)
print(f"  report sections: {[k for k in report.keys()]}")
print()

print("=== DeploymentIntelligence Validation COMPLETE ===")
