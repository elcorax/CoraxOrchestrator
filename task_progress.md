# Hardening Cleanup - Task Progress

## Completed: Alpha Hardening Script Removal & Validator Fixes

- [x] **Archived `_alpha_hardening_h5_h9.py`** - The file became overly large, coupled to runtime internals, architecturally unsafe, and outside HP operational scope.
- [x] **Fixed `stress_restart_runner.py`** - Updated bootstrap class name from `RuntimeBootstrap` to `BootstrapRuntime`, `.initialize()` to `.run()`.
- [x] **Fixed `smoke_test_runner.py`** - Updated bootstrap class name from `RuntimeBootstrap` to `BootstrapRuntime`, `.initialize()` to `.run()`, and replaced `RuntimeLifecycle.shutdown()` with `CoraxRuntimeKernel` instantiation for shutdown survivability test.
- [x] **Verified all external validators pass cleanly:**
  | Validator | Status |
  |---|---|
  | `validation/smoke_test_runner.py` | ✅ All 5/5 PASS |
  | `validation/stress_restart_runner.py` | ✅ All 3 cycles PASS |
  | `validation/diagnostics_validator.py` | ✅ All 6/6 PASS |
  | `validation/diagnostics_bundle_exporter.py` | ✅ All 5/5 PASS |
  | `validation/runtime_snapshot_exporter.py` | ✅ All 5/5 PASS |
  | `validation/deployment_checklist.py` | ✅ All 8/8 PASS |
  | `validation/package_validation_runner.py` | ✅ All 5/5 PASS |
  | `validation/runtime_validation_tools.py` | ✅ All 4/4 PASS |
  | `validation/soak_runner.py` | ✅ All 5/5 iterations PASS |
- [x] **Returned to small external validators** - All validation tools are now focused on external validation, executable testing, deployment survivability, packaging validation, restart-cycle testing, and diagnostics export validation. No runtime internals manipulation, no startup state machine manipulation, no lifecycle internals imports, no mega-hardening scripts.
