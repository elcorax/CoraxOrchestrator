"""
Corax Orchestrator — Validation Summary Generator (Auxiliary Validation Tool).

NON-CORE TOOLING. Does not modify runtime core, planner, event bus,
startup lifecycle, recovery architecture, or capability system.

Purpose:
- clean validation summaries
- validation summary generation
- repeated suite execution support

Usage:
    python validation/validation_summary_generator.py [--input DIR] [--output FILE]
"""

import sys
import os
import time
import json
import argparse
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional


_project_root = Path(__file__).parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
RESET = "\033[0m"
BOLD = "\033[1m"


class ValidationSummaryGenerator:
    """
    Generates clean, human-readable validation summaries from
    existing validation reports.

    Aggregates reports from:
    - alpha_validation_suite_report.json
    - alpha_smoke_suite_report.json
    - smoke_test_runner_report.json
    - restart_cycle_report.json
    - diagnostics_validation_report.json
    - executable_validation_report.json
    - package_validation_report.json
    - soak_test_report.json
    - stress_restart_report.json
    - runtime_validation_report.json
    - diagnostics_bundle_export_report.json
    - runtime_snapshot_export_report.json
    - alpha_validation_report.json
    - deployment_checklist_report.json

    Produces a unified summary in JSON and Markdown.
    """

    def __init__(self, input_dir: Optional[str] = None, output_file: Optional[str] = None):
        self._reports_dir = Path(input_dir) if input_dir else (
            _project_root / "data" / "reports"
        )
        self._output_file = Path(output_file) if output_file else (
            self._reports_dir / "validation_summary.json"
        )
        self._start_time = time.time()
        self._reports_loaded: Dict[str, Any] = {}
        self._summary: Dict[str, Any] = {}

    def run_all(self) -> Dict[str, Any]:
        """Load reports and generate summary."""
        print(f"\n{BOLD}{CYAN}Corax Orchestrator — Validation Summary Generator{RESET}")
        print(f"{'=' * 60}")
        print(f"Reports dir:  {self._reports_dir}")
        print(f"Output file:  {self._output_file}")
        print(f"Python:       {sys.version.split()[0]}")
        print(f"Platform:     {sys.platform}")
        print(f"{'=' * 60}\n")

        self._load_all_reports()
        self._generate_aggregated_summary()
        self._generate_human_summary()
        self._generate_markdown_summary()

        self._print_summary()
        return self._summary

    def _load_all_reports(self) -> None:
        """Load all validation reports from the reports directory."""
        self._reports_dir.mkdir(parents=True, exist_ok=True)

        report_files = list(self._reports_dir.glob("*.json"))
        print(f"  Found {len(report_files)} report files\n")

        for path in report_files:
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                self._reports_loaded[path.stem] = data
                print(f"    Loaded: {path.name}")
            except (json.JSONDecodeError, Exception) as e:
                print(f"    {YELLOW}Skipped{RESET}: {path.name} ({e})")

    def _generate_aggregated_summary(self) -> None:
        """Generate an aggregated validation summary."""
        aggregated = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "reports_loaded": len(self._reports_loaded),
            "tools": {},
            "categories": {
                "smoke_tests": {"passed": 0, "failed": 0, "total": 0},
                "restart_tests": {"passed": 0, "failed": 0, "total": 0},
                "diagnostics": {"passed": 0, "failed": 0, "total": 0},
                "executable": {"passed": 0, "failed": 0, "total": 0},
                "package": {"passed": 0, "failed": 0, "total": 0},
                "stress": {"passed": 0, "failed": 0, "total": 0},
                "export": {"passed": 0, "failed": 0, "total": 0},
            },
            "overall": {
                "total_reports": len(self._reports_loaded),
                "passed": 0,
                "failed": 0,
                "all_passed": True,
            },
        }

        # Extract pass/fail from each report
        for name, data in self._reports_loaded.items():
            report_info = self._extract_report_info(data)
            aggregated["tools"][name] = report_info

            if report_info["status"] == "passed":
                aggregated["overall"]["passed"] += 1
            else:
                aggregated["overall"]["failed"] += 1
                aggregated["overall"]["all_passed"] = False

            # Categorize
            category = self._categorize_report(name)
            if category and category in aggregated["categories"]:
                cat = aggregated["categories"][category]
                cat["total"] += 1
                if report_info["status"] == "passed":
                    cat["passed"] += 1
                else:
                    cat["failed"] += 1

        self._summary["aggregated"] = aggregated

    def _extract_report_info(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Extract pass/fail/status info from any report format."""
        info = {
            "status": "unknown",
            "passed": 0,
            "failed": 0,
            "total": 0,
            "success_rate": 0.0,
        }

        # Try common report structures
        for key, value in data.items() if isinstance(data, dict) else []:
            if isinstance(value, dict):
                if "passed" in value and "failed" in value:
                    info["passed"] = value.get("passed", 0)
                    info["failed"] = value.get("failed", 0)
                    info["total"] = value.get("total_checks") or value.get("total_tests") or value.get("total_items") or value.get("total_exports") or (info["passed"] + info["failed"])
                    info["success_rate"] = value.get("success_rate", 0.0)
                    info["status"] = "passed" if info["failed"] == 0 else "failed"
                    break

        return info

    def _categorize_report(self, name: str) -> Optional[str]:
        """Categorize a report by its name."""
        name_lower = name.lower()
        if "smoke" in name_lower:
            return "smoke_tests"
        elif "restart" in name_lower:
            return "restart_tests"
        elif "diagnostic" in name_lower:
            return "diagnostics"
        elif "executable" in name_lower:
            return "executable"
        elif "package" in name_lower or "deployment" in name_lower:
            return "package"
        elif "soak" in name_lower or "stress" in name_lower or "runtime_validation" in name_lower:
            return "stress"
        elif "bundle" in name_lower or "snapshot" in name_lower or "export" in name_lower:
            return "export"
        return None

    def _generate_human_summary(self) -> None:
        """Generate a human-readable summary."""
        agg = self._summary.get("aggregated", {})
        categories = agg.get("categories", {})

        human = {
            "summary": "Corax Orchestrator — Validation Summary",
            "generated": datetime.now(timezone.utc).isoformat(),
            "reports_analyzed": agg.get("reports_loaded", 0),
            "overall_status": "PASSED" if agg.get("overall", {}).get("all_passed") else "DEGRADED",
            "category_breakdown": {},
        }

        for cat_name, cat_data in categories.items():
            label = cat_name.replace("_", " ").title()
            if cat_data["total"] > 0:
                human["category_breakdown"][label] = {
                    "passed": cat_data["passed"],
                    "failed": cat_data["failed"],
                    "total": cat_data["total"],
                    "status": "PASSED" if cat_data["failed"] == 0 else "DEGRADED",
                }

        self._summary["human_summary"] = human

    def _generate_markdown_summary(self) -> None:
        """Generate a Markdown-formatted summary."""
        agg = self._summary.get("aggregated", {})
        human = self._summary.get("human_summary", {})

        lines = [
            "# Corax Orchestrator — Validation Summary",
            "",
            f"**Generated:** {human.get('generated', 'N/A')}",
            f"**Reports Analyzed:** {human.get('reports_analyzed', 0)}",
            f"**Overall Status:** {'✅ PASSED' if human.get('overall_status') == 'PASSED' else '❌ DEGRADED'}",
            "",
            "---",
            "",
            "## Category Breakdown",
            "",
            "| Category | Passed | Failed | Total | Status |",
            "|----------|--------|--------|-------|--------|",
        ]

        for cat_name, cat_data in human.get("category_breakdown", {}).items():
            status_icon = "✅" if cat_data["status"] == "PASSED" else "❌"
            lines.append(
                f"| {cat_name} | {cat_data['passed']} | {cat_data['failed']} | "
                f"{cat_data['total']} | {status_icon} |"
            )

        lines.extend([
            "",
            "---",
            "",
            "## Tool Results",
            "",
            "| Tool | Status | Passed | Failed | Success Rate |",
            "|------|--------|--------|--------|--------------|",
        ])

        for tool_name, tool_data in agg.get("tools", {}).items():
            status_icon = "✅" if tool_data["status"] == "passed" else "❌"
            lines.append(
                f"| {tool_name} | {status_icon} | {tool_data['passed']} | "
                f"{tool_data['failed']} | {tool_data['success_rate']}% |"
            )

        lines.extend([
            "",
            "---",
            "",
            f"*Report generated by Corax Orchestrator Validation Summary Generator*",
        ])

        summary_md = self._output_file.with_suffix(".md")
        summary_md.write_text("\n".join(lines), encoding="utf-8")
        self._summary["markdown_path"] = str(summary_md)

    def _print_summary(self) -> None:
        """Print the summary."""
        total_duration = (time.time() - self._start_time) * 1000
        human = self._summary.get("human_summary", {})

        print(f"\n{'=' * 60}")
        print(f"{BOLD}Validation Summary{RESET}")
        print(f"{'=' * 60}")
        print(f"  Reports analyzed: {human.get('reports_analyzed', 0)}")
        print(f"  Overall status:   ", end="")
        if human.get("overall_status") == "PASSED":
            print(f"{GREEN}{BOLD}PASSED{RESET}")
        else:
            print(f"{YELLOW}{BOLD}DEGRADED{RESET}")
        print(f"  Duration:         {total_duration:.0f}ms")
        print()

        for cat_name, cat_data in human.get("category_breakdown", {}).items():
            icon = "✅" if cat_data["status"] == "PASSED" else "❌"
            print(f"    {icon} {cat_name}: {cat_data['passed']}/{cat_data['total']} passed")

    def _generate_report(self) -> Dict[str, Any]:
        """Generate the complete summary report content."""
        return self._summary


def main() -> int:
    """Run the validation summary generator."""
    parser = argparse.ArgumentParser(
        description="Corax Orchestrator — Validation Summary Generator"
    )
    parser.add_argument(
        "--input", type=str, default=None,
        help="Directory containing validation reports"
    )
    parser.add_argument(
        "--output", type=str, default=None,
        help="Output file path for summary JSON"
    )
    args = parser.parse_args()

    generator = ValidationSummaryGenerator(
        input_dir=args.input,
        output_file=args.output,
    )
    summary = generator.run_all()

    # Save summary
    output_path = generator._output_file
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, default=str)

    print(f"\nSummary JSON saved to: {output_path}")
    md_path = summary.get("markdown_path")
    if md_path:
        print(f"Summary Markdown saved to: {md_path}")

    human = summary.get("human_summary", {})
    return 0 if human.get("overall_status") == "PASSED" else 1


if __name__ == "__main__":
    sys.exit(main())
