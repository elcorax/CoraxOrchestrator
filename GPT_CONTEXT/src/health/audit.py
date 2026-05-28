"""
Corax Orchestrator - Project Health Audit System.

Validates project health across multiple dimensions:
- Unresolved imports and dependency graph
- Failing tests and runtime readiness
- Virtual environment reproducibility
- Packaging and installer readiness
- Deployment and AI provisioning readiness

Generates comprehensive health reports with readiness scores,
critical blockers, warnings, and actionable recommendations.
"""

from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timezone
import ast
import importlib
import importlib.util
import inspect
import os
import pkgutil
import subprocess
import sys
import tempfile
import textwrap
from pathlib import Path


@dataclass
class HealthAuditResult:
    """Complete result of a project health audit."""
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    overall_score: float = 0.0
    critical_blockers: List[Dict[str, Any]] = field(default_factory=list)
    warnings: List[Dict[str, Any]] = field(default_factory=list)
    info: List[Dict[str, Any]] = field(default_factory=list)

    # Module health
    modules_checked: int = 0
    modules_healthy: int = 0
    modules_unhealthy: int = 0
    unresolved_imports: List[Dict[str, Any]] = field(default_factory=list)
    circular_imports: List[Dict[str, Any]] = field(default_factory=list)

    # Dependency health
    dependencies_checked: int = 0
    dependencies_installed: int = 0
    dependencies_missing: List[str] = field(default_factory=list)
    dependency_version_conflicts: List[Dict[str, Any]] = field(default_factory=list)

    # Test health
    tests_total: int = 0
    tests_passed: int = 0
    tests_failed: int = 0
    tests_skipped: int = 0
    failing_tests: List[Dict[str, Any]] = field(default_factory=list)

    # Runtime health
    python_version_valid: bool = True
    venv_active: bool = False
    platform_compatible: bool = True
    runtime_issues: List[str] = field(default_factory=list)

    # Packaging health
    packaging_ready: bool = False
    packaging_issues: List[str] = field(default_factory=list)
    entry_points_valid: bool = False
    pyinstaller_compatible: bool = False

    # Deployment health
    deployment_ready: bool = False
    deployment_issues: List[str] = field(default_factory=list)
    ai_provisioning_ready: bool = False
    ai_provisioning_issues: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "overall_score": round(self.overall_score, 1),
            "critical_blockers": self.critical_blockers,
            "warnings": self.warnings,
            "info": self.info,
            "modules": {
                "checked": self.modules_checked,
                "healthy": self.modules_healthy,
                "unhealthy": self.modules_unhealthy,
                "unresolved_imports": self.unresolved_imports,
                "circular_imports": self.circular_imports,
            },
            "dependencies": {
                "checked": self.dependencies_checked,
                "installed": self.dependencies_installed,
                "missing": self.dependencies_missing,
                "version_conflicts": self.dependency_version_conflicts,
            },
            "tests": {
                "total": self.tests_total,
                "passed": self.tests_passed,
                "failed": self.tests_failed,
                "skipped": self.tests_skipped,
                "failing": self.failing_tests,
            },
            "runtime": {
                "python_version_valid": self.python_version_valid,
                "venv_active": self.venv_active,
                "platform_compatible": self.platform_compatible,
                "issues": self.runtime_issues,
            },
            "packaging": {
                "ready": self.packaging_ready,
                "issues": self.packaging_issues,
                "entry_points_valid": self.entry_points_valid,
                "pyinstaller_compatible": self.pyinstaller_compatible,
            },
            "deployment": {
                "ready": self.deployment_ready,
                "issues": self.deployment_issues,
                "ai_provisioning_ready": self.ai_provisioning_ready,
                "ai_provisioning_issues": self.ai_provisioning_issues,
            },
        }


