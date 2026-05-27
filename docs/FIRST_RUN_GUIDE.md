# Corax Orchestrator — First Run Guide

**Version:** 1.0.0-alpha  
**Purpose:** Guide for running Corax Orchestrator for the first time

---

## Overview

This guide walks through the first run of Corax Orchestrator, covering what to
expect, how to verify successful startup, and how to troubleshoot common issues.

## Prerequisites

- **Windows 10/11** (64-bit)
- **No Python required** — The executable is self-contained
- **Administrator privileges** recommended but not required
- **Internet connection** for AI provider communication (optional)

## Quick Start

### 1. Extract the Build

If you received a one-folder build:

```
CoraxOrchestrator/
├── CoraxOrchestrator.exe    <-- Main executable
├── config/                   <-- Configuration files
├── data/                     <-- Data directory
└── ...                       <-- Supporting DLLs and modules
```

If you received a one-file build:

```
CoraxOrchestrator.exe         <-- Single-file executable
```

### 2. Run the Executable

**Double-click** `CoraxOrchestrator.exe` or run from command line:

```powershell
.\CoraxOrchestrator.exe
```

### 3. Observe Startup

The executable will display startup progress:

```
[BOOTSTRAP] Validating environment...
[BOOTSTRAP] Validating dependencies...
[BOOTSTRAP] Validating permissions...
[BOOTSTRAP] Validating PATH...
[BOOTSTRAP] Runtime initialized.
[RUNTIME] Logging system initialized.
[RUNTIME] Configuration loaded.
[DEPLOYMENT] Deployment orchestrator loaded.
[AI] Provider registry initialized.
[AI] Model registry initialized.
[DIAGNOSTICS] Startup diagnostics saved.
[SUCCESS] Corax Orchestrator started successfully.
```

### 4. Verify Diagnostics

Check that diagnostics were generated:

```powershell
dir data\logs\startup_diagnostics_*.md
```

Open the most recent file to review startup details.

## What Happens on First Run

### Bootstrap Phase

The bootstrap system performs these checks:

1. **Environment Validation** — Checks Python version, platform, system resources
2. **Dependency Validation** — Verifies all required Python packages are available
3. **Permission Validation** — Checks if running as administrator
4. **PATH Validation** — Ensures Python directories are in PATH
5. **Runtime Initialization** — Prepares the Corax runtime environment

### Self-Healing

If any issues are detected, the bootstrap will attempt to repair them:

| Issue                    | Auto-Repair                  | User Action Needed                |
| ------------------------ | ---------------------------- | --------------------------------- |
| Missing data directories | ✅ Created automatically     | None                              |
| Missing config file      | ✅ Generated with defaults   | None                              |
| PATH issues              | ✅ Repaired in-memory        | None                              |
| Missing dependencies     | ✅ Installed automatically   | Internet connection may be needed |
| Permission issues        | ⚠️ Detected but not repaired | Run as administrator              |

### Startup Diagnostics

After startup, diagnostics are saved to:

```
data/logs/startup_diagnostics_<timestamp>.json
data/logs/startup_diagnostics_<timestamp>.md
```

These contain detailed information about every startup phase.

## Verifying Successful Startup

### Check Exit Code

```powershell
.\CoraxOrchestrator.exe
echo $LASTEXITCODE
```

- **0** — Success
- **1** — Startup failure (check diagnostics)
- **2** — Bootstrap failure (check diagnostics)

### Check Log Files

```powershell
dir data\logs\
```

Expected files:

- `startup_diagnostics_<timestamp>.json`
- `startup_diagnostics_<timestamp>.md`
- `bootstrap.log`

### Check Diagnostic Report

Open the Markdown diagnostic report:

```powershell
notepad data\logs\startup_diagnostics_*.md
```

Look for:

- **Status:** ✅ SUCCESS
- All phases marked ✅
- No ❌ FAILED entries

## Common First-Run Issues

### Issue: "Access Denied" When Creating Directories

**Solution:** Run as administrator:

```powershell
Run as Administrator
.\CoraxOrchestrator.exe
```

### Issue: Executable Flagged by Antivirus

**Solution:** This is a known false positive with PyInstaller executables.
Add an exclusion for the executable or build directory.

### Issue: Executable Crashes Immediately

**Solution:**

1. Run from command prompt to see error output
2. Check `data/logs/startup_diagnostics_*.md`
3. Try running with `--debug` flag (if supported)

### Issue: "No Module Named" Error

**Solution:** This indicates a missing hidden import in the build.
Report this issue with the full error message and diagnostic files.

## Configuration

### Default Configuration

The executable generates a default configuration at:

```
config/default.yaml
```

### Custom Configuration

To use a custom configuration file:

```powershell
.\CoraxOrchestrator.exe --config path\to\custom.yaml
```

## Next Steps After First Run

1. ✅ **Verify diagnostics** — Confirm startup was clean
2. ✅ **Check logs** — Review for any warnings
3. ✅ **Test basic functionality** — Run health checks
4. ✅ **Report issues** — Include diagnostic files with bug reports

## Getting Help

If you encounter issues:

1. Check `data/logs/startup_diagnostics_*.md` for error details
2. Check `data/logs/bootstrap.log` for bootstrap details
3. Include both files when reporting issues

---

_Last updated: 2026-05-27_  
_Corax Orchestrator — First Run Guide_
