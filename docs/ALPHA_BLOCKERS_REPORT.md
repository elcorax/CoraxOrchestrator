# Corax Orchestrator — Alpha Blockers Report

**Generated:** 2026-05-27  
**Version:** 1.0.0-alpha  
**Status:** PRE-ALPHA — Blockers identified for resolution

---

## Overview

This report identifies all critical blockers, warnings, and issues that must be
resolved before the first internal alpha executable can be considered stable.

## Blocker Summary

| Severity    | Count | Action Required                |
| ----------- | ----- | ------------------------------ |
| 🔴 Critical | 1     | Must resolve before build      |
| 🟡 High     | 3     | Should resolve before alpha    |
| 🟠 Medium   | 4     | Resolve during alpha iteration |
| 🔵 Low      | 5     | Track for beta                 |

---

## 🔴 Critical Blockers

### B1 — PyInstaller Not Installed

**Description:** PyInstaller is required to build the Windows executable but is
not currently installed in the development environment.

**Impact:** Cannot build `CoraxOrchestrator.exe`.

**Resolution:**

```powershell
pip install pyinstaller pyinstaller-hooks-contrib
```

**Status:** ⏳ Pending

---

## 🟡 High Priority Blockers

### H1 — Dynamic Import Coverage Verification

**Description:** The `corax.spec` file lists 80+ hidden imports, but these have
not been verified against actual runtime import behavior. Some modules may be
missed, causing `ImportError` at runtime.

**Impact:** Executable may crash on startup with missing module errors.

**Resolution:**

1. Build the executable
2. Run it and check for `ImportError`
3. Add any missing modules to `corax.spec` hiddenimports
4. Repeat until clean startup

**Status:** ⏳ Pending

### H2 — Clean Machine Testing

**Description:** The executable has not been tested on a clean Windows machine
without Python or development tools installed.

**Impact:** Unknown whether the executable can bootstrap itself in a clean
environment.

**Resolution:**

1. Build the executable
2. Copy to a clean Windows VM
3. Run and verify bootstrap self-healing
4. Document any failures

**Status:** ⏳ Pending

### H3 — Antivirus Interference

**Description:** PyInstaller-packaged executables are frequently flagged by
antivirus software as false positives, especially when UPX compression is used.

**Impact:** Executable may be quarantined or blocked on user machines.

**Resolution:**

1. Build without UPX compression as a test
2. Submit to Microsoft Defender for whitelisting
3. Document known antivirus issues

**Status:** ⏳ Pending

---

## 🟠 Medium Priority Blockers

### M1 — Legacy Shim Deprecation Warnings

**Description:** The `src/installers/base.py` module now emits deprecation
warnings. While functional, these warnings may confuse users during alpha
testing.

**Impact:** User confusion; noisy startup output.

**Resolution:**

- Suppress deprecation warnings in production builds
- Or remove legacy shims entirely

**Status:** ⏳ Pending

### M2 — Application Icon Missing

**Description:** The executable has no icon file specified in `corax.spec`.

**Impact:** Executable uses default PyInstaller icon; unprofessional appearance.

**Resolution:**

- Create or source a `.ico` file
- Add to `corax.spec`: `icon='corax.ico'`

**Status:** ⏳ Pending

### M3 — Version Metadata Missing

**Description:** The executable has no embedded version metadata (File version,
Product version, etc.).

**Impact:** Users cannot easily identify the build version from file properties.

**Resolution:**

- Create a version resource file (`.rc`)
- Compile and link into the executable
- Or use PyInstaller's `--version-file` option

**Status:** ⏳ Pending

### M4 — Startup Performance Baseline

**Description:** No performance baseline has been established for startup time.

**Impact:** Cannot detect performance regressions during alpha iteration.

**Resolution:**

1. Build the executable
2. Measure startup time on reference hardware
3. Document baseline in `STARTUP_DIAGNOSTICS.md`

