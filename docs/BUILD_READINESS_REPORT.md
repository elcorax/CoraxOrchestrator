# Corax Orchestrator — Build Readiness Report

**Generated:** 2026-05-27  
**Version:** 1.0.0-alpha  
**Status:** PRE-ALPHA — Preparing for first internal executable build

---

## Overview

This report assesses the project's readiness for Windows executable packaging
using PyInstaller. It covers dependency bundling, dynamic imports, startup flow,
and runtime initialization.

## Readiness Score

| Category                  | Score    | Status                       |
| ------------------------- | -------- | ---------------------------- |
| Dependency Graph          | 8/10     | ✅ Good                      |
| Import Resolution         | 7/10     | ⚠️ Needs attention           |
| PyInstaller Compatibility | 8/10     | ✅ Good                      |
| Startup Flow              | 9/10     | ✅ Strong                    |
| Runtime Initialization    | 8/10     | ✅ Good                      |
| Dynamic Import Handling   | 7/10     | ⚠️ Needs attention           |
| Package Discovery         | 9/10     | ✅ Strong                    |
| Reproducible Builds       | 8/10     | ✅ Good                      |
| **Overall**               | **8/10** | **✅ Ready for alpha build** |

## Dependency Graph

### Core Dependencies (requirements.txt)

| Dependency   | Version | Status       | Notes                 |
| ------------ | ------- | ------------ | --------------------- |
| pyyaml       | >=6.0   | ✅ Installed | Configuration parsing |
| requests     | >=2.31  | ✅ Installed | HTTP client           |
| psutil       | >=5.9   | ✅ Installed | System monitoring     |
| aiohttp      | >=3.9   | ✅ Installed | Async HTTP            |
| httpx        | >=0.27  | ✅ Installed | HTTP client           |
| aiofiles     | >=23.2  | ✅ Installed | Async file I/O        |
| orjson       | >=3.9   | ✅ Installed | Fast JSON             |
| structlog    | >=24.1  | ✅ Installed | Structured logging    |
| rich         | >=13.7  | ✅ Installed | Terminal formatting   |
| click        | >=8.1   | ✅ Installed | CLI framework         |
| platformdirs | >=4.1   | ✅ Installed | Platform paths        |

### Build Dependencies

| Dependency                | Status           | Notes                         |
| ------------------------- | ---------------- | ----------------------------- |
| pyinstaller               | ⚠️ Not installed | Required for executable build |
| pyinstaller-hooks-contrib | ⚠️ Not installed | Additional PyInstaller hooks  |

### Internal Module Dependencies

```
src/main.py
├── src/core/logging.py
├── src/core/exceptions.py
├── src/core/config.py
├── src/health/audit.py
├── src/health/packaging.py
├── src/health/diagnostics.py
├── src/health/self_setup.py
├── src/deployment/orchestrator.py
│   ├── src/deployment/installers/base.py
│   ├── src/deployment/installers/dev_base.py
│   ├── src/deployment/installers/*.py (14 installer modules)
│   ├── src/deployment/execution/*.py (5 execution modules)
│   ├── src/deployment/models/*.py (2 model modules)
│   ├── src/deployment/profiles/*.py (2 profile modules)
│   ├── src/deployment/verification/*.py (2 verification modules)
│   ├── src/deployment/integration/*.py (2 integration modules)
│   ├── src/deployment/repair/*.py (2 repair modules)
│   ├── src/deployment/config/*.py (2 config modules)
│   ├── src/deployment/validation.py
│   ├── src/deployment/operations.py
│   └── src/deployment/windows_utils.py
├── src/agent/runtime.py
│   ├── src/agent/runtime/*.py (5 runtime modules)
│   ├── src/agent/modes/*.py (4 mode modules)
│   ├── src/agent/execution/*.py (3 execution modules)
│   ├── src/agent/execution/capabilities/*.py (8 capability modules)
│   ├── src/agent/reasoning/*.py (3 reasoning modules)
│   ├── src/agent/conversation/*.py (3 conversation modules)
│   ├── src/agent/providers/*.py (4 provider modules)
│   ├── src/agent/session.py
│   ├── src/agent/state.py
│   └── src/agent/tool_executor.py
├── src/platform/factory.py
│   ├── src/platform/base.py
│   ├── src/platform/windows.py
│   ├── src/platform/macos.py
│   └── src/platform/linux.py
├── src/utils/system.py
├── src/utils/network.py
├── src/utils/validation.py
└── src/modules/*.py (10 module files)
```

## Import Resolution

### Direct Imports — ✅ All resolved

All direct imports in `src/main.py` and core modules resolve correctly.

### Dynamic Imports — ⚠️ Needs attention

The following modules use dynamic/lazy imports that PyInstaller may miss:

| Module                               | Dynamic Import Pattern      | Risk      |
| ------------------------------------ | --------------------------- | --------- |
| `src.deployment.installers.__init__` | `__import__` or `importlib` | ⚠️ Medium |
| `src.agent.providers.registry`       | Dynamic provider loading    | ⚠️ Medium |
| `src.deployment.models.registry`     | Dynamic model loading       | ⚠️ Medium |
| `src.modules.installer_engine`       | Dynamic installer discovery | ⚠️ Medium |

**Mitigation:** All dynamic imports are listed in `corax.spec` hiddenimports.

### Legacy Shim Imports — ✅ Handled

| Shim                      | Status     | Notes                                          |
| ------------------------- | ---------- | ---------------------------------------------- |
| `src.installers.base`     | ✅ Fixed   | Now re-exports from deployment.installers.base |
| `src.installers.__init__` | ✅ Handled | Re-exports with deprecation warning            |

