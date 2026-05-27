# Corax Orchestrator - Recovery Validation Guide

## Overview

This guide validates Corax's self-healing and recovery capabilities. The system must be able to detect, diagnose, and recover from various failure modes without data loss or infinite loops.

## Recovery Systems

### 1. Retry Queue

The retry queue handles transient failures with bounded retries.

**Validation:**
- [ ] Failed operations enter retry queue
- [ ] Retries respect max_retries limit
- [ ] Backoff multiplier increases delay between retries
- [ ] Cooldown period prevents rapid retry storms
- [ ] Retry exhaustion triggers escalation
- [ ] Queue persists across application restarts

### 2. Checkpoint System

Checkpoints save deployment state for recovery.

**Validation:**
- [ ] Checkpoints created at each deployment stage
- [ ] Checkpoints include full state snapshot
- [ ] Interrupted deployment resumes from last checkpoint
- [ ] Checkpoints are bounded (max N checkpoints)
- [ ] Old checkpoints are pruned automatically

### 3. PATH Repair

Corax can detect and repair corrupted PATH entries.

**Validation:**
- [ ] Missing tool directories detected
- [ ] Corrupted PATH entries identified
- [ ] PATH is repaired without duplicates
- [ ] System PATH is preserved
- [ ] User PATH is preserved

### 4. Venv Repair

Corax can recreate corrupted virtual environments.

**Validation:**
- [ ] Missing venv detected
- [ ] Corrupted venv detected
- [ ] Venv is recreated with correct Python version
- [ ] Installed packages are restored
- [ ] Activation scripts are regenerated

### 5. Dependency Repair

Corax can reinstall missing or corrupted dependencies.

**Validation:**
- [ ] Missing packages detected
- [ ] Corrupted packages detected
- [ ] Packages are reinstalled from cache or network
- [ ] Version constraints are respected
- [ ] Dependency conflicts are resolved

### 6. Reboot Resume

Corax can resume deployment after system reboot.

**Validation:**
- [ ] Deployment state persisted before reboot
- [ ] State detected on next launch
- [ ] Deployment resumes from correct stage
- [ ] Already-completed steps are skipped
- [ ] Failed steps are retried

## Recovery Scenarios

### Scenario 1: Network Failure During Download

1. Start a deployment that downloads installers
2. Disconnect network mid-download
3. Expected: Download fails, enters retry queue
4. Reconnect network
5. Expected: Download resumes from retry queue

### Scenario 2: Process Crash During Installation

1. Start an installer
2. Kill the installer process
3. Expected: Corax detects process exit with error
4. Expected: Failure is analyzed
5. Expected: Operation enters retry queue

### Scenario 3: Disk Space Exhaustion

1. Fill disk to near capacity
2. Start a deployment
3. Expected: Disk space check fails
4. Expected: User is notified
5. Expected: Deployment pauses until space is available

### Scenario 4: Permission Denied

1. Run Corax without admin rights
2. Start an installer that requires elevation
3. Expected: Elevation request is detected
4. Expected: User is prompted for elevation
5. Expected: Operation retries with elevation

### Scenario 5: Antivirus Quarantine

1. Start a deployment
2. Antivirus quarantines a downloaded installer
3. Expected: Missing file is detected
4. Expected: File is re-downloaded
5. Expected: Antivirus exclusion is requested

## Recovery Metrics

| Metric | Target | Current |
|--------|--------|---------|
| Retry success rate | >90% | - |
| Recovery time (avg) | <30s | - |
| Checkpoint overhead | <1s | - |
| PATH repair success | >95% | - |
| Venv repair success | >95% | - |
| Reboot resume success | >90% | - |

## Infinite Loop Prevention

- Bounded retries (configurable max)
- Exponential backoff with cap
- Cooldown periods between retry batches
- Maximum recovery attempts per operation
- Escalation to user after exhaustion
- Circuit breaker pattern for repeated failures
