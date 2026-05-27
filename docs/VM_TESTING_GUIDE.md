# Corax Orchestrator — VM Testing Guide

**Version:** 1.0.0-alpha  
**Purpose:** Guide for testing the executable in virtual machine environments

---

## Overview

Virtual machine testing is essential for validating that the Corax Orchestrator
executable works correctly in clean, isolated environments. This guide covers
VM setup, testing procedures, and common VM-specific issues.

## Recommended VM Platforms

| Platform           | Version           | Notes                         |
| ------------------ | ----------------- | ----------------------------- |
| Hyper-V            | Windows 10/11 Pro | Best integration with Windows |
| VirtualBox         | 7.0+              | Free, cross-platform          |
| VMware Workstation | 17+               | Commercial, feature-rich      |
| Windows Sandbox    | Windows 10/11 Pro | Lightweight, ephemeral        |

## VM Configuration

### Minimum Requirements

| Resource  | Minimum        | Recommended     |
| --------- | -------------- | --------------- |
| CPU Cores | 2              | 4               |
| RAM       | 4GB            | 8GB             |
| Disk      | 20GB           | 40GB            |
| Network   | NAT or Bridged | Internet access |

### Windows Guest OS

- **Windows 10 22H2** (64-bit) or **Windows 11 23H2** (64-bit)
- **No additional software** — Clean install only
- **Windows Updates** — Fully updated
- **User Account** — Create both standard and admin users

## VM Setup Steps

### 1. Create the VM

```powershell
# Hyper-V example
New-VM -Name "Corax-Test" -MemoryStartupBytes 8GB -BootDevice VHD
Set-VMProcessor -VMName "Corax-Test" -Count 4
```

### 2. Install Windows

- Use official Windows ISO from Microsoft
- Perform clean installation
- Do NOT install any additional software
- Create a standard user account
- Create an administrator account

### 3. Configure Windows

```powershell
# Disable Windows Defender real-time monitoring (optional, for testing)
Set-MpPreference -DisableRealtimeMonitoring $true

# Enable script execution (for build scripts)
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

### 4. Take a Snapshot

Before testing, take a VM snapshot so you can revert to a clean state:

```powershell
# Hyper-V
Checkpoint-VM -Name "Corax-Test" -SnapshotName "Clean-State"
```

## Testing Procedures

### Test Scenario 1: Clean Machine Bootstrap

**Objective:** Verify the executable can bootstrap on a machine with no Python.

**Steps:**

1. Revert VM to clean state snapshot
2. Copy the CoraxOrchestrator build to the VM
3. Run as administrator
4. Observe bootstrap behavior
5. Check diagnostics

### Test Scenario 2: Dependency Self-Healing

**Objective:** Verify the executable can install missing dependencies.

**Steps:**

1. Revert VM to clean state snapshot
2. Copy the build to the VM
3. Delete the `data` and `config` directories
4. Run the executable
5. Verify directories are recreated
6. Verify default config is generated

### Test Scenario 3: Repeated Startup Stability

**Objective:** Verify consistent startup behavior.

**Steps:**

1. Run the executable 5 times consecutively
2. Compare diagnostics across runs
3. Verify no cumulative errors
4. Verify consistent startup times

### Test Scenario 4: Network Disconnected

**Objective:** Verify graceful degradation without network.

**Steps:**

1. Disconnect the VM network adapter
2. Run the executable
3. Verify bootstrap completes
4. Verify graceful degradation for network-dependent features

### Test Scenario 5: Limited Resources

**Objective:** Verify behavior with minimum resources.

**Steps:**

1. Reduce VM to minimum specs (2 cores, 4GB RAM)
2. Run the executable
3. Verify startup completes
4. Check for performance issues

## VM-Specific Issues

### Issue: Hyper-V Enhanced Session Mode

**Problem:** Enhanced session mode may interfere with console applications.

\*\*
