# -*- mode: python ; coding: utf-8 -*-
"""
Corax Orchestrator - PyInstaller Build Specification.

Builds a standalone Windows executable with:
- GUI (PySide6 - lightweight, NO WebEngine)
- Runtime kernel
- Deployment engine
- All installers
- Health/self-healing systems
- Agent systems
- Platform abstractions

CRITICAL FIXES APPLIED:
1. ✅ Platform module shadowing resolved via hook-platform.py
2. ✅ Platform module shadowing resolved via runtime_platform_fix.py
3. ✅ UPX disabled (causes DLL corruption on some Windows configs)
4. ✅ PySide6.QtWebEngineWidgets removed (heavy, unnecessary, hook recursion)
5. ✅ Console mode ON for first builds (debug visibility)
6. ✅ Optimized hidden imports (no redundant entries)
7. ✅ Hookspath configured for custom hooks

Usage:
    pyinstaller --clean --noconfirm corax.spec
"""

import sys
import os
from pathlib import Path

# Project paths
PROJECT_DIR = os.getcwd()
SRC_DIR = os.path.join(PROJECT_DIR, "src")
DATA_DIR = os.path.join(PROJECT_DIR, "data")
CONFIG_DIR = os.path.join(PROJECT_DIR, "config")
ASSETS_DIR = os.path.join(PROJECT_DIR, "assets")
HOOKS_DIR = os.path.join(PROJECT_DIR, "hooks")

# Collect all data files (critical for runtime operation)
datas = [
    (CONFIG_DIR, "config"),
    (DATA_DIR, "data"),
]

# Include branding assets
if os.path.isdir(ASSETS_DIR):
    datas.append((ASSETS_DIR, "assets"))

# 🟢 CORE hidden imports - minimal, no redundancy
hiddenimports = [
    # 🟢 Standard library (critical for runtime)
    "asyncio",
    "concurrent",
    "concurrent.futures",
    "shutil",
    "tempfile",
    "uuid",
    "hashlib",
    "io",
    "statistics",
    "zlib",
    "gc",

    # Core
    "src",
    "src.core",
    "src.core.config",
    "src.core.exceptions",
    "src.core.logging",

    # GUI
    "src.gui",
    "src.gui.ui_state",
    "src.gui.application",
    "src.gui.main_window",
    "src.gui.panels",
    "src.gui.panels.dashboard",
    "src.gui.panels.deployment_progress",
    "src.gui.panels.tool_selection",
    "src.gui.panels.deployment_control",
    "src.gui.panels.permissions",
    "src.gui.panels.reports_viewer",
    "src.gui.panels.runtime_monitor",
    "src.gui.panels.settings",
    "src.gui.panels.console_viewer",

    # Runtime
    "src.runtime",
    "src.runtime.kernel",
    "src.runtime.bootstrap",
    "src.runtime.lifecycle",
    "src.runtime.recovery",
    "src.runtime.state",
    "src.runtime.diagnostics",
    "src.runtime.bridge",
    "src.runtime.state_bus",

    # Deployment
    "src.deployment",
    "src.deployment.orchestrator",
    "src.deployment.preflight",
    "src.deployment.validation",
    "src.deployment.unattended",
    "src.deployment.ai_stack",
    "src.deployment.dev_deploy",
    "src.deployment.windows_utils",
    "src.deployment.operations",
    "src.deployment.portable",
    "src.deployment.restore",
    "src.deployment.restore.windows_restore",
    "src.deployment.execution",
    "src.deployment.execution.executor",
    "src.deployment.execution.session",
    "src.deployment.execution.terminal",
    "src.deployment.execution.retry_queue",
    "src.deployment.execution.failure_analyzer",
    "src.deployment.installers",
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
    "src.deployment.installers.windsurf_installer",
    "src.deployment.installers.java_installer",
    "src.deployment.installers.flutter_installer",
    "src.deployment.installers.docker_installer",
    "src.deployment.installers.dev_base",
    "src.deployment.models",
    "src.deployment.models.registry",
    "src.deployment.models.recommender",
    "src.deployment.profiles",
    "src.deployment.profiles.manager",
    "src.deployment.profiles.base",
    "src.deployment.verification",
    "src.deployment.verification.base",
    "src.deployment.verification.health",
    "src.deployment.integration",
    "src.deployment.integration.base",
    "src.deployment.integration.manager",
    "src.deployment.repair",
    "src.deployment.repair.base",
    "src.deployment.repair.engine",
    "src.deployment.config",
    "src.deployment.config.base",
    "src.deployment.config.manager",

    # Modules
    "src.modules",
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

    # Platform (already disambiguated via hook/runtime-fix)
    "src.platform",
    "src.platform.base",
    "src.platform.factory",
    "src.platform.windows",
    "src.platform.macos",
    "src.platform.linux",

    # Sysenv (platform abstraction layer)
    "src.sysenv",
    "src.sysenv.base",
    "src.sysenv.factory",
    "src.sysenv.windows",
    "src.sysenv.macos",
    "src.sysenv.linux",

    # Utils
    "src.utils",
    "src.utils.system",
    "src.utils.network",
    "src.utils.validation",

    # Health
    "src.health",
    "src.health.self_setup",
    "src.health.diagnostics",
    "src.health.audit",
    "src.health.packaging",

    # Agent
    "src.agent",
    "src.agent.session",
    "src.agent.state",
    "src.agent.runtime",
    "src.agent.runtime.lifecycle",
    "src.agent.runtime.scheduler",
    "src.agent.runtime.recovery",
    "src.agent.runtime.loop",
    "src.agent.runtime.engine",
    "src.agent.modes",
    "src.agent.modes.base",
    "src.agent.modes.safe_mode",
    "src.agent.modes.assisted_mode",
    "src.agent.modes.autonomous_mode",
    "src.agent.execution",
    "src.agent.execution.engine",
    "src.agent.execution.workflow",
    "src.agent.execution.context",
    "src.agent.execution.capabilities",
    "src.agent.execution.capabilities.base",
    "src.agent.execution.capabilities.terminal",
    "src.agent.execution.capabilities.process",
    "src.agent.execution.capabilities.installer_interaction",
    "src.agent.execution.capabilities.desktop",
    "src.agent.execution.capabilities.browser",
    "src.agent.execution.capabilities.sandbox",
    "src.agent.execution.capabilities.recovery",
    "src.agent.reasoning",
    "src.agent.reasoning.engine",
    "src.agent.reasoning.planner",
    "src.agent.reasoning.decisions",
    "src.agent.conversation",
    "src.agent.conversation.history",
    "src.agent.conversation.context",
    "src.agent.conversation.messages",
    "src.agent.tool_executor",

    # Installers (legacy)
    "src.installers",
    "src.installers.base",

    # PySide6 (MINIMAL - no WebEngine to avoid hook recursion)
    "PySide6",
    "PySide6.QtCore",
    "PySide6.QtWidgets",
    "PySide6.QtGui",

    # Third party (explicit to avoid recursive analysis)
    "yaml",
    "aiohttp",
    "aiofiles",
    "psutil",
    "requests",
    "packaging",
    "jsonschema",
    "tenacity",
    "wmi",
    "win32api",
    "win32com",
    "msgpack",
    "watchdog",
    "huggingface_hub",
    "structlog",
    "orjson",
    "click",
    "rich",
    "httpx",
    "platformdirs",
]

