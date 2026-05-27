# Corax Orchestrator - Internal Alpha Testing Guide

## Overview

This guide covers the testing process for Corax Internal Alpha. The goal is to validate that Corax is executable-ready, GUI-capable, runtime-stable, self-healing, deployment-resilient, and independently runnable on another Windows machine.

## Test Categories

### 1. Executable Tests

| Test | Description | Pass Criteria |
|------|-------------|---------------|
| EXE-01 | Build executable | `build_windows.ps1` completes without errors |
| EXE-02 | Launch executable | GUI appears within 10 seconds |
| EXE-03 | Debug executable | Console output shows startup sequence |
| EXE-04 | Executable size | `< 500MB` |
| EXE-05 | Dependency bundling | All imports resolve at runtime |

### 2. GUI Tests

| Test | Description | Pass Criteria |
|------|-------------|---------------|
| GUI-01 | Dashboard loads | All widgets render, no errors |
| GUI-02 | Progress panel | Progress bars update in real-time |
| GUI-03 | Tool selection | All installers listed, selectable |
| GUI-04 | Deployment control | Start/pause/resume/cancel work |
| GUI-05 | Permissions panel | Shows accurate elevation/access status |
| GUI-06 | Reports viewer | Loads and renders reports |
| GUI-07 | Runtime monitor | Shows live terminal output |
| GUI-08 | Settings panel | Loads/saves settings correctly |
| GUI-09 | Tab switching | All tabs switch without errors |
| GUI-10 | Status bar | Updates with phase/deployment/health info |

### 3. Runtime Tests

| Test | Description | Pass Criteria |
|------|-------------|---------------|
| RTE-01 | Kernel initialization | Kernel starts without errors |
| RTE-02 | Bootstrap sequence | Bootstrap completes successfully |
| RTE-03 | Lifecycle management | Start/shutdown cycle works |
| RTE-04 | State persistence | State saves and restores correctly |
| RTE-05 | Diagnostics | Diagnostics run without errors |
| RTE-06 | Recovery | Recovery from checkpoint works |

### 4. Deployment Tests

| Test | Description | Pass Criteria |
|------|-------------|---------------|
| DEP-01 | Preflight validation | Environment validated correctly |
| DEP-02 | Tool installation | Installers download and install |
| DEP-03 | AI stack deployment | AI tools deploy successfully |
| DEP-04 | Unattended mode | Deployment proceeds without input |
| DEP-05 | Retry queue | Failed operations retry correctly |
| DEP-06 | Failure analysis | Failures analyzed and reported |

### 5. Self-Healing Tests

| Test | Description | Pass Criteria |
|------|-------------|---------------|
| SELF-01 | PATH repair | Corrupted PATH is repaired |
| SELF-02 | Venv repair | Corrupted venv is recreated |
| SELF-03 | Dependency repair | Missing deps are installed |
| SELF-04 | Checkpoint recovery | Interrupted deployment resumes |
| SELF-05 | Reboot resume | Deployment continues after reboot |

### 6. Cross-Platform Tests

| Test | Description | Pass Criteria |
|------|-------------|---------------|
| PLAT-01 | Windows detection | Windows-specific features work |
| PLAT-02 | Platform factory | Correct platform module loaded |
| PLAT-03 | Path handling | Windows paths handled correctly |
| PLAT-04 | Elevation detection | Admin status detected correctly |

## Test Execution

### Automated Tests

```powershell
# Run all tests
python -m pytest tests/ -v

# Run specific test categories
python -m pytest tests/unit/ -v
python -m pytest tests/integration/ -v

# Run executable smoke test
python tests/executable_smoke_test.py
```

### Manual Tests

1. Build the executable
2. Copy to clean Windows VM
3. Run through all test categories
4. Document any failures

## Reporting Issues

When reporting issues, include:
- Test ID (e.g., GUI-03)
- Steps to reproduce
- Expected vs actual behavior
- Logs from `data/logs/`
- Screenshots if applicable

## Alpha Readiness Criteria

- [ ] All EXE tests pass
- [ ] All GUI tests pass
- [ ] All RTE tests pass
- [ ] Core DEP tests pass
- [ ] Core SELF tests pass
- [ ] Executable builds cleanly
- [ ] GUI launches on clean machine
- [ ] Deployment pipeline functions
- [ ] Self-healing activates on failure
- [ ] Reports generate correctly
