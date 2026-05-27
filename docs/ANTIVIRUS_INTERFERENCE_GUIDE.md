# Corax Orchestrator — Antivirus Interference Guide

**Version:** 1.0.0-alpha  
**Purpose:** Document known antivirus issues and mitigation strategies

---

## Overview

PyInstaller-packaged Python executables are frequently flagged by antivirus
software as false positives. This is a well-known issue in the Python packaging
community. This guide documents known issues and provides mitigation strategies.

## Why Antivirus Flags PyInstaller Executables

1. **PyInstaller bootloader** — The bootloader is a compiled C executable that
   extracts and runs Python code. Antivirus software may flag this as suspicious
   behavior.

2. **UPX compression** — PyInstaller uses UPX compression by default to reduce
   executable size. UPX-compressed executables are frequently flagged because
   malware also uses UPX compression.

3. **Self-extracting archive** — The executable contains a compressed archive of
   Python modules, which resembles the behavior of some malware packers.

4. **Heuristic detection** — Antivirus heuristics may flag the executable based
   on behavioral patterns (e.g., writing files to disk, modifying PATH).

## Known Antivirus Issues

### Windows Defender (Microsoft Defender Antivirus)

| Issue                             | Frequency  | Status         |
| --------------------------------- | ---------- | -------------- |
| False positive detection          | Common     | ⚠️ Known issue |
| SmartScreen block                 | Common     | ⚠️ Known issue |
| Real-time protection interference | Occasional | ⚠️ Known issue |

### Third-Party Antivirus

| Software     | Issue          | Frequency  |
| ------------ | -------------- | ---------- |
| Norton       | False positive | Common     |
| McAfee       | False positive | Common     |
| Avast        | False positive | Occasional |
| AVG          | False positive | Occasional |
| Kaspersky    | False positive | Occasional |
| Bitdefender  | False positive | Occasional |
| Malwarebytes | False positive | Rare       |

## Detection and Diagnosis

### Check if Executable is Quarantined

```powershell
# Windows Defender
Get-MpThreatDetection | Where-Object { $_.Resources -like "*Corax*" }

# Check Windows Security
# Open Windows Security → Virus & threat protection → Protection history
```

### Check SmartScreen Status

```powershell
# Check SmartScreen event logs
Get-WinEvent -LogName "Microsoft-Windows-SmartScreen/Operational" |
    Where-Object { $_.Message -like "*Corax*" }
```

### Check Real-Time Protection Interference

```powershell
# Temporarily disable real-time monitoring (admin required)
Set-MpPreference -DisableRealtimeMonitoring $true

# Run the executable
.\CoraxOrchestrator.exe

# Re-enable real-time monitoring
Set-MpPreference -DisableRealtimeMonitoring $false
```

## Mitigation Strategies

### Strategy 1: Add Exclusion (Recommended)

Add the build directory or executable to antivirus exclusions:

```powershell
# Windows Defender - Add folder exclusion
Add-MpPreference -ExclusionPath "C:\path\to\CoraxOrchestrator"

# Windows Defender - Add file exclusion
Add-MpPreference -ExclusionPath "C:\path\to\CoraxOrchestrator\CoraxOrchestrator.exe"
```

### Strategy 2: Build Without UPX

UPX compression is a common trigger for false positives. Build without it:

```powershell
# Using build script
.\build_windows.ps1 -NoUPX

# Using PyInstaller directly
pyinstaller corax.spec -- --noupx
```

### Strategy 3: Code Signing

Code signing the executable reduces SmartScreen blocks:

1. Obtain a code signing certificate (e.g., from DigiCert, Sectigo)
2. Sign the executable after build:
   ```powershell
   signtool sign /fd SHA256 /a /f certificate.pfx /p password CoraxOrchestrator.exe
   ```
3. Verify the signature:
   ```powershell
   signtool verify /pa CoraxOrchestrator.exe
   ```

### Strategy 4: Submit to Microsoft

Submit the executable to Microsoft for false positive analysis:

1. Go to [Microsoft Security Intelligence](https://www.microsoft.com/en-us/wdsi/filesubmission)
2. Upload the executable
3. Select "Software developer" as submitter type
4. Describe the executable as a legitimate Python application
5. Include source code URL if available

### Strategy 5: Use One-Folder Build

One-folder builds are less likely to be flagged than one-file builds:

```powershell
.\build_windows.ps1  # Default is one-folder
```

## Testing with Antivirus

### Pre-Testing Checklist

- [ ] Windows Defender is enabled with default settings
- [ ] No exclusions have been added (test default behavior)
- [ ] Real-time protection is enabled
- [ ] Cloud-delivered protection is enabled
- [ ] Automatic sample submission is enabled

### Test Procedure

1. **Build the executable:**

   ```powershell
   .\build_windows.ps1
   ```

2. **Copy to test machine:**
   - Use a clean VM with default Windows Defender settings
   - Do NOT add any exclusions

3. **Run the executable:**

   ```powershell
   .\dist\CoraxOrchestrator\CoraxOrchestrator.exe
   ```

4. **Check for interference:**
   - Executable runs without delay
   - No Windows Security alerts
   - No quarantine events
   - Normal startup time

5. **Check protection history:**
   ```powershell
   Get-MpThreatDetection
   ```

### Test Results Template

```markdown
## Antivirus Test Results

**Build:** <version>
**Date:** <date>
**Antivirus:** Windows Defender / <other>

### Results

- [ ] Executable runs without interference
- [ ] No quarantine events
- [ ] No SmartScreen blocks
- [ ] Normal startup time

### Notes

- <any issues observed>
```

## Reporting Antivirus Issues

When reporting antivirus false positives, include:

1. **Executable details:**
   - Build version and timestamp
   - SHA256 hash of the executable
   - Build configuration (UPX, one-file/one-folder)

2. **Antivirus details:**
   - Antivirus software and version
   - Detection name and description
   - Alert details from protection history

3. **Environment details:**
   - Windows version
   - Antivirus configuration
   - Any exclusions or special settings

## Known Safe Practices

The following practices help reduce antivirus interference:

| Practice                 | Impact | Effort |
| ------------------------ | ------ | ------ |
| Code signing             | High   | High   |
| Build without UPX        | Medium | Low    |
| One-folder build         | Medium | Low    |
| Add exclusions           | High   | Low    |
| Submit to Microsoft      | Medium | Medium |
| Use trusted distribution | High   | Medium |

## References

- [PyInstaller: Antivirus False Positives](https://pyinstaller.org/en/stable/feature-notes.html#antivirus-false-positives)
- [Microsoft: Submit File for Malware Analysis](https://www.microsoft.com/en-us/wdsi/filesubmission)
- [Microsoft: Configure Exclusions](https://docs.microsoft.com/en-us/microsoft-365/security/defender-endpoint/configure-exclusions-microsoft-defender-antivirus)

---

_Last updated: 2026-05-27_  
_Corax Orchestrator — Antivirus Interference Guide_
