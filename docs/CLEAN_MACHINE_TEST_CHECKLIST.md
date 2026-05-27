# Corax Orchestrator — Clean Machine Test Checklist

**Version:** 1.0.0-alpha  
**Purpose:** Validate executable behavior on a clean Windows machine

---

## Overview

This checklist is used to validate that the Corax Orchestrator executable can
bootstrap itself and run correctly on a clean Windows machine that has never
had Python or any development tools installed.

## Test Environment

### Machine Requirements

- **OS:** Windows 10 22H2 or Windows 11 23H2 (64-bit)
- **RAM:** 8GB minimum, 16GB recommended
- **Disk:** 10GB free space
- **Network:** Internet access (for dependency installation)
- **Python:** NOT installed (clean machine)
- **Git:** NOT installed (clean machine)
- **VS Code:** NOT installed (clean machine)

### Setup

1. Create a clean Windows VM or use a test machine
2. Do NOT install Python, Git, or any development tools
3. Copy the CoraxOrchestrator build to the machine
4. Run through the checklist below

---

## Pre-Test Checklist

- [ ] Clean Windows VM is ready (no Python, no dev tools)
- [ ] CoraxOrchestrator build is copied to the machine
- [ ] Executable is accessible from command prompt
- [ ] Antivirus is enabled (default Windows Defender)
- [ ] User is a standard user (not administrator)

---

## Test 1: Basic Startup (Standard User)

**Steps:**

1. Open Command Prompt as standard user
2. Navigate to the build directory
3. Run: `CoraxOrchestrator.exe`

**Expected Results:**

- [ ] Executable starts without crash
- [ ] Bootstrap phase completes (may show warnings)
- [ ] Runtime phase completes or shows graceful degradation
- [ ] Diagnostics are generated
- [ ] Exit code is 0 or 1 (not a crash)

**Notes:**

- Some features may be unavailable without admin rights
- Bootstrap should still complete its validation

---

## Test 2: Basic Startup (Administrator)

**Steps:**

1. Open Command Prompt as administrator
2. Navigate to the build directory
3. Run: `CoraxOrchestrator.exe`

**Expected Results:**

- [ ] Executable starts without crash
- [ ] Bootstrap phase completes successfully
- [ ] Runtime phase completes successfully
- [ ] Deployment phase completes or shows graceful degradation
- [ ] AI provisioning phase completes or shows graceful degradation
- [ ] Diagnostics are generated
- [ ] Exit code is 0

---

## Test 3: Startup Diagnostics Verification

**Steps:**

1. After running Test 2, check diagnostics:
2. `dir data\logs\startup_diagnostics_*.md`
3. Open the most recent file

**Expected Results:**

- [ ] Diagnostic file exists
- [ ] Report shows system information
- [ ] All phases are documented
- [ ] No critical errors
- [ ] Dependency status is documented

---

## Test 4: Bootstrap Self-Healing

**Steps:**

1. Delete the `data` directory: `rmdir /s data`
2. Delete the `config` directory: `rmdir /s config`
3. Run: `CoraxOrchestrator.exe`

**Expected Results:**

- [ ] Executable starts without crash
- [ ] Bootstrap recreates data directories
- [ ] Bootstrap recreates config directory
- [ ] Default config is generated
- [ ] Startup completes successfully

---

## Test 5: Configuration Loading

**Steps:**

1. After Test 4, check that config was created:
2. `type config\default.yaml`

**Expected Results:**

- [ ] `config/default.yaml` exists
- [ ] File contains valid YAML
- [ ] Configuration values are sensible defaults

---

## Test 6: Repeated Startup

**Steps:**

1. Run: `CoraxOrchestrator.exe`
2. Run: `CoraxOrchestrator.exe`
3. Run: `CoraxOrchestrator.exe`

**Expected Results:**

- [ ] All three runs complete successfully
- [ ] Consistent startup behavior
- [ ] No cumulative errors
- [ ] Similar startup times across runs

---

## Test 7: Error Handling

**Steps:**

1. Run with invalid flag: `CoraxOrchestrator.exe --invalid-flag`
2. Run with missing config: `CoraxOrchestrator.exe --config nonexistent.yaml`

**Expected Results:**

- [ ] Graceful error message displayed
- [ ] No unhandled exceptions
- [ ] Exit code is non-zero
- [ ] Diagnostics capture the error

---

## Test 8: Antivirus Compatibility

**Steps:**

1. Ensure Windows Defender is enabled with default settings
2. Run: `CoraxOrchestrator.exe`
3. Check Windows Security for any quarantine alerts

**Expected Results:**

- [ ] Executable is not quarantined
- [ ] No Windows Defender alerts
- [ ] Executable runs without interference

**If quarantined:**

- [ ] Document the alert details
- [ ] Submit to Microsoft for false positive review
- [ ] Try build without UPX compression

---

## Test 9: Disk Space and File Structure

**Steps:**

1. After running, check the build directory structure:
2. `dir /s CoraxOrchestrator`

**Expected Results:**

- [ ] Build directory is < 500MB (one-folder mode)
- [ ] All expected subdirectories exist
- [ ] No unexpected files created outside build directory
- [ ] Log files are in `data/logs/`

---

## Test 10: Network Independence

**Steps:**

1. Disconnect the machine from the internet
2. Run: `CoraxOrchestrator.exe`

**Expected Results:**

- [ ] Executable starts without network
- [ ] Bootstrap completes (no network dependencies)
- [ ] Runtime initializes
- [ ] AI provisioning shows graceful degradation
- [ ] Diagnostics are generated

---

## Overall Results

| Test                             | Status | Notes |
| -------------------------------- | ------ | ----- |
| 1. Basic Startup (Standard User) | ⬜     |       |
| 2. Basic Startup (Administrator) | ⬜     |       |
| 3. Startup Diagnostics           | ⬜     |       |
| 4. Bootstrap Self-Healing        | ⬜     |       |
| 5. Configuration Loading         | ⬜     |       |
| 6. Repeated Startup              | ⬜     |       |
| 7. Error Handling                | ⬜     |       |
| 8. Antivirus Compatibility       | ⬜     |       |
| 9. Disk Space and Structure      | ⬜     |       |
| 10. Network Independence         | ⬜     |       |

**Overall Result:** ⬜ PASS / ⬜ FAIL / ⬜ PARTIAL

**Tested By:** ********\_******** **Date:** ********\_********

---

## Issues Found

| #   | Test | Issue | Severity | Status |
| --- | ---- | ----- | -------- | ------ |
|     |      |       |          |        |

## Recommendations

-

---

_Last updated: 2026-05-27_  
_Corax Orchestrator — Clean Machine Test Checklist_
