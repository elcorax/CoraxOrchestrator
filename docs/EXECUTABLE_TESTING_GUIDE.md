# Corax Orchestrator — Executable Testing Guide

**Version:** 1.0.0-alpha  
**Purpose:** Validate the Windows executable build and runtime behavior

---

## Pre-Testing Checklist

Before testing the executable, verify:

- [ ] Build completed successfully (see `data/logs/build.log`)
- [ ] Executable exists at expected path
- [ ] Health check reports generated (see `docs/`)
- [ ] Bootstrap validation passed
- [ ] All dependencies installed

## Test Scenarios

### 1. Basic Startup Test

**Objective:** Verify the executable starts without crashing.

```powershell
# Run the executable
.\dist\CoraxOrchestrator\CoraxOrchestrator.exe

# Expected: Clean startup with no ImportError or crash
# Expected: Bootstrap phases complete successfully
# Expected: Exit code 0
```

**Pass Criteria:**

- [ ] Executable launches without crash
- [ ] Bootstrap validation completes
- [ ] Runtime initializes
- [ ] Exit code is 0

### 2. Startup Diagnostics Test

**Objective:** Verify diagnostics are generated correctly.

```powershell
# Run and check diagnostics
.\dist\CoraxOrchestrator\CoraxOrchestrator.exe
dir data/logs/startup_diagnostics_*.md
```

**Pass Criteria:**

- [ ] Diagnostic JSON file created
- [ ] Diagnostic Markdown file created
- [ ] Report contains system information
- [ ] Report contains phase timing data
- [ ] Report contains dependency status

### 3. Dependency Validation Test

**Objective:** Verify all dependencies are bundled correctly.

**Pass Criteria:**

- [ ] No ImportError on startup
- [ ] All third-party modules load correctly
- [ ] Core Python modules available
- [ ] Project modules import successfully

### 4. Configuration Loading Test

**Objective:** Verify configuration is loaded correctly.

**Pass Criteria:**

- [ ] Default config loads without error
- [ ] Config directory is accessible
- [ ] Config values are parsed correctly

### 5. Deployment Module Test

**Objective:** Verify deployment orchestration loads.

**Pass Criteria:**

- [ ] Deployment orchestrator module loads
- [ ] Installer modules are accessible
- [ ] Validation modules are accessible
- [ ] Repair modules are accessible

### 6. AI Provisioning Test

**Objective:** Verify AI provisioning systems initialize.

**Pass Criteria:**

- [ ] Provider registry loads
- [ ] Model registry loads
- [ ] Provider implementations are accessible
- [ ] AI installer modules are accessible

### 7. Error Handling Test

**Objective:** Verify graceful error handling.

```powershell
# Test with missing config
.\dist\CoraxOrchestrator\CoraxOrchestrator.exe --config nonexistent.yaml

# Test with invalid arguments
.\dist\CoraxOrchestrator\CoraxOrchestrator.exe --invalid-flag
```

**Pass Criteria:**

- [ ] Graceful error messages displayed
- [ ] No unhandled exceptions
- [ ] Diagnostic report captures errors
- [ ] Exit code is non-zero on failure

### 8. Bootstrap Self-Healing Test

**Objective:** Verify bootstrap can repair missing dependencies.

**Pass Criteria:**

- [ ] Bootstrap detects missing dependencies
- [ ] Bootstrap attempts repair
- [ ] Bootstrap reports repair status
- [ ] Bootstrap continues after successful repair

### 9. Performance Test

**Objective:** Verify startup performance is acceptable.

**Pass Criteria:**

- [ ] Total startup time < 30 seconds
- [ ] Bootstrap phase < 10 seconds
- [ ] Runtime initialization < 10 seconds
- [ ] No excessive memory usage

### 10. Repeated Startup Test

**Objective:** Verify reproducible startup behavior.

```powershell
# Run 3 times and compare diagnostics
.\dist\CoraxOrchestrator\CoraxOrchestrator.exe
.\dist\CoraxOrchestrator\CoraxOrchestrator.exe
.\dist\CoraxOrchestrator\CoraxOrchestrator.exe
```

**Pass Criteria:**

- [ ] Consistent startup behavior across runs
- [ ] No cumulative errors
- [ ] Similar startup times
- [ ] Same diagnostic structure

## Test Results Template

```markdown
# Test Run: <date>

## Summary

- **Build Version:** <version>
- **Test Environment:** <OS, Python version>
- **Overall Result:** PASS / FAIL / PARTIAL

## Scenario Results

| #   | Scenario               | Status    | Notes |
| --- | ---------------------- | --------- | ----- |
| 1   | Basic Startup          | PASS/FAIL |       |
| 2   | Startup Diagnostics    | PASS/FAIL |       |
| 3   | Dependency Validation  | PASS/FAIL |       |
| 4   | Configuration Loading  | PASS/FAIL |       |
| 5   | Deployment Module      | PASS/FAIL |       |
| 6   | AI Provisioning        | PASS/FAIL |       |
| 7   | Error Handling         | PASS/FAIL |       |
| 8   | Bootstrap Self-Healing | PASS/FAIL |       |
| 9   | Performance            | PASS/FAIL |       |
| 10  | Repeated Startup       | PASS/FAIL |       |

## Issues Found

- <issue description>

## Recommendations

- <recommendation>
```

## Reporting Issues

When reporting issues, include:

1. Build version and timestamp
2. Test environment details
3. Startup diagnostics from `data/logs/`
4. Build log from `data/logs/build.log`
5. Steps to reproduce
6. Expected vs actual behavior

---

_Last updated: 2026-05-27_  
_Corax Orchestrator — Executable Testing Guide_
