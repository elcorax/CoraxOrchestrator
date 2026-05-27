# Corax Orchestrator - Executable Deployment Guide

## Overview

This guide covers building and deploying Corax as a standalone Windows executable.

## Building the Executable

### Prerequisites

- Python 3.10+
- PyInstaller
- All project dependencies

### Build Commands

**PowerShell (recommended):**
```powershell
.\build_windows.ps1
```

**Command Prompt:**
```cmd
build_windows.bat
```

**Quick build (skip validation):**
```cmd
build_windows.bat quick
```

**Debug build (with console window):**
```cmd
build_windows.bat debug
```

**Clean build:**
```cmd
build_windows.bat clean
```

### Build Output

After successful build, the `dist/` directory contains:

```
dist/
├── corax.exe              # Main executable (GUI mode)
├── corax_debug.exe        # Debug executable (console mode)
├── run_corax.bat          # Launcher script
├── config/                # Configuration files
│   ├── corax.yaml
│   └── default.yaml
└── data/                  # Data directories
    ├── logs/
    ├── reports/
    ├── persistence/
    └── models/
```

## Deployment to Clean Machine

### Step 1: Prepare Distribution Package

```powershell
# Create deployment package
.\build_windows.ps1 -Clean
Compress-Archive -Path dist\* -DestinationPath corax-deploy.zip
```

### Step 2: Transfer to Target Machine

- Copy `corax-deploy.zip` via USB drive, network share, or download
- Extract to `C:\Corax\` (recommended)

### Step 3: First Launch

1. Navigate to `C:\Corax\`
2. Run `corax.exe` (or `run_corax.bat`)
3. Corax will:
   - Validate environment
   - Detect missing dependencies
   - Self-heal if needed
   - Launch the GUI

### Step 4: Deploy Tools

1. Use the **Tools** tab to select installers
2. Use the **Control** tab to start deployment
3. Monitor progress in the **Monitor** tab
4. View reports in the **Reports** tab

## Troubleshooting

### Executable Won't Launch

1. Run `corax_debug.exe` for console output
2. Check `data/logs/` for error logs
3. Verify all DLLs are present
4. Check antivirus quarantine

### Missing Dependencies

Corax will attempt to self-heal. If it fails:
1. Run `corax_debug.exe` to see detailed errors
2. Install missing Python packages manually
3. Restart Corax

### Antivirus Interference

- Add `C:\Corax\` to antivirus exclusions
- See `ANTIVIRUS_INTERFERENCE_GUIDE.md` for details

## Post-Deployment Verification

- [ ] GUI launches without errors
- [ ] Dashboard shows system status
- [ ] All panels render correctly
- [ ] Deployment controls respond
- [ ] Reports generate and display
- [ ] Settings persist across restarts