**Status:** ⏳ Pending

---

## 🔵 Low Priority Blockers

### L1 — Cross-Platform Build Testing

**Description:** Build scripts have only been tested on Windows.

**Impact:** macOS and Linux builds may have issues.

**Resolution:**

- Test build scripts on macOS and Linux
- Document platform-specific differences

**Status:** ⏳ Pending

### L2 — Code Signing

**Description:** The executable is not code-signed.

**Impact:** Windows SmartScreen may block the executable.

**Resolution:**

- Obtain a code signing certificate
- Sign the executable during build

**Status:** ⏳ Pending

### L3 — Installer Creation

**Description:** No installer (MSI/InnoSetup) has been created.

**Impact:** Users must manually extract and configure the executable.

**Resolution:**

- Create an InnoSetup or WiX installer script
- Include in build pipeline

**Status:** ⏳ Pending

### L4 — Automated Build Pipeline

**Description:** Build process is manual (run scripts).

**Impact:** No CI/CD integration for reproducible builds.

**Resolution:**

- Set up GitHub Actions or similar CI
- Automate build, test, and deploy

**Status:** ⏳ Pending

### L5 — User Documentation

**Description:** No end-user documentation for running the executable.

**Impact:** Users may not know how to configure or troubleshoot.

**Resolution:**

- Create a user guide
- Include README with executable

**Status:** ⏳ Pending

---

## Unstable Modules

The following modules have been identified as potentially unstable for the
alpha build:

| Module                                     | Risk      | Reason                                                 |
| ------------------------------------------ | --------- | ------------------------------------------------------ |
| `src.agent.runtime.engine`                 | ⚠️ Medium | Complex async runtime; limited test coverage           |
| `src.deployment.execution.executor`        | ⚠️ Medium | Heavy async orchestration; many dependencies           |
| `src.deployment.installers.*`              | ⚠️ Medium | 14 installer modules; some may have import issues      |
| `src.agent.execution.capabilities.browser` | ⚠️ Low    | Browser automation; may fail without browser installed |
| `src.agent.execution.capabilities.desktop` | ⚠️ Low    | Desktop automation; platform-specific                  |

## Missing Dependencies

| Dependency                | Required By    | Status           |
| ------------------------- | -------------- | ---------------- |
| pyinstaller               | Build pipeline | ⚠️ Not installed |
| pyinstaller-hooks-contrib | Build pipeline | ⚠️ Not installed |

## Packaging Risks

| Risk                                  | Severity | Status                                  |
| ------------------------------------- | -------- | --------------------------------------- |
| Dynamic imports missed by PyInstaller | High     | ✅ Mitigated (listed in corax.spec)     |
| Legacy shim import conflicts          | Medium   | ✅ Resolved (re-export shim)            |
| UPX false positive with antivirus     | Medium   | ⚠️ Open                                 |
| Large bundle size (>200MB)            | Low      | ✅ Mitigated (excluded packages)        |
| Missing data files in bundle          | Medium   | ✅ Mitigated (configured in corax.spec) |

---

## Resolution Tracking

| Blocker                          | Assigned | Target             | Status |
| -------------------------------- | -------- | ------------------ | ------ |
| B1 — PyInstaller installation    | —        | Before first build | ⏳     |
| H1 — Dynamic import verification | —        | Before alpha       | ⏳     |
| H2 — Clean machine testing       | —        | Before alpha       | ⏳     |
| H3 — Antivirus interference      | —        | Before alpha       | ⏳     |
| M1 — Legacy shim warnings        | —        | Alpha iteration    | ⏳     |
| M2 — Application icon            | —        | Alpha iteration    | ⏳     |
| M3 — Version metadata            | —        | Alpha iteration    | ⏳     |
| M4 — Performance baseline        | —        | Alpha iteration    | ⏳     |

---

_Report generated by Corax Orchestrator Alpha Blockers System_
