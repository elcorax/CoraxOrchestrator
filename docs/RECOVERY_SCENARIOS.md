# Corax Orchestrator — Recovery Scenarios Guide

**Version:** 1.0.0-alpha  
**Purpose:** Document recovery procedures for common failure scenarios

---

## Overview

This guide documents recovery procedures for common failure scenarios that may
occur during alpha testing. Each scenario includes detection, diagnosis, and
recovery steps.

---

## Scenario 1: Corrupted Installation

### Symptoms

- Executable crashes on startup
- ImportError for core modules
- Missing configuration files
- Corrupted data directories

### Detection

```powershell
# Check diagnostics
notepad data\logs\startup_diagnostics_*.md

# Look for:
# - ❌ FAILED phases
# - Missing dependency errors
# - File access errors
```

### Recovery

1. **Delete corrupted directories:**

   ```powershell
   rmdir /s data
   rmdir /s config
   ```

2. **Run the executable:**

   ```powershell
   CoraxOrchestrator.exe
   ```

3. **Verify recovery:**
   - Bootstrap recreates directories
   - Default config is generated
   - Startup completes successfully

### Prevention

- Regular backups of `config/` directory
- Version-controlled configuration files

---

## Scenario 2: Missing Dependencies

### Symptoms

- `ModuleNotFoundError` on startup
- `ImportError` for third-party packages
- Bootstrap reports missing dependencies

### Detection

```powershell
# Check diagnostics
notepad data\logs\startup_diagnostics_*.md

# Look for:
# - Dependency status: missing
# - ImportError in runtime phase
```

### Recovery

1. **Automatic recovery (recommended):**
   - Bootstrap will attempt to install missing dependencies
   - Requires internet connection
   - May require administrator privileges

2. **Manual recovery:**

   ```powershell
   # If Python is available
   pip install -r requirements.txt
   ```

3. **For bundled executable:**
   - Rebuild with PyInstaller to include missing packages
   - Add missing packages to `corax.spec` hiddenimports

### Prevention

- Comprehensive `requirements.txt`
- All dependencies listed in `corax.spec`
- Regular dependency audits

---

## Scenario 3: PATH Corruption

### Symptoms

- Bootstrap reports PATH issues
- Subprocess calls fail
- Cannot find Python or system tools

### Detection

```powershell
# Check diagnostics
notepad data\logs\startup_diagnostics_*.md

# Look for:
# - PATH validation warnings
# - Subprocess execution errors
```

### Recovery

1. **Automatic recovery:**
   - Bootstrap repairs PATH in-memory
   - Python and Scripts directories are added

2. **Manual recovery:**

   ```powershell
   # Check current PATH
   echo %PATH%

   # Add Python to PATH (System)
   setx /M PATH "%PATH%;C:\Python312;C:\Python312\Scripts"
   ```

### Prevention

- Bootstrap PATH validation on every startup
- Document PATH requirements in setup guide

---

## Scenario 4: Permission Denied

### Symptoms

- "Access Denied" errors
- Cannot create directories
- Cannot write log files
- Cannot install dependencies

### Detection

```powershell
# Check diagnostics
notepad data\logs\startup_diagnostics_*.md

# Look for:
# - Permission validation warnings
# - File access errors
```

### Recovery

1. **Run as administrator:**

   ```powershell
   # Right-click → Run as Administrator
   CoraxOrchestrator.exe
   ```

2. **Fix directory permissions:**

   ```powershell
   # Take ownership
   takeown /f . /r /d y
   icacls . /grant "%USERNAME%:(OI)(CI)F" /t
   ```

3. **Use alternative directory:**
   - Copy executable to user-writable location
   - Avoid `Program Files` or system directories

### Prevention

- Run from user-writable directory
- Document administrator requirements
- Graceful degradation for non-admin scenarios

---

## Scenario 5: Configuration Corruption

### Symptoms

- YAML parsing errors
- Missing configuration keys
- Default values used unexpectedly
- Deployment failures

### Detection

```powershell
# Check diagnostics
notepad data\logs\startup_diagnostics_*.md

# Look for:
# - Configuration loading errors
# - YAML parsing errors
```

### Recovery

1. **Delete corrupted config:**

   ```powershell
   del config\default.yaml
   ```

2. **Run the executable:**

   ```powershell
   CoraxOrchestrator.exe
   ```

3. **Verify:**
   - Default config is regenerated
   - Configuration loads correctly

### Prevention

- Validate configuration on load
- Backup configuration files
- Document configuration schema

---

## Scenario 6: Network Failure

### Symptoms

- AI provider connection errors
- Dependency installation failures
- Model download failures
- Timeout errors

### Detection

```powershell
# Check diagnostics
notepad data\logs\startup_diagnostics_*.md

# Look for:
# - Network-related errors
# - Connection timeout errors
# - Download failures
```

### Recovery

