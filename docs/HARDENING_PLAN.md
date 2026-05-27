# Corax Orchestrator - Real Execution Hardening Plan

## Objective

Transform from architecturally complete to practically reliable on real Windows machines.

## Priority 1: Real Winget Execution

- [ ] Fix `WindowsUtils.winget_install()` to properly handle winget exit codes
- [ ] Add winget source agreement auto-acceptance
- [ ] Add proper timeout handling for winget operations
- [ ] Add structured logging with operation IDs for each winget command
- [ ] Add installer verification after winget completion
- [ ] Add fallback to direct installer when winget fails

## Priority 2: Clean Machine Validation

- [ ] Add `EnvironmentValidator` checks for missing PATH entries
- [ ] Add partial installation detection (registry artifacts without binaries)
- [ ] Add broken installation detection (binaries present but non-functional)
- [ ] Add PATH repair logic for common tool directories
- [ ] Add environment variable repair for common tools

## Priority 3: Deployment Resume System

- [ ] Add checkpoint persistence at each deployment step
- [ ] Add reboot-safe state storage (non-volatile)
- [ ] Add resume-from-last-successful-step logic
- [ ] Add retry-only-failed-operations logic
- [ ] Add checkpoint cleanup on successful completion

## Priority 4: Real Validation Engine

- [ ] Add deep validation for each tool:
  - [ ] git: executable exists, callable, version readable, PATH accessible
  - [ ] python: executable exists, callable, version readable, pip available
  - [ ] node: executable exists, callable, version readable, npm available
  - [ ] vscode: CLI exists, callable, version readable
  - [ ] docker: CLI exists, callable, version readable, daemon status
- [ ] Add validation result to deployment reports
- [ ] Add actionable repair suggestions for each validation failure

## Priority 5: Failure Hardening

- [ ] Add retry exhaustion detection with clear messaging
- [ ] Add cooldown delays between retry attempts
- [ ] Add alternative install strategy support (winget -> direct -> manual)
- [ ] Add transient failure detection (network blips, temporary locks)
- [ ] Add infinite retry loop prevention

## Priority 6: Unattended Deployment Mode

- [ ] Add `--unattended` flag to CLI
- [ ] Add auto-approve for safe operations
- [ ] Add suppress-prompts mode
- [ ] Add continue-on-noncritical-failure mode
- [ ] Add collect-failures-for-review mode

## Priority 7: Deployment Report Maturity

- [ ] Add operation IDs to all report entries
- [ ] Add executed commands to reports
- [ ] Add durations for each step
- [ ] Add retry history to reports
- [ ] Add repaired issues to reports
- [ ] Add skipped tools with reasons
- [ ] Add validation results to reports
- [ ] Add environment modifications (PATH changes, env vars)
- [ ] Add concise summary section
- [ ] Add detailed technical report section

## Priority 8: Real End-to-End Testing

- [ ] Add smoke deployment tests (winget execution)
- [ ] Add installer verification tests
- [ ] Add PATH repair tests
- [ ] Add retry queue behavior tests
- [ ] Add interrupted deployment recovery tests
- [ ] Add deployment resume tests
- [ ] Add validation engine tests
- [ ] Add unattended mode tests

## Priority 9: Stabilization & Cleanup

- [ ] Fix remaining `datetime.utcnow()` deprecation warnings
- [ ] Normalize installer patterns across all 5 installers
- [ ] Improve logging consistency (structured fields)
- [ ] Improve error messages with actionable guidance
- [ ] Clean dead code in deployment modules
- [ ] Reduce duplicate logic between installers

## Files to Modify

1. `src/deployment/windows_utils.py` - Fix winget execution, add verification
2. `src/deployment/validation.py` - Add deep validation, PATH repair
3. `src/deployment/dev_deploy.py` - Add unattended mode, checkpoint resume
4. `src/deployment/execution/executor.py` - Add checkpoint persistence
5. `src/deployment/execution/session.py` - Add resume improvements
6. `src/deployment/installers/base.py` - Fix datetime deprecation
7. `src/deployment/installers/dev_base.py` - Normalize patterns
8. `src/deployment/installers/git_installer.py` - Add verification
9. `src/deployment/installers/python_installer.py` - Add verification
10. `src/deployment/installers/node_installer.py` - Add verification
11. `src/deployment/installers/vscode_installer.py` - Add verification
12. `src/deployment/installers/docker_installer.py` - Add verification
13. `src/deployment/operations.py` - Fix datetime deprecation
14. `src/main.py` - Add unattended flag
15. `tests/integration/test_dev_deploy.py` - Add real execution tests
16. `tests/integration/test_deployment_execution.py` - Add resume tests
17. `docs/TODO.md` - Update progress

## Non-Goals

- No GUI systems
- No browser automation
- No cloud orchestration
- No new abstraction layers
- No AI reasoning expansion
- No macOS deployment (Windows-first)
