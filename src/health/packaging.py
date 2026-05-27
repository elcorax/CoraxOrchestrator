"""
Corax Orchestrator - Packaging Validator.

Validates project readiness for PyInstaller executable packaging.
Checks entry points, dynamic imports, dependency bundling,
and startup flow compatibility.
"""

from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field
from datetime import datetime, timezone
import ast
import importlib
import os
import sys
from pathlib import Path


@dataclass
class PackagingValidationResult:
    """Result of packaging validation."""
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    valid: bool = False
    score: float = 0.0
    issues: List[Dict[str, Any]] = field(default_factory=list)
    warnings: List[Dict[str, Any]] = field(default_factory=list)
    info: List[Dict[str, Any]] = field(default_factory=list)

    # Entry point validation
    entry_point_found: bool = False
    entry_point_valid: bool = False
    entry_point_issues: List[str] = field(default_factory=list)

    # Import analysis
    total_imports: int = 0
    stdlib_imports: int = 0
    third_party_imports: int = 0
    local_imports: int = 0
    dynamic_imports: List[str] = field(default_factory=list)
    hidden_imports: List[str] = field(default_factory=list)

    # PyInstaller compatibility
    pyinstaller_available: bool = False
    pyinstaller_version: Optional[str] = None
    spec_file_exists: bool = False
    build_script_exists: bool = False

    # Bundle analysis
    bundle_size_estimate_mb: float = 0.0
    recommended_hidden_imports: List[str] = field(default_factory=list)
    data_files_to_include: List[str] = field(default_factory=list)


