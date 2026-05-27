# Corax Orchestrator — Internal Alpha Build Guide

**Version:** 1.0.0-alpha  
**Status:** Internal Alpha  
**Build System:** PyInstaller (Windows)

---

## Overview

This document describes how to build, test, and deploy the Corax Orchestrator
internal alpha executable for Windows.

## Prerequisites

- **Python 3.10+** installed and in PATH
- **Git** (optional, for version tracking)
- **Windows 10/11** (64-bit)
- **Administrator privileges** (recommended for full functionality)

## Build Pipeline

The build pipeline consists of 6 phases:

```
Phase 1: Environment Validation
    ↓
Phase 2: Dependency Installation
    ↓
Phase 3: Health Check
    ↓
Phase 4: Bootstrap Validation
    ↓
Phase 5: PyInstaller Build
    ↓
Phase 6: Post-Build Validation
```

## Quick Start

### PowerShell (Recommended)

```powershell
# Standard build
.\build_windows.ps1

# One-file executable
.\build_windows.ps1 -OneFile

# Debug build
.\build_windows.ps1 -Debug

# Skip health checks for faster iteration
.\build_windows.ps1 -SkipHealthCheck -SkipBootstrap
```

### Command Prompt

```batch
:: Standard build
build_windows.bat

:: One-file executable
build_windows.bat --onefile

:: Debug build
build_windows.bat --debug

:: Skip health checks
build_windows.bat --skip-health --skip-bootstrap
```

## Build Output

After a successful build, the executable will be at:

```
dist/
└── CoraxOrchestrator/
    ├── CoraxOrchestrator.exe    <-- Main executable
    ├── config/                   <-- Configuration files
    ├── data/                     <-- Data directory
    └── ...                       <-- Supporting DLLs and modules
```

Or for one-file builds:

```
dist/
└── CoraxOrchestrator.exe        <-- Single-file executable
```

## Build Reports

After each build, the following reports are generated:

| Report                 | Location                         | Description              |
| ---------------------- | -------------------------------- | ------------------------ |
| Project Health Report  | `docs/PROJECT_HEALTH_REPORT.md`  | Overall project health   |
| Build Readiness Report | `docs/BUILD_READINESS_REPORT.md` | Build-specific readiness |
| Alpha Blockers Report  | `docs/ALPHA_BLOCKERS_REPORT.md`  | Alpha release blockers   |
| Build Log              | `data/logs/build.log`            | Build process log        |
| Bootstrap Log          | `data/logs/bootstrap.log`        | Bootstrap validation log |

## Running the Executable

### Command Line

```powershell
# Run with default configuration
.\dist\CoraxOrchestrator\CoraxOrchestrator.exe

# Run with debug output
.\dist\CoraxOrchestrator\CoraxOrchestrator.exe --debug

# Run with custom config
.\dist\CoraxOrchestrator\CoraxOrchestrator.exe --config path\to\config.yaml
```

### Startup Sequence

1. **Bootstrap Phase**: Validates environment, dependencies, permissions
2. **Runtime Phase**: Initializes logging, configuration, modules
3. **Deployment Phase**: Loads deployment orchestration
4. **AI Provisioning Phase**: Initializes AI providers and model registry

## Diagnostics

Startup diagnostics are saved to:

```
data/logs/startup_diagnostics_<timestamp>.json
data/logs/startup_diagnostics_<timestamp>.md
```

These contain:

- System information
- Phase-by-phase startup timing
- Dependency status
- Error and warning details
- Crash diagnostics (if applicable)

## Troubleshooting

### Build Fails

1. Check `data/logs/build.log` for error details
2. Ensure all dependencies are installed: `pip install -r requirements.txt`
3. Ensure PyInstaller is installed: `pip install pyinstaller`
4. Try with `-Debug` flag for more verbose output

### Executable Crashes on Startup

1. Check `data/logs/startup_diagnostics_*.md` for crash details
2. Run the bootstrap validation: `python scripts/runtime_bootstrap.py`
3. Check for missing dependencies or configuration issues

### Missing Functionality

1. Ensure all hidden imports are specified in the build script
2. Check `docs/BUILD_READINESS_REPORT.md` for packaging issues
3. Verify dynamic imports are properly handled

## Version Information

The alpha build version is embedded in:

- `src/core/version.py` (if exists)
- Executable metadata (Windows file properties)
- Build log headers

## Security Notes

- The alpha executable runs with the user's privileges
- Network access is required for AI provider communication
- Configuration files may contain API endpoints
- Logs may contain system information

---

_Last updated: 2026-05-27_  
_Corax Orchestrator — Internal Alpha Build_
