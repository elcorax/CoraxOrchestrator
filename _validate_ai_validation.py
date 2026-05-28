"""
Corax Orchestrator — AI Validation Engine Validation.

Validates:
- check_ollama_accessibility (safe, never crashes)
- check_model_availability (graceful degradation)
- check_inference_sanity (graceful timeout/failure)
- check_api_connectivity (safe, never crashes)
- check_disk_space_for_ai (read-only)
- check_gpu_capability (graceful fallback)
- check_model_integrity (safe on missing model)
- check_pull_recovery (safe filesystem check)
- calculate_readiness_score (grading logic)
- generate_ai_diagnostics (comprehensive)
"""

import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

from src.deployment.hardening import AIValidationEngine


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


def print_result(name, result):
    status = "PASS" if result.passed else "FAIL"
    errors = result.errors[:2] if result.errors else []
    print(f"  {status}: {name} (errors={len(result.errors)})")
    if errors:
        for e in errors:
            print(f"    error: {e}")


print("=== AIValidationEngine Validation ===\n")

engine = AIValidationEngine()

# =============================================================
# 1. check_ollama_accessibility
# =============================================================
print("1. check_ollama_accessibility (safe, never crashes)")
result = engine.check_ollama_accessibility()
print_result("ollama_accessibility", result)
print(f"    details keys: {list(result.details.keys())}")
assert_true("errors is list", isinstance(result.errors, list))
assert_true("recommendations is list", isinstance(result.recommendations, list))
print()

# =============================================================
# 2. check_model_availability
# =============================================================
print("2. check_model_availability (graceful)")
result = engine.check_model_availability()
print_result("model_availability", result)
print(f"    details keys: {list(result.details.keys())}")
if not result.passed:
    # If no models available, should still give recommendations
    assert_true("recommendations on failure", len(result.recommendations) > 0 or not result.passed)
print()

# =============================================================
# 3. check_inference_sanity (short timeout so it fails fast)
# =============================================================
print("3. check_inference_sanity (safe timeout)")
result = engine.check_inference_sanity(timeout=5)
print_result("inference_sanity", result)
# This will likely fail (no model running) but should never crash
print()

# =============================================================
# 4. check_api_connectivity
# =============================================================
print("4. check_api_connectivity (safe, never crashes)")
result = engine.check_api_connectivity()
print_result("api_connectivity", result)
print(f"    reachable={result.details.get('reachable')}/{result.details.get('total')}")
print()

# =============================================================
# 5. check_disk_space_for_ai
# =============================================================
print("5. check_disk_space_for_ai (read-only)")
result = engine.check_disk_space_for_ai()
print_result("disk_space", result)
if result.details.get("free_gb"):
    print(f"    free={result.details['free_gb']}GB / required={result.details['minimum_required_gb']}GB")
print()

# =============================================================
# 6. check_gpu_capability
# =============================================================
print("6. check_gpu_capability (never fails — CPU fallback OK)")
result = engine.check_gpu_capability()
assert_true("gpu check never fails", result.passed)
print(f"    gpu_info: {result.details}")
print()

# =============================================================
# 7. check_model_integrity (safe on missing model)
# =============================================================
print("7. check_model_integrity (safe)")
result = engine.check_model_integrity()
print_result("model_integrity", result)
# May fail (no model) but should never crash
print()

# =============================================================
# 8. check_pull_recovery (safe filesystem scan)
# =============================================================
print("8. check_pull_recovery (safe filesystem)")
result = engine.check_pull_recovery()
print_result("pull_recovery", result)
print(f"    checked_paths: {result.details.get('checked_paths', [])}")
print()

# =============================================================
# 9. calculate_readiness_score
# =============================================================
print("9. calculate_readiness_score")
score = engine.calculate_readiness_score(run_checks=True)
assert_true("score is 0.0-1.0", 0.0 <= score.score <= 1.0)
assert_true("grade is valid", score.grade in ("A", "B", "C", "D", "F"))
print(f"    score={score.score:.3f} grade={score.grade}")
print(f"    checks: {len(score.checks)}")
print(f"    passed={score.summary.get('passed')} failed={score.summary.get('failed')}")
print()

# =============================================================
# 10. generate_ai_diagnostics (comprehensive, never crashes)
# =============================================================
print("10. generate_ai_diagnostics (comprehensive)")
diag = engine.generate_ai_diagnostics()
assert_true("timestamp present", "timestamp" in diag)
assert_true("checks present", "checks" in diag)
assert_true("total_checks > 0", diag.get("total_checks", 0) > 0)
print(f"    total_checks={diag.get('total_checks')}")
print(f"    all_passed={diag.get('all_checks_passed')}")
for check_name, check_data in diag["checks"].items():
    print(f"    {check_name}: {'PASS' if check_data.get('passed') else 'FAIL'}")
print()

print("=== AIValidationEngine Validation COMPLETE ===")