class PackagingValidator:
    """
    Validates project packaging readiness for PyInstaller.

    Analyzes import graphs, entry points, and runtime startup
    to ensure compatibility with executable bundling.
    """

    def __init__(self, project_root: Optional[str] = None):
        self._project_root = project_root or os.getcwd()
        self._src_dir = os.path.join(self._project_root, "src")
        self._result = PackagingValidationResult()

    def validate(self) -> PackagingValidationResult:
        """Run complete packaging validation."""
        self._result = PackagingValidationResult()

        self._validate_entry_point()
        self._analyze_imports()
        self._check_pyinstaller()
        self._check_build_artifacts()
        self._estimate_bundle()
        self._calculate_score()

        return self._result

    def _validate_entry_point(self) -> None:
        """Validate the main entry point for packaging."""
        main_py = os.path.join(self._src_dir, "main.py")

        if not os.path.exists(main_py):
            self._result.entry_point_found = False
            self._result.issues.append({
                "category": "entry_point",
                "severity": "critical",
                "message": "src/main.py not found",
            })
            return

        self._result.entry_point_found = True

        try:
            with open(main_py, "r", encoding="utf-8") as f:
                tree = ast.parse(f.read(), filename=main_py)

            has_main_guard = False
            has_main_call = False
            for node in ast.walk(tree):
                if isinstance(node, ast.If):
                    if (isinstance(node.test, ast.Compare) and
                        isinstance(node.test.left, ast.Name) and
                        node.test.left.id == "__name__" and
                        isinstance(node.test.comparators[0], ast.Constant) and
                        node.test.comparators[0].value == "__main__"):
                        has_main_guard = True
                if isinstance(node, ast.Call):
                    if isinstance(node.func, ast.Attribute) and node.func.attr == "main":
                        has_main_call = True
                    elif isinstance(node.func, ast.Name) and node.func.id == "main":
                        has_main_call = True

            if not has_main_guard:
                self._result.entry_point_issues.append(
                    "Missing `if __name__ == '__main__'` guard"
                )
                self._result.warnings.append({
                    "category": "entry_point",
                    "severity": "warning",
                    "message": "Entry point missing __main__ guard",
                    "detail": "PyInstaller requires proper entry point structure",
                })

            if not has_main_call:
                self._result.entry_point_issues.append(
                    "No main() function call detected in entry point"
                )
                self._result.warnings.append({
                    "category": "entry_point",
                    "severity": "warning",
                    "message": "Entry point may not have a main() call",
                })

            self._result.entry_point_valid = len(self._result.entry_point_issues) == 0

        except SyntaxError as e:
            self._result.entry_point_valid = False
            self._result.issues.append({
                "category": "entry_point",
                "severity": "critical",
                "message": f"Syntax error in entry point: {e}",
            })

    def _analyze_imports(self) -> None:
        """Analyze all imports for packaging compatibility."""
        src_path = Path(self._src_dir)
        all_imports: Dict[str, str] = {}

        for py_file in src_path.rglob("*.py"):
            try:
                with open(py_file, "r", encoding="utf-8") as f:
                    content = f.read()
                    tree = ast.parse(content, filename=str(py_file))

                for node in ast.walk(tree):
                    if isinstance(node, ast.Import):
                        for alias in node.names:
                            self._categorize_import(alias.name, all_imports)
                    elif isinstance(node, ast.ImportFrom):
                        if node.module:
                            self._categorize_import(node.module, all_imports)

                if "__import__" in content:
                    rel = os.path.relpath(py_file, self._project_root)
                    self._result.dynamic_imports.append(rel)

                if "importlib.import_module" in content:
                    rel = os.path.relpath(py_file, self._project_root)
                    if rel not in self._result.dynamic_imports:
                        self._result.dynamic_imports.append(rel)

            except (SyntaxError, Exception):
                continue

        self._result.total_imports = len(all_imports)
        self._result.stdlib_imports = sum(
            1 for v in all_imports.values() if v == "stdlib"
        )
        self._result.third_party_imports = sum(
            1 for v in all_imports.values() if v == "third_party"
        )
        self._result.local_imports = sum(
            1 for v in all_imports.values() if v == "local"
        )

        self._result.hidden_imports = [
            imp for imp, cat in all_imports.items()
            if cat == "third_party"
        ]

    def _categorize_import(self, import_name: str, all_imports: Dict[str, str]) -> None:
        """Categorize an import as stdlib, third-party, or local."""
        if import_name in all_imports:
            return

        if import_name.startswith("src."):
            all_imports[import_name] = "local"
            return

        stdlib_modules = {
            "os", "sys", "json", "logging", "asyncio", "pathlib",
            "typing", "dataclasses", "datetime", "abc", "ast",
            "importlib", "inspect", "subprocess", "tempfile",
            "textwrap", "functools", "collections", "enum",
            "io", "re", "shutil", "threading", "time", "uuid",
            "warnings", "weakref", "types", "math", "random",
            "hashlib", "base64", "copy", "pprint", "traceback",
            "argparse", "configparser", "contextlib", "itertools",
            "operator", "pickle", "platform", "signal", "socket",
            "ssl", "stat", "string", "struct", "tarfile", "zipfile",
        }

        base = import_name.split(".")[0]
        if base in stdlib_modules:
            all_imports[import_name] = "stdlib"
        elif base.startswith("src"):
            all_imports[import_name] = "local"
        else:
            all_imports[import_name] = "third_party"

    def _check_pyinstaller(self) -> None:
        """Check PyInstaller availability and version."""
        try:
            import PyInstaller  # noqa: F401
            self._result.pyinstaller_available = True
            try:
                import PyInstaller.__main__  # noqa: F401
                self._result.pyinstaller_version = getattr(
                    PyInstaller, "__version__", "unknown"
                )
            except Exception:
                self._result.pyinstaller_version = "unknown"
        except ImportError:
            self._result.pyinstaller_available = False
            self._result.issues.append({
                "category": "pyinstaller",
                "severity": "critical",
                "message": "PyInstaller is not installed",
                "detail": "Install with: pip install pyinstaller",
            })

    def _check_build_artifacts(self) -> None:
        """Check for existing build artifacts."""
        spec_files = list(Path(self._project_root).glob("*.spec"))
        self._result.spec_file_exists = len(spec_files) > 0

        build_scripts = [
            "build_windows.ps1",
            "build_windows.bat",
            "build.sh",
            "Makefile",
        ]
        for script in build_scripts:
            if os.path.exists(os.path.join(self._project_root, script)):
                self._result.build_script_exists = True
                break

        if not self._result.spec_file_exists:
            self._result.warnings.append({
                "category": "build_artifacts",
                "severity": "warning",
                "message": "No PyInstaller .spec file found",
                "detail": "A .spec file is needed for reproducible builds",
            })

    def _estimate_bundle(self) -> None:
        """Estimate bundle size and identify files to include."""
        src_path = Path(self._src_dir)
        total_size = 0

        for py_file in src_path.rglob("*.py"):
            try:
                total_size += py_file.stat().st_size
            except OSError:
                pass

        self._result.bundle_size_estimate_mb = round(
            (total_size / (1024 * 1024)) * 3 + 10, 1
        )

        data_dirs = ["config", "data"]
        for d in data_dirs:
            d_path = os.path.join(self._project_root, d)
            if os.path.exists(d_path):
                self._result.data_files_to_include.append(d)

        if self._result.dynamic_imports:
            self._result.recommended_hidden_imports = [
                "src.agent.providers",
                "src.deployment.installers",
                "src.deployment.models",
                "src.deployment.profiles",
                "src.deployment.config",
                "src.deployment.repair",
                "src.deployment.verification",
                "src.deployment.integration",
                "src.deployment.execution",
                "src.agent.runtime",
                "src.agent.modes",
                "src.agent.execution",
                "src.agent.reasoning",
                "src.agent.conversation",
                "src.agent.execution.capabilities",
                "src.modules",
                "src.platform",
                "src.utils",
                "src.core",
                "src.health",
            ]

    def _calculate_score(self) -> None:
        """Calculate packaging readiness score."""
        score = 100.0

        if not self._result.entry_point_found:
            score -= 40
        elif not self._result.entry_point_valid:
            score -= 20

        if not self._result.pyinstaller_available:
            score -= 25

        if not self._result.spec_file_exists:
            score -= 10

        if not self._result.build_script_exists:
            score -= 10

        if len(self._result.dynamic_imports) > 0:
            score -= min(len(self._result.dynamic_imports) * 3, 15)

        self._result.score = max(0.0, min(100.0, score))
        self._result.valid = self._result.score >= 70

    def generate_pyinstaller_spec(self) -> str:
        """Generate a PyInstaller .spec file content."""
        ts = datetime.now(timezone.utc).isoformat()
        hidden = "\n".join(f'    "{imp}",' for imp in self._result.recommended_hidden_imports)

        return f'''# -*- mode: python ; coding: utf-8 -*-
"""
Corax Orchestrator - PyInstaller Build Specification.

Generated by PackagingValidator on {ts}
"""

import sys
import os
from pathlib import Path


block_cipher = None


# Collect all source directories as Tree objects
src_dir = os.path.join(os.path.dirname(__file__), "src")
config_dir = os.path.join(os.path.dirname(__file__), "config")
data_dir = os.path.join(os.path.dirname(__file__), "data")

# Hidden imports for dynamic module loading
hidden_imports = [
{hidden}
]

# Data files to include
datas = [
    ("config", "config"),
    ("data", "data"),
]

a = Analysis(
    ["src/main.py"],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=hidden_imports,
    hookspath=[],
    hooksconfig={{}},
    runtime_hooks=[],
    excludes=[
        "tkinter",
        "matplotlib",
        "PIL",
        "cv2",
        "notebook",
        "jupyter",
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="CoraxOrchestrator",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)
'''

    def generate_build_config(self) -> Dict[str, Any]:
        """Generate build configuration dictionary."""
        return {
            "app_name": "CoraxOrchestrator",
            "entry_point": "src/main.py",
            "dist_dir": "dist",
            "build_dir": "build",
            "one_file": False,
            "console": True,
            "hidden_imports": self._result.recommended_hidden_imports,
            "data_dirs": self._result.data_files_to_include,
            "excludes": [
                "tkinter",
                "matplotlib",
                "PIL",
                "cv2",
                "notebook",
                "jupyter",
            ],
            "upx": True,
            "icon": None,
            "version_file": None,
        }