## PyInstaller Compatibility

### Build Configuration

| Item                | Status        | Notes                                  |
| ------------------- | ------------- | -------------------------------------- |
| `corax.spec`        | ✅ Created    | Complete spec with all hidden imports  |
| `build_windows.ps1` | ✅ Created    | PowerShell build script                |
| `build_windows.bat` | ✅ Created    | CMD build script                       |
| Hidden imports      | ✅ Listed     | 80+ hidden imports specified           |
| Excluded modules    | ✅ Listed     | 40+ excluded to reduce bundle size     |
| Data files          | ✅ Configured | config/ and data/ directories included |

### Known PyInstaller Issues

1. **Windows-specific paths**: The spec uses `os.path` which works on Windows
2. **UPX compression**: Enabled by default; may cause false positives with antivirus
3. **Console mode**: Console window is shown; required for CLI operation
4. **One-file vs one-folder**: One-folder mode recommended for alpha; one-file for distribution

## Startup Flow

```
┌─────────────────────────────────────────────────────────────┐
│                     CoraxOrchestrator.exe                    │
├─────────────────────────────────────────────────────────────┤
│ 1. Bootstrap Phase                                           │
│    ├── Validate environment                                  │
│    ├── Validate Python/runtime dependencies                  │
│    ├── Validate admin permissions                            │
│    ├── Validate PATH state                                   │
│    ├── Repair missing runtime dependencies                   │
│    └── Initialize Corax runtime                              │
├─────────────────────────────────────────────────────────────┤
│ 2. Runtime Phase                                             │
│    ├── Initialize logging system                             │
│    ├── Load configuration                                    │
│    ├── Initialize module system                              │
│    └── Verify core modules                                   │
├─────────────────────────────────────────────────────────────┤
│ 3. Deployment Phase                                          │
│    ├── Load deployment orchestrator                          │
│    ├── Initialize installer registry                         │
│    └── Prepare deployment environment                        │
├─────────────────────────────────────────────────────────────┤
│ 4. AI Provisioning Phase                                     │
│    ├── Initialize provider registry                          │
│    ├── Initialize model registry                             │
│    └── Prepare AI provisioning                                │
├─────────────────────────────────────────────────────────────┤
│ 5. Diagnostics Phase                                         │
│    ├── Generate startup diagnostics                          │
│    ├── Save diagnostic reports                               │
│    └── Report startup status                                 │
└─────────────────────────────────────────────────────────────┘
```

## Runtime Initialization

### Phase Timing Estimates

| Phase           | Estimated Duration | Notes                   |
| --------------- | ------------------ | ----------------------- |
| Bootstrap       | < 2s               | Lightweight validation  |
| Runtime         | < 3s               | Module loading          |
| Deployment      | < 3s               | Installer registration  |
| AI Provisioning | < 2s               | Provider initialization |
| Diagnostics     | < 1s               | Report generation       |
| **Total**       | **< 11s**          | Acceptable for alpha    |

### Error Recovery

| Failure Mode         | Recovery Strategy       | Status         |
| -------------------- | ----------------------- | -------------- |
| Missing dependency   | Auto-install via pip    | ✅ Implemented |
| PATH issue           | Auto-repair PATH        | ✅ Implemented |
| Missing config       | Generate default config | ✅ Implemented |
| Missing directories  | Auto-create directories | ✅ Implemented |
| Import error         | Graceful degradation    | ✅ Implemented |
| Crash during startup | Diagnostic capture      | ✅ Implemented |

## Packaging Risks

### High Priority

| Risk                      | Impact              | Mitigation                         | Status       |
| ------------------------- | ------------------- | ---------------------------------- | ------------ |
| PyInstaller not installed | Build fails         | Documented in build scripts        | ⚠️ Open      |
| Dynamic imports missed    | Runtime ImportError | Listed in corax.spec hiddenimports | ✅ Mitigated |
| Legacy shim conflicts     | Import ambiguity    | Fixed to re-export                 | ✅ Resolved  |

### Medium Priority

| Risk                   | Impact                | Mitigation                      | Status       |
| ---------------------- | --------------------- | ------------------------------- | ------------ |
| UPX false positive     | Antivirus flags exe   | Documented in testing guide     | ⚠️ Open      |
| Large bundle size      | Slow download         | Excluded unnecessary packages   | ✅ Mitigated |
| Windows-specific paths | Cross-platform issues | Platform detection in bootstrap | ✅ Mitigated |

### Low Priority

| Risk           | Impact          | Mitigation                 | Status      |
| -------------- | --------------- | -------------------------- | ----------- |
| Console window | User experience | Required for alpha         | ✅ Accepted |
| Debug symbols  | Bundle size     | Stripped in release builds | ✅ Planned  |
| Icon missing   | Visual identity | Not critical for alpha     | ✅ Accepted |

## Recommendations

### Before First Build

1. [ ] Install PyInstaller: `pip install pyinstaller pyinstaller-hooks-contrib`
2. [ ] Run `python _validate.py` to confirm zero import errors
3. [ ] Run `python scripts/runtime_bootstrap.py` to confirm bootstrap passes
4. [ ] Test `python src/main.py --health` to confirm health audit works
5. [ ] Verify all 80+ hidden imports in `corax.spec` are correct

### Before Alpha Release

1. [ ] Add application icon (`.ico` file)
2. [ ] Add version metadata to executable
3. [ ] Test on clean Windows VM
4. [ ] Test with antivirus enabled
5. [ ] Generate signed build for distribution

---

_Report generated by Corax Orchestrator Build Readiness System_