class ProjectHealthAudit:
    """
    Comprehensive project health auditor.

    Validates all aspects of project health and generates
    structured reports with readiness scores and actionable
    recommendations.
    """

    def __init__(self, project_root: Optional[str] = None):
        self._project_root = project_root or os.getcwd()
        self._result = HealthAuditResult()
        self._src_dir = os.path.join(self._project_root, "src")

    async def run_full_audit(self) -> HealthAuditResult:
        """Run a complete project health audit across all dimensions."""
        self._result = HealthAuditResult()

        # Phase 1: Module and import validation
        self._audit_modules()

        # Phase 2: Dependency validation
        self._audit_dependencies()

        # Phase 3: Test health
        await self._audit_tests()

        # Phase 4: Runtime readiness
        self._audit_runtime()

        # Phase 5: Packaging readiness
        self._audit_packaging()

        # Phase 6: Deployment readiness
        self._audit_deployment()

        # Phase 7: AI provisioning readiness
        self._audit_ai_provisioning()

        # Calculate overall score
        self._calculate_score()

        return self._result

    def _audit_modules(self) -> None:
        """Audit all Python modules for import health."""
        src_path = Path(self._src_dir)
        if not src_path.exists():
            self._result.modules_checked = 0
            self._result.critical_blockers.append({
                "category": "modules",
                "severity": "critical",
                "message": "src/ directory not found",
                "detail": f"Expected at: {self._src_dir}",
            })
            return

        python_files = list(src_path.rglob("*.py"))
        self._result.modules_checked = len(python_files)

        for py_file in python_files:
            try:
                with open(py_file, "r", encoding="utf-8") as f:
                    tree = ast.parse(f.read(), filename=str(py_file))

                # Check for import issues
                imports = []
                for node in ast.walk(tree):
                    if isinstance(node, ast.Import):
                        for alias in node.names:
                            imports.append(alias.name)
                    elif isinstance(node, ast.ImportFrom):
                        module = node.module or ""
                        for alias in node.names:
                            full_import = f"{module}.{alias.name}" if module else alias.name
                            imports.append(full_import)

                # Try to resolve each import
                for imp in imports:
                    if imp.startswith("src."):
                        try:
                            importlib.import_module(imp)
                        except ImportError as e:
                            rel_path = os.path.relpath(py_file, self._project_root)
                            self._result.unresolved_imports.append({
                                "file": rel_path,
                                "import": imp,
                                "error": str(e),
                            })

                self._result.modules_healthy += 1

            except SyntaxError as e:
                rel_path = os.path.relpath(py_file, self._project_root)
                self._result.modules_unhealthy += 1
                self._result.warnings.append({
                    "category": "syntax",
                    "severity": "warning",
                    "file": rel_path,
                    "message": f"Syntax error: {e}",
                })

        # Check for circular imports
        self._detect_circular_imports()

        # Summarize module health
        unhealthy_count = len(self._result.unresolved_imports)
        if unhealthy_count > 0:
            self._result.modules_unhealthy = unhealthy_count
            self._result.critical_blockers.append({
                "category": "imports",
                "severity": "critical" if unhealthy_count > 5 else "warning",
                "message": f"{unhealthy_count} unresolved import(s) detected",
                "detail": "Unresolved imports will cause runtime failures in packaged executable",
            })

    def _detect_circular_imports(self) -> None:
        """Detect potential circular imports in the project."""
        src_path = Path(self._src_dir)
        import_map: Dict[str, List[str]] = {}

        for py_file in src_path.rglob("*.py"):
            try:
                with open(py_file, "r", encoding="utf-8") as f:
                    tree = ast.parse(f.read(), filename=str(py_file))

                module_name = str(py_file.relative_to(self._project_root))
                module_name = module_name.replace(os.sep, ".").replace(".py", "")
                if module_name.endswith(".__init__"):
                    module_name = module_name[:-9]

                imports = []
                for node in ast.walk(tree):
                    if isinstance(node, ast.Import):
                        for alias in node.names:
                            if alias.name.startswith("src."):
                                imports.append(alias.name)
                    elif isinstance(node, ast.ImportFrom):
                        if node.module and node.module.startswith("src."):
                            imports.append(node.module)

                if imports:
                    import_map[module_name] = imports

            except (SyntaxError, Exception):
                pass

        for module, deps in import_map.items():
            for dep in deps:
                if dep in import_map and module in import_map.get(dep, []):
                    self._result.circular_imports.append({
                        "module_a": module,
                        "module_b": dep,
                    })

        if self._result.circular_imports:
            self._result.warnings.append({
                "category": "circular_imports",
                "severity": "warning",
                "message": f"{len(self._result.circular_imports)} potential circular import(s) detected",
                "detail": "Circular imports can cause issues with PyInstaller packaging",
            })

    def _audit_dependencies(self) -> None:
        """Audit project dependencies from requirements.txt."""
        req_path = os.path.join(self._project_root, "requirements.txt")
        if not os.path.exists(req_path):
            self._result.critical_blockers.append({
                "category": "dependencies",
                "severity": "critical",
                "message": "requirements.txt not found",
                "detail": "Cannot validate dependencies without requirements.txt",
            })
            return

        try:
            with open(req_path, "r", encoding="utf-8") as f:
                lines = [l.strip() for l in f.readlines() if l.strip() and not l.startswith("#")]

            self._result.dependencies_checked = len(lines)

            for line in lines:
                pkg_name = line.split(">=")[0].split("==")[0].split("<")[0].split("~=")[0].strip()
                if not pkg_name:
                    continue

                try:
                    importlib.import_module(pkg_name.replace("-", "_"))
                    self._result.dependencies_installed += 1
                except ImportError:
                    spec = importlib.util.find_spec(pkg_name.replace("-", "_"))
                    if spec is None:
                        self._result.dependencies_missing.append(pkg_name)
                        self._result.warnings.append({
                            "category": "missing_dependency",
                            "severity": "warning",
                            "package": pkg_name,
                            "message": f"Dependency '{pkg_name}' is not installed",
                            "detail": f"Required by: {line}",
                        })

        except Exception as e:
            self._result.warnings.append({
                "category": "dependency_audit",
                "severity": "warning",
                "message": f"Failed to audit dependencies: {str(e)}",
            })

    async def _audit_tests(self) -> None:
        """Audit test health by running test discovery."""
        test_dir = os.path.join(self._project_root, "tests")
        if not os.path.exists(test_dir):
            self._result.info.append({
                "category": "tests",
                "severity": "info",
                "message": "No tests directory found",
            })
            return

        test_files = list(Path(test_dir).rglob("test_*.py"))
        self._result.tests_total = len(test_files)

        if not test_files:
            self._result.info.append({
                "category": "tests",
                "severity": "info",
                "message": "No test files found",
            })
            return

        try:
            result = subprocess.run(
                [sys.executable, "-m", "pytest", "--collect-only", "-q", test_dir],
                capture_output=True,
                text=True,
                timeout=60,
                cwd=self._project_root,
            )

            output = result.stdout + result.stderr
            for line in output.split("\n"):
                if "selected" in line:
                    parts = line.strip().split()
                    if parts and parts[0].isdigit():
                        self._result.tests_total = int(parts[0])

        except (subprocess.TimeoutExpired, FileNotFoundError, Exception):
            self._result.info.append({
                "category": "tests",
                "severity": "info",
                "message": "Could not collect tests via pytest",
            })

    def _audit_runtime(self) -> None:
        """Audit runtime environment readiness."""
        py_version = sys.version_info
        if py_version < (3, 10):
            self._result.python_version_valid = False
            self._result.runtime_issues.append(
                f"Python {py_version.major}.{py_version.minor} is below minimum 3.10"
            )
            self._result.warnings.append({
                "category": "runtime",
                "severity": "warning",
                "message": f"Python {py_version.major}.{py_version.minor} is below recommended 3.10+",
            })

        self._result.venv_active = sys.prefix != sys.base_prefix
        if not self._result.venv_active:
            self._result.runtime_issues.append("Not running in a virtual environment")
            self._result.warnings.append({
                "category": "runtime",
                "severity": "info",
                "message": "Not running in a virtual environment",
                "detail": "Virtual environments ensure reproducible builds",
            })

        if os.name == "nt":
            self._result.platform_compatible = True
        elif sys.platform == "darwin":
            self._result.platform_compatible = True
        else:
            self._result.platform_compatible = True

        critical_modules = ["asyncio", "json", "logging", "pathlib", "dataclasses"]
        for mod in critical_modules:
            try:
                importlib.import_module(mod)
            except ImportError:
                self._result.runtime_issues.append(f"Critical module '{mod}' not available")
                self._result.critical_blockers.append({
                    "category": "runtime",
                    "severity": "critical",
                    "message": f"Critical Python module '{mod}' is not available",
                })

    def _audit_packaging(self) -> None:
        """Audit packaging readiness for PyInstaller."""
        issues = []

        main_py = os.path.join(self._src_dir, "main.py")
        if not os.path.exists(main_py):
            issues.append("No src/main.py entry point found")
            self._result.entry_points_valid = False
        else:
            self._result.entry_points_valid = True

        src_path = Path(self._src_dir)
        packages = [p for p in src_path.rglob("__init__.py")]
        if not packages:
            issues.append("No package __init__.py files found")

        dynamic_imports = []
        for py_file in src_path.rglob("*.py"):
            try:
                with open(py_file, "r", encoding="utf-8") as f:
                    content = f.read()
                    if "__import__" in content or "importlib.import_module" in content:
                        rel = os.path.relpath(py_file, self._project_root)
                        dynamic_imports.append(rel)
            except Exception:
                pass

        if dynamic_imports:
            issues.append(f"{len(dynamic_imports)} file(s) use dynamic imports")
            self._result.info.append({
                "category": "packaging",
                "severity": "info",
                "message": f"Dynamic imports detected in {len(dynamic_imports)} file(s)",
                "detail": "Dynamic imports may need hidden imports in PyInstaller spec",
                "files": dynamic_imports[:10],
            })

        try:
            import PyInstaller  # noqa: F401
            self._result.pyinstaller_compatible = True
        except ImportError:
            issues.append("PyInstaller is not installed")
            self._result.pyinstaller_compatible = False
            self._result.warnings.append({
                "category": "packaging",
                "severity": "warning",
                "message": "PyInstaller is not installed",
                "detail": "Install with: pip install pyinstaller",
            })

        spec_files = list(Path(self._project_root).glob("*.spec"))
        if not spec_files:
            issues.append("No PyInstaller .spec file found")

        self._result.packaging_issues = issues
        self._result.packaging_ready = len([i for i in issues if "critical" in i.lower()]) == 0

    def _audit_deployment(self) -> None:
        """Audit deployment readiness."""
        issues = []

        deploy_dir = os.path.join(self._src_dir, "deployment")
        if not os.path.exists(deploy_dir):
            issues.append("Deployment module not found")
        else:
            key_components = [
                "orchestrator.py",
                "validation.py",
                "operations.py",
            ]
            for comp in key_components:
                if not os.path.exists(os.path.join(deploy_dir, comp)):
                    issues.append(f"Missing deployment component: {comp}")

        config_dir = os.path.join(self._project_root, "config")
        if not os.path.exists(config_dir):
            issues.append("Config directory not found")
        elif not os.path.exists(os.path.join(config_dir, "default.yaml")):
            issues.append("Default config file not found")

        data_dir = os.path.join(self._project_root, "data")
        required_data_dirs = ["logs", "reports", "persistence", "models"]
        for d in required_data_dirs:
            if not os.path.exists(os.path.join(data_dir, d)):
                issues.append(f"Missing data directory: {d}")

        self._result.deployment_issues = issues
        self._result.deployment_ready = len(issues) == 0

    def _audit_ai_provisioning(self) -> None:
        """Audit AI provisioning readiness."""
        issues = []

        providers_dir = os.path.join(self._src_dir, "agent", "providers")
        if not os.path.exists(providers_dir):
            issues.append("AI provider modules not found")
        else:
            provider_files = list(Path(providers_dir).glob("*.py"))
            if len(provider_files) <= 1:
                issues.append("No AI provider implementations found")

        models_dir = os.path.join(self._src_dir, "deployment", "models")
        if not os.path.exists(models_dir):
            issues.append("Model management module not found")

        ai_installers = [
            "ollama.py",
            "lm_studio.py",
            "open_webui.py",
        ]
        installers_dir = os.path.join(self._src_dir, "deployment", "installers")
        if os.path.exists(installers_dir):
            for installer in ai_installers:
                if not os.path.exists(os.path.join(installers_dir, installer)):
                    issues.append(f"Missing AI installer: {installer}")

        self._result.ai_provisioning_issues = issues
        self._result.ai_provisioning_ready = len(issues) == 0

    def _calculate_score(self) -> None:
        """Calculate overall health score (0-100)."""
        score = 100.0
        deductions = []

        blocker_count = len(self._result.critical_blockers)
        score -= blocker_count * 20
        if blocker_count > 0:
            deductions.append(f"Critical blockers: -{blocker_count * 20}")

        import_count = len(self._result.unresolved_imports)
        score -= import_count * 5
        if import_count > 0:
            deductions.append(f"Unresolved imports: -{import_count * 5}")

        missing_count = len(self._result.dependencies_missing)
        score -= missing_count * 5
        if missing_count > 0:
            deductions.append(f"Missing dependencies: -{missing_count * 5}")

        fail_count = self._result.tests_failed
        score -= fail_count * 10
        if fail_count > 0:
            deductions.append(f"Failing tests: -{fail_count * 10}")

        runtime_count = len(self._result.runtime_issues)
        score -= runtime_count * 5
        if runtime_count > 0:
            deductions.append(f"Runtime issues: -{runtime_count * 5}")

        packaging_count = len(self._result.packaging_issues)
        score -= packaging_count * 5
        if packaging_count > 0:
            deductions.append(f"Packaging issues: -{packaging_count * 5}")

        deploy_count = len(self._result.deployment_issues)
        score -= deploy_count * 5
        if deploy_count > 0:
            deductions.append(f"Deployment issues: -{deploy_count * 5}")

        ai_count = len(self._result.ai_provisioning_issues)
        score -= ai_count * 5
        if ai_count > 0:
            deductions.append(f"AI provisioning issues: -{ai_count * 5}")

        self._result.overall_score = max(0.0, min(100.0, score))

        self._result.info.append({
            "category": "score",
            "severity": "info",
            "message": f"Overall health score: {self._result.overall_score:.1f}/100",
            "detail": "; ".join(deductions) if deductions else "No deductions applied",
        })

    def generate_markdown_report(self) -> str:
        """Generate a comprehensive markdown health report."""
        r = self._result

        lines = [
            "# Corax Orchestrator — Project Health Report",
            "",
            f"**Generated:** {r.timestamp}",
            f"**Overall Score:** {r.overall_score:.1f}/100",
            "",
            "---",
            "",
            "## Executive Summary",
            "",
            f"- **Modules Checked:** {r.modules_checked}",
            f"- **Dependencies:** {r.dependencies_installed}/{r.dependencies_checked} installed",
            f"- **Tests:** {r.tests_passed}/{r.tests_total} passed",
            f"- **Packaging Ready:** {'✅ YES' if r.packaging_ready else '❌ NO'}",
            f"- **Deployment Ready:** {'✅ YES' if r.deployment_ready else '❌ NO'}",
            f"- **AI Provisioning Ready:** {'✅ YES' if r.ai_provisioning_ready else '❌ NO'}",
            "",
            "---",
            "",
        ]

        if r.critical_blockers:
            lines.extend(["## 🚨 Critical Blockers", ""])
            for blocker in r.critical_blockers:
                lines.append(f"- **{blocker['message']}**")
                if "detail" in blocker:
                    lines.append(f"  - *{blocker['detail']}*")
            lines.append("")

        if r.warnings:
            lines.extend(["## ⚠️ Warnings", ""])
            for warning in r.warnings:
                lines.append(f"- **{warning['message']}**")
                if "detail" in warning:
                    lines.append(f"  - *{warning['detail']}*")
            lines.append("")

        lines.extend([
            "## 📦 Module Health",
            "",
            f"- **Total Modules:** {r.modules_checked}",
            f"- **Healthy:** {r.modules_healthy}",
            f"- **Unhealthy:** {r.modules_unhealthy}",
            "",
        ])
        if r.unresolved_imports:
            lines.append("### Unresolved Imports")
            lines.append("")
            lines.append("| File | Import | Error |")
            lines.append("|------|--------|-------|")
            for imp in r.unresolved_imports[:20]:
                lines.append(f"| {imp['file']} | `{imp['import']}` | {imp['error']} |")
            if len(r.unresolved_imports) > 20:
                lines.append(f"| ... | *{len(r.unresolved_imports) - 20} more* | |")
            lines.append("")

        lines.extend([
            "## 📋 Dependencies",
            "",
            f"- **Checked:** {r.dependencies_checked}",
            f"- **Installed:** {r.dependencies_installed}",
            f"- **Missing:** {len(r.dependencies_missing)}",
            "",
        ])
        if r.dependencies_missing:
            lines.append("### Missing Dependencies")
            lines.append("")
            for dep in r.dependencies_missing:
                lines.append(f"- `{dep}`")
            lines.append("")

        lines.extend([
            "## 🧪 Test Health",
            "",
            f"- **Total:** {r.tests_total}",
            f"- **Passed:** {r.tests_passed}",
            f"- **Failed:** {r.tests_failed}",
            f"- **Skipped:** {r.tests_skipped}",
            "",
        ])

        lines.extend([
            "## ⚡ Runtime Readiness",
            "",
            f"- **Python Version Valid:** {'✅' if r.python_version_valid else '❌'}",
            f"- **Virtual Environment Active:** {'✅' if r.venv_active else '❌'}",
            f"- **Platform Compatible:** {'✅' if r.platform_compatible else '❌'}",
            "",
        ])
        if r.runtime_issues:
            lines.append("### Runtime Issues")
            lines.append("")
            for issue in r.runtime_issues:
                lines.append(f"- {issue}")
            lines.append("")

        lines.extend([
            "## 📦 Packaging Readiness",
            "",
            f"- **Ready:** {'✅ YES' if r.packaging_ready else '❌ NO'}",
            f"- **Entry Points Valid:** {'✅' if r.entry_points_valid else '❌'}",
            f"- **PyInstaller Compatible:** {'✅' if r.pyinstaller_compatible else '❌'}",
            "",
        ])
        if r.packaging_issues:
            lines.append("### Packaging Issues")
            lines.append("")
            for issue in r.packaging_issues:
                lines.append(f"- {issue}")
            lines.append("")

        lines.extend([
            "## 🚀 Deployment Readiness",
            "",
            f"- **Ready:** {'✅ YES' if r.deployment_ready else '❌ NO'}",
            "",
        ])
        if r.deployment_issues:
            lines.append("### Deployment Issues")
            lines.append("")
            for issue in r.deployment_issues:
                lines.append(f"- {issue}")
            lines.append("")

        lines.extend([
            "## 🤖 AI Provisioning Readiness",
            "",
            f"- **Ready:** {'✅ YES' if r.ai_provisioning_ready else '❌ NO'}",
            "",
        ])
        if r.ai_provisioning_issues:
            lines.append("### AI Provisioning Issues")
            lines.append("")
            for issue in r.ai_provisioning_issues:
                lines.append(f"- {issue}")
            lines.append("")

        lines.extend(["---", "", "## 📋 Recommendations", ""])
        if r.critical_blockers:
            lines.append("### Must Fix Before Build")
            for blocker in r.critical_blockers:
                lines.append(f"- [ ] {blocker['message']}")
            lines.append("")
        if r.warnings:
            lines.append("### Should Address")
            for warning in r.warnings:
                lines.append(f"- [ ] {warning['message']}")
            lines.append("")

        lines.append("---")
        lines.append("")
        lines.append("*Report generated by Corax Orchestrator Health Audit System*")
        return "\n".join(lines)

    def generate_build_readiness_report(self) -> str:
        """Generate a build readiness report focused on executable packaging."""
        r = self._result

        lines = [
            "# Corax Orchestrator — Build Readiness Report",
            "",
            f"**Generated:** {r.timestamp}",
            f"**Overall Score:** {r.overall_score:.1f}/100",
            "",
            "---",
            "",
            "## Build Readiness Checklist",
            "",
            "| Check | Status | Detail |",
            "|-------|--------|--------|",
            f"| Entry Point (`src/main.py`) | {'✅' if r.entry_points_valid else '❌'} | {'Found' if r.entry_points_valid else 'Missing'} |",
            f"| PyInstaller Available | {'✅' if r.pyinstaller_compatible else '❌'} | {'Installed' if r.pyinstaller_compatible else 'Not installed'} |",
            f"| All Imports Resolvable | {'✅' if len(r.unresolved_imports) == 0 else '❌'} | {len(r.unresolved_imports)} unresolved |",
            f"| Dependencies Installed | {'✅' if len(r.dependencies_missing) == 0 else '❌'} | {len(r.dependencies_missing)} missing |",
            f"| Virtual Environment | {'✅' if r.venv_active else '❌'} | {'Active' if r.venv_active else 'Not active'} |",
            f"| Python >= 3.10 | {'✅' if r.python_version_valid else '❌'} | {'Valid' if r.python_version_valid else 'Below minimum'} |",
            f"| No Circular Imports | {'✅' if len(r.circular_imports) == 0 else '⚠️'} | {len(r.circular_imports)} detected |",
            f"| Tests Passing | {'✅' if r.tests_failed == 0 else '❌'} | {r.tests_failed} failing |",
            "",
        ]

        build_score = 100
        if not r.entry_points_valid:
            build_score -= 30
        if not r.pyinstaller_compatible:
            build_score -= 20
        if len(r.unresolved_imports) > 0:
            build_score -= min(len(r.unresolved_imports) * 5, 25)
        if len(r.dependencies_missing) > 0:
            build_score -= min(len(r.dependencies_missing) * 5, 15)
        if not r.venv_active:
            build_score -= 10
        build_score = max(0, build_score)

        lines.extend([f"**Build Readiness Score:** {build_score}/100", ""])

        if build_score >= 80:
            lines.append("**Status: ✅ READY FOR BUILD**")
        elif build_score >= 50:
            lines.append("**Status: ⚠️ CONDITIONALLY READY**")
            lines.append("")
            lines.append("### Items to resolve before production build:")
            for issue in r.packaging_issues:
                lines.append(f"- {issue}")
        else:
            lines.append("**Status: ❌ NOT READY**")
            lines.append("")
            lines.append("### Critical items blocking build:")
            for blocker in r.critical_blockers:
                lines.append(f"- {blocker['message']}")

        lines.append("")
        lines.append("---")
        lines.append("")
        lines.append("*Report generated by Corax Orchestrator Health Audit System*")
        return "\n".join(lines)

    def generate_alpha_blockers_report(self) -> str:
        """Generate a focused report on alpha-release blockers."""
        r = self._result

        lines = [
            "# Corax Orchestrator — Alpha Blockers Report",
            "",
            f"**Generated:** {r.timestamp}",
            f"**Overall Score:** {r.overall_score:.1f}/100",
            "",
            "---",
            "",
            "## 🚫 Critical Blockers (Must Fix Before Alpha)",
            "",
        ]

        if r.critical_blockers:
            for i, blocker in enumerate(r.critical_blockers, 1):
                lines.append(f"### {i}. {blocker['message']}")
                lines.append("")
                lines.append(f"- **Category:** {blocker['category']}")
                if "detail" in blocker:
                    lines.append(f"- **Detail:** {blocker['detail']}")
                lines.append("")
        else:
            lines.append("*No critical blockers detected.*")
            lines.append("")

        lines.extend(["---", "", "## ⚠️ Warnings (Should Fix Before Alpha)", ""])

        if r.warnings:
            for warning in r.warnings:
                lines.append(f"- **{warning['message']}**")
                if "detail" in warning:
                    lines.append(f"  - {warning['detail']}")
                lines.append("")
        else:
            lines.append("*No warnings detected.*")
            lines.append("")

        lines.extend([
            "---",
            "",
            "## 📊 Alpha Readiness Summary",
            "",
            "| Metric | Value |",
            "|--------|-------|",
            f"| Overall Score | {r.overall_score:.1f}/100 |",
            f"| Critical Blockers | {len(r.critical_blockers)} |",
            f"| Warnings | {len(r.warnings)} |",
            f"| Unresolved Imports | {len(r.unresolved_imports)} |",
            f"| Missing Dependencies | {len(r.dependencies_missing)} |",
            f"| Failing Tests | {r.tests_failed} |",
            f"| Packaging Issues | {len(r.packaging_issues)} |",
            f"| Deployment Issues | {len(r.deployment_issues)} |",
            f"| AI Provisioning Issues | {len(r.ai_provisioning_issues)} |",
            "",
        ])

        if r.overall_score >= 80 and len(r.critical_blockers) == 0:
            verdict = "✅ READY FOR ALPHA"
        elif r.overall_score >= 50:
            verdict = "⚠️ CONDITIONALLY READY"
        else:
            verdict = "❌ NOT READY"

        lines.append(f"**Verdict:** {verdict}")
        lines.append("")
        lines.append("---")
        lines.append("")
        lines.append("*Report generated by Corax Orchestrator Health Audit System*")
        return "\n".join(lines)