1. **Offline mode:**
   - Executable should start without network
   - AI provisioning will show graceful degradation
   - Core functionality remains available

2. **Check network connectivity:**

   ```powershell
   ping localhost
   ping 8.8.8.8
   ```

3. **Check firewall settings:**
   - Ensure executable is allowed through firewall
   - Check for corporate proxy requirements

### Prevention

- Offline-capable startup
- Graceful degradation for network features
- Configurable timeout settings

---

## Scenario 7: Disk Space Exhaustion

### Symptoms

- "No space left on device" errors
- Log file write failures
- Database write failures
- Model download failures

### Detection

```powershell
# Check disk space
wmic logicaldisk get size,freespace,caption

# Check log directory size
dir /s data\logs
```

### Recovery

1. **Clean up old logs:**

   ```powershell
   del data\logs\*.log /q
   del data\logs\startup_diagnostics_*.json /q
   del data\logs\startup_diagnostics_*.md /q
   ```

2. **Clean up old reports:**

   ```powershell
   del data\reports\*.json /q
   ```

3. **Free up disk space:**
   - Run Disk Cleanup
   - Uninstall unnecessary applications
   - Move data to another drive

### Prevention

- Log rotation
- Configurable log retention
- Disk space monitoring
- Warning at 90% capacity

---

## Scenario 8: Antivirus Quarantine

### Symptoms

- Executable disappears after extraction
- "Windows protected your PC" warning
- SmartScreen block on execution
- Missing DLL or executable files

### Detection

```powershell
# Check Windows Security
# Open Windows Security → Protection history

# Check for quarantined files
Get-MpThreatDetection
```

### Recovery

1. **Restore from quarantine:**
   - Open Windows Security
   - Go to Protection history
   - Restore the executable

2. **Add exclusion:**

   ```powershell
   # Add folder exclusion
   Add-MpPreference -ExclusionPath "C:\path\to\CoraxOrchestrator"
   ```

3. **Rebuild without UPX:**
   ```powershell
   .\build_windows.ps1 -NoUPX
   ```

### Prevention

- Submit executable to Microsoft for analysis
- Use code signing certificate
- Document known antivirus issues

---

## Scenario 9: Version Mismatch

### Symptoms

- Incompatible dependency versions
- API changes between versions
- Configuration format changes
- Data format incompatibility

### Detection

```powershell
# Check diagnostics
notepad data\logs\startup_diagnostics_*.md

# Look for:
# - Version mismatch warnings
# - API compatibility errors
```

### Recovery

1. **Clean reinstall:**

   ```powershell
   rmdir /s data
   rmdir /s config
   ```

2. **Use matching versions:**
   - Ensure executable and config versions match
   - Use version-pinned dependencies

### Prevention

- Semantic versioning
- Version compatibility checks
- Migration scripts for data formats
- Documented upgrade paths

---

## Scenario 10: Complete Failure

### Symptoms

- Executable fails to start at all
- No diagnostics generated
- No error messages displayed
- Process exits immediately

### Detection

```powershell
# Run from command prompt to see output
CoraxOrchestrator.exe

# Check Windows Event Viewer
# Applications and Services Logs → Windows → Application
```

### Recovery

1. **Check event logs:**

   ```powershell
   Get-WinEvent -LogName Application | Where-Object { $_.ProviderName -like "*Corax*" }
   ```

2. **Run bootstrap validation:**

   ```powershell
   python scripts\runtime_bootstrap.py
   ```

3. **Rebuild executable:**

   ```powershell
   .\build_windows.ps1 -Debug
   ```

4. **Last resort — clean rebuild:**
   ```powershell
   rmdir /s dist
   rmdir /s build
   .\build_windows.ps1
   ```

### Prevention

- Comprehensive error handling
- Diagnostic capture on crash
- Bootstrap validation before runtime
- Regular build testing

---

## Recovery Quick Reference

| Scenario                 | Detection         | Recovery              | Time   |
| ------------------------ | ----------------- | --------------------- | ------ |
| Corrupted Installation   | Diagnostics       | Delete data/config    | 1 min  |
| Missing Dependencies     | ImportError       | Auto-install          | 5 min  |
| PATH Corruption          | Bootstrap warning | Auto-repair           | 1 min  |
| Permission Denied        | Access errors     | Run as admin          | 1 min  |
| Configuration Corruption | YAML errors       | Delete config         | 1 min  |
| Network Failure          | Timeout errors    | Offline mode          | 1 min  |
| Disk Space Exhaustion    | No space errors   | Clean logs            | 5 min  |
| Antivirus Quarantine     | Missing files     | Restore/add exclusion | 5 min  |
| Version Mismatch         | API errors        | Clean reinstall       | 10 min |
| Complete Failure         | No startup        | Event logs/rebuild    | 30 min |

---

_Last updated: 2026-05-27_  
_Corax Orchestrator — Recovery Scenarios Guide_