# Exclude test modules and heavy unused packages
excludes = [
    "test",
    "tests",
    "unittest",
    "pytest",
    "tkinter",
    "matplotlib",
    "scipy",
    "numpy",
    "pandas",
    "PIL",
    "cv2",
    "tensorflow",
    "torch",
    "transformers",
    "notebook",
    "jupyter",
    "ipython",
    "PySide6.QtWebEngineWidgets",
    "PySide6.QtWebEngineCore",
    "PySide6.QtWebChannel",
    "PySide6.QtQml",
    "PySide6.QtQuick",
    "PySide6.QtSvg",
    "PySide6.QtNetwork",
    "PySide6.QtTest",
    "PySide6.QtBluetooth",
    "PySide6.QtNfc",
    "PySide6.QtPositioning",
    "PySide6.QtSensors",
    "PySide6.QtSerialPort",
    "PySide6.QtXml",
    "PySide6.QtDBus",
    "PySide6.QtHelp",
    "PySide6.QtMultimedia",
    "PySide6.QtPrintSupport",
    "PySide6.QtSql",
]

a = Analysis(
    ['src/main.py'],
    pathex=[PROJECT_DIR, SRC_DIR],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[HOOKS_DIR],       # 🟢 Custom hooks path for platform fix
    hooksconfig={},
    runtime_hooks=[os.path.join(HOOKS_DIR, "runtime_platform_fix.py")],  # 🟢 Runtime hook for platform fix
    excludes=excludes,
    noarchive=False,
    optimize=1,
)

pyz = PYZ(a.pure)

# 🟢 UPX disabled - causes DLL corruption on Windows with PySide6
# 🟢 Console=True for alpha builds - critical for debugging

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='corax',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,                          # 🟢 DISABLED UPX
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,                       # 🟢 Console ON for alpha debugging
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='assets/branding/corax_logo.ico' if os.path.exists('assets/branding/corax_logo.ico') else None,
)

# Debug version with same fixes
exe_debug = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='corax_debug',
    debug=True,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,                          # 🟢 DISABLED UPX
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='assets/branding/corax_logo.ico' if os.path.exists('assets/branding/corax_logo.ico') else None,
)
