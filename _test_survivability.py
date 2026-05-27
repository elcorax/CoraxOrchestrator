"""
Comprehensive Survivability & GUI Validation Test.
Validates: GUI panels, restore points, timeout manager,
recovery engine, self-healing, retry queue, failure analysis,
preflight validation, and persistence.
"""
import sys
import os
sys.path.insert(0, os.getcwd())
os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ["CORAX_SKIP_GUI_INIT"] = "1"

errors = []
ok_count = 0

def test(name, func):
    global ok_count
    try:
        func()
        print("  OK " + name)
        ok_count += 1
    except Exception as e:
        errors.append(name + ": " + str(e))
        print("  FAIL " + name + ": " + str(e))

# 1. GUI Panel imports (all 9)
print("=== GUI Panels ===")
import importlib

panel_map = {
    "DashboardPanel": "src.gui.panels.dashboard",
    "DeploymentProgressPanel": "src.gui.panels.deployment_progress",
    "ToolSelectionPanel": "src.gui.panels.tool_selection",
    "DeploymentControlPanel": "src.gui.panels.deployment_control",
    "PermissionsPanel": "src.gui.panels.permissions",
    "ReportsViewerPanel": "src.gui.panels.reports_viewer",
    "RuntimeMonitorPanel": "src.gui.panels.runtime_monitor",
    "ConsoleViewerPanel": "src.gui.panels.console_viewer",
    "SettingsPanel": "src.gui.panels.settings",
}

for name, mod_path in panel_map.items():
    test(name, lambda mn=name, mp=mod_path: getattr(importlib.import_module(mp), mn))

# 2. UI State
print("\n=== UI State ===")
test("UIStateManager", lambda: (
    importlib.import_module("src.gui.ui_state").ui_state.__setattr__("runtime_status", "Testing"),
    importlib.import_module("src.gui.ui_state").ui_state.__setattr__("system_health", "OK"),
))

# 3. Restore Point
print("\n=== Restore Point ===")
test("WindowsRestorePoint", lambda: importlib.import_module("src.deployment.restore.windows_restore").WindowsRestorePoint().get_status_report())

# 4. Timeout Manager
print("\n=== Timeout Manager ===")
test("TimeoutManager", lambda: importlib.import_module("src.runtime.timeout_manager").TimeoutManager())

# 5. Recovery Engine
print("\n=== Recovery Engine ===")
test("StartupRecovery", lambda: importlib.import_module("src.runtime.recovery").StartupRecovery())

# 6. Self-Healing
print("\n=== Self-Healing ===")
test("SelfHealingEngine", lambda: importlib.import_module("src.modules.self_healing").SelfHealingEngine())

# 7. Retry Queue
print("\n=== Retry Queue ===")
test("RetryQueue", lambda: importlib.import_module("src.deployment.execution.retry_queue").RetryQueue())

# 8. Failure Analyzer
print("\n=== Failure Analyzer ===")
test("FailureAnalyzer", lambda: importlib.import_module("src.deployment.execution.failure_analyzer").FailureAnalyzer())

# 9. State Persistence
print("\n=== State Persistence ===")
test("StatePersistence", lambda: importlib.import_module("src.modules.state_persistence").StatePersistence())

# 10. Preflight
print("\n=== Preflight ===")
test("EnvironmentPreflight", lambda: importlib.import_module("src.deployment.preflight").EnvironmentPreflight())

# 11. Agent Systems
print("\n=== Agent Systems ===")
test("AgentSession", lambda: importlib.import_module("src.agent.session").AgentSession(session_id="test"))
test("AgentState", lambda: importlib.import_module("src.agent.state").AgentState())
test("ToolExecutor", lambda: importlib.import_module("src.agent.tool_executor").ToolExecutor())

# 12. Diagnostics
print("\n=== Diagnostics ===")
test("StartupDiagnostics", lambda: importlib.import_module("src.health.diagnostics").StartupDiagnostics())
test("RuntimeDiagnostics", lambda: importlib.import_module("src.runtime.diagnostics").RuntimeDiagnostics())
test("ProjectHealthAudit", lambda: importlib.import_module("src.health.audit").ProjectHealthAudit())

# Summary
print("\n" + "=" * 60)
total = ok_count + len(errors)
if errors:
    print("  FAILURES: " + str(len(errors)) + "/" + str(total))
    for e in errors:
        print("    - " + e)
    sys.exit(1)
else:
    print("  ALL " + str(total) + " SURVIVABILITY & GUI TESTS PASSED")
    sys.exit(0)
