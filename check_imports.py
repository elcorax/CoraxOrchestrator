"""
Comprehensive import validation for Corax Orchestrator.

Checks all critical modules and third-party packages
to ensure the runtime environment is complete.
"""
import sys
import os
import importlib

sys.path.insert(0, ".")

REQUIRED_PACKAGES = [
    # Core
    ("yaml", "PyYAML"),
    ("psutil", "psutil"),
    ("platformdirs", "platformdirs"),
    ("aiohttp", "aiohttp"),
    ("httpx", "httpx"),
    ("aiofiles", "aiofiles"),
    ("orjson", "orjson"),
    ("msgpack", "msgpack"),
    ("structlog", "structlog"),
    ("rich", "rich"),
    ("click", "click"),
    ("packaging", "packaging"),
    ("jsonschema", "jsonschema"),
    ("tenacity", "tenacity"),
    ("watchdog", "watchdog"),

    # Windows
    ("win32api", "pywin32"),
    ("wmi", "wmi"),

    # GUI
    ("PySide6", "PySide6"),
    ("PySide6.QtCore", "PySide6"),
    ("PySide6.QtWidgets", "PySide6"),
    ("PySide6.QtGui", "PySide6"),

    # Model management
    ("huggingface_hub", "huggingface-hub"),
]

CRITICAL_MODULES = [
    "src.main",
    "src.core.config",
    "src.core.logging",
    "src.core.exceptions",
    "src.runtime.kernel",
    "src.runtime.state",
    "src.runtime.bootstrap",
    "src.runtime.bridge",
    "src.runtime.state_bus",
    "src.runtime.timeout_manager",
    "src.runtime.diagnostics",
    "src.runtime.recovery",
    "src.runtime.lifecycle",
    "src.gui.application",
    "src.gui.main_window",
    "src.gui.ui_state",
    "src.gui.panels.dashboard",
    "src.gui.panels.deployment_progress",
    "src.gui.panels.tool_selection",
    "src.gui.panels.deployment_control",
    "src.gui.panels.permissions",
    "src.gui.panels.reports_viewer",
    "src.gui.panels.runtime_monitor",
    "src.gui.panels.settings",
    "src.gui.panels.console_viewer",
    "src.deployment.orchestrator",
    "src.deployment.preflight",
    "src.deployment.validation",
    "src.deployment.unattended",
    "src.deployment.ai_stack",
    "src.deployment.dev_deploy",
    "src.deployment.windows_utils",
    "src.deployment.operations",
    "src.deployment.portable",
    "src.deployment.restore.windows_restore",
    "src.deployment.execution.executor",
    "src.deployment.execution.session",
    "src.deployment.execution.terminal",
    "src.deployment.execution.retry_queue",
    "src.deployment.execution.failure_analyzer",
    "src.deployment.installers.base",
    "src.deployment.installers.ollama",
    "src.deployment.installers.lm_studio",
    "src.deployment.installers.open_webui",
    "src.deployment.installers.anythingllm",
    "src.deployment.installers.comfyui",
    "src.deployment.installers.open_interpreter",
    "src.deployment.installers.git_installer",
    "src.deployment.installers.python_installer",
    "src.deployment.installers.node_installer",
    "src.deployment.installers.vscode_installer",
    "src.deployment.installers.docker_installer",
    "src.deployment.models.registry",
    "src.deployment.models.recommender",
    "src.deployment.profiles.manager",
    "src.deployment.verification.health",
    "src.deployment.integration.manager",
    "src.deployment.repair.engine",
    "src.deployment.config.manager",
    "src.modules.system_scanner",
    "src.modules.environment_analyzer",
    "src.modules.tool_registry",
    "src.modules.installer_engine",
    "src.modules.model_manager",
    "src.modules.permission_manager",
    "src.modules.state_persistence",
    "src.modules.reporting",
    "src.modules.self_healing",
    "src.modules.task_orchestrator",
    "src.platform.base",
    "src.platform.factory",
    "src.platform.windows",
    "src.utils.system",
    "src.utils.network",
    "src.utils.validation",
    "src.health.self_setup",
    "src.health.diagnostics",
    "src.health.audit",
    "src.health.packaging",
]

failed_any = False

print("=" * 70)
print("Corax Orchestrator - Import Validation")
print("=" * 70)

# 1. Third-party packages
print("\n--- Third-Party Packages ---")
for module_name, package_name in REQUIRED_PACKAGES:
    try:
        mod = importlib.import_module(module_name)
        ver = getattr(mod, "__version__", "unknown")
        print(f"  ✓ {module_name:30s} ({package_name:20s}) version {ver}")
    except ImportError as e:
        print(f"  ✗ {module_name:30s} ({package_name:20s}) MISSING: {e}")
        failed_any = True

# 2. Project modules
print("\n--- Project Modules ---")
for mod_name in CRITICAL_MODULES:
    try:
        __import__(mod_name)
        print(f"  ✓ {mod_name}")
    except Exception as e:
        print(f"  ✗ {mod_name}: {e}")
        failed_any = True

# Summary
print("\n" + "=" * 70)
if failed_any:
    print("  ❌ IMPORT VALIDATION FAILED - some imports are missing")
    sys.exit(1)
else:
    print("  ✅ IMPORT VALIDATION PASSED - all imports resolved")
    sys.exit(0)
