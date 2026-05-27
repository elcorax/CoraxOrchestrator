# Corax Orchestrator — Startup Diagnostics Reference

**Version:** 1.0.0-alpha  
**Purpose:** Reference for interpreting startup diagnostics and troubleshooting

---

## Overview

The Corax Orchestrator startup diagnostics system captures detailed information
about every startup phase. Diagnostics are saved as both JSON (for programmatic
analysis) and Markdown (for human review).

## Diagnostic File Locations

```
data/logs/
├── startup_diagnostics_<timestamp>.json    # Machine-readable diagnostics
├── startup_diagnostics_<timestamp>.md      # Human-readable report
├── bootstrap.log                           # Bootstrap phase log
└── build.log                               # Build process log
```

## Diagnostic Structure

### Top-Level Fields

```json
{
  "timestamp": "2026-05-27T12:00:00+00:00",
  "success": true,
  "phase": "initialization",
  "system_info": { ... },
  "bootstrap_phase": { ... },
  "runtime_phase": { ... },
  "deployment_phase": { ... },
  "ai_provisioning_phase": { ... },
  "errors": [ ... ],
  "warnings": [ ... ],
  "performance": { ... },
  "dependency_status": { ... },
  "crash_info": null
}
```

### System Information

Contains platform, Python version, and hardware details:

| Field                 | Description          | Example                     |
| --------------------- | -------------------- | --------------------------- |
| `platform`            | Full platform string | `Windows-10-10.0.19045-SP0` |
| `platform_system`     | OS name              | `Windows`                   |
| `python_version`      | Python version       | `3.12.3`                    |
| `architecture`        | CPU architecture     | `AMD64`                     |
| `cpu_count`           | Logical CPU cores    | `16`                        |
| `memory_total_gb`     | Total RAM            | `32.0`                      |
| `memory_available_gb` | Available RAM        | `24.5`                      |

### Phase Diagnostics

Each startup phase records:

```json
{
  "status": "success",
  "duration_ms": 1234.56,
  "errors": []
}
```

**Status Values:**

- `success` — Phase completed without issues
- `failed` — Phase encountered errors
- `warning` — Phase completed with non-critical issues

### Error Structure

```json
{
  "phase": "bootstrap",
  "message": "Dependency 'yaml' not found",
  "detail": "Required for configuration parsing",
  "traceback": "Traceback (most recent call last):\n  ..."
}
```

### Dependency Status

```json
{
  "yaml": "ok",
  "requests": "ok",
  "psutil": "missing",
  "aiohttp": "ok"
}
```

**Status Values:**

- `ok` — Dependency is available
- `missing` — Dependency is not installed
- `error` — Dependency failed to load

## Interpreting Diagnostics

### Success Indicators

```
✅ SUCCESS — All phases completed without errors
✅ All dependencies available
✅ Clean startup with no warnings
```

### Warning Indicators

```
⚠️ WARNING — Non-critical issues found
- Missing optional dependencies
- Non-admin permissions
- PATH issues
```

### Failure Indicators

```
❌ FAILED — Critical issues found
- Missing required dependencies
- Import errors
- Configuration errors
- Crash during startup
```

## Common Issues and Solutions

### Issue: ImportError on Startup

**Diagnostic Pattern:**

```json
{
  "phase": "runtime",
  "message": "No module named 'src.deployment.orchestrator'"
}
```

**Solutions:**

1. Ensure all hidden imports are specified in PyInstaller build config
2. Check that the module exists in the source tree
3. Verify the import path is correct
4. Add missing module to `hiddenimports` in build script

### Issue: Missing Dependency

**Diagnostic Pattern:**

```json
{
  "dependency_status": {
    "pyyaml": "missing"
  }
}
```

**Solutions:**

1. Install the missing dependency: `pip install pyyaml`
2. Ensure dependency is listed in `requirements.txt`
3. For bundled executables, ensure dependency is included in build

### Issue: Crash During Bootstrap

**Diagnostic Pattern:**

```json
{
  "crash_info": {
    "type": "PermissionError",
    "message": "[Errno 13] Permission denied: 'data/logs'"
  }
}
```

**Solutions:**

1. Run with administrator privileges
2. Check directory permissions
3. Ensure data directories exist

### Issue: Slow Startup

**Diagnostic Pattern:**

```json
{
  "performance": {
    "total_startup_time": 45.2
  }
}
```

**Solutions:**

1. Check for excessive import time
2. Reduce dynamic imports
3. Optimize module loading order
4. Consider lazy loading for non-critical modules

## Diagnostic API

### Programmatic Access

```python
from src.health.diagnostics import StartupDiagnostics, DiagnosticReport

# Create diagnostics instance
diag = StartupDiagnostics()

# Collect system info
diag.collect_system_info()

# Track phases
diag.start_phase("bootstrap")
# ... bootstrap logic ...
diag.end_phase("bootstrap", status="success")

# Check dependencies
diag.check_dependencies({
    "pyyaml": "yaml",
    "requests": "requests",
})

# Record errors
diag.record_error("runtime", "Failed to load config", "Config file not found")

# Capture crashes
try:
    risky_operation()
except Exception:
    diag.capture_crash()

# Finalize and save
report = diag.finalize(success=True)
filepath = diag.save_report()
```

### Loading Saved Reports

```python
from src.health.diagnostics import DiagnosticReport

report = DiagnosticReport.load_report("data/logs/startup_diagnostics_20260527_120000.json")
print(report.to_markdown())
```

## Diagnostic Report Example

```markdown
# Corax Orchestrator — Startup Diagnostics Report

**Generated:** 2026-05-27T12:00:00+00:00
**Status:** ✅ SUCCESS
**Phase:** ai_provisioning

---

## System Information

- **platform:** Windows-10-10.0.19045-SP0
- **python_version:** 3.12.3 (tags/v3.12.3:...)
- **architecture:** AMD64
- **cpu_count:** 16
- **memory_total_gb:** 32.0

---

## Startup Phases

### ✅ Bootstrap Phase

- **Status:** success
- **Duration:** 2345.67ms

### ✅ Runtime Phase

- **Status:** success
- **Duration:** 4567.89ms

### ✅ Deployment Phase

- **Status:** success
- **Duration:** 1234.56ms

### ✅ AI Provisioning Phase

- **Status:** success
- **Duration:** 890.12ms

---

## Dependency Status

| Dependency | Status |
| ---------- | ------ |
| yaml       | ✅ ok  |
| requests   | ✅ ok  |
| aiohttp    | ✅ ok  |

---

## Performance

- **total_startup_time:** 9.04s

---

_Report generated by Corax Orchestrator Diagnostics System_
```

## Diagnostic Best Practices

1. **Always check diagnostics after startup** — They contain the most detailed
   information about what happened during initialization.

2. **Compare diagnostics across runs** — Consistent diagnostics indicate stable
   behavior. Changes may indicate regressions.

3. **Include diagnostics in bug reports** — The JSON format is machine-readable
   and contains all necessary context for debugging.

4. **Monitor startup time trends** — Increasing startup times may indicate
   accumulating issues or regressions.

5. **Check dependency status first** — Missing dependencies are the most common
   cause of startup failures.

---

_Last updated: 2026-05-27_  
_Corax Orchestrator — Startup Diagnostics Reference_
