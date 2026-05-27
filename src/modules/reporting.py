"""
Corax Orchestrator - Reporting Engine Module.

Generates comprehensive deployment reports in multiple formats
including JSON, HTML, and Markdown. Tracks deployment history
and provides actionable insights.
"""

import json
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, List, Optional

from src.core.logging import get_logger
from src.modules.system_scanner import ScanResult
from src.modules.environment_analyzer import EnvironmentAnalysis
from src.modules.installer_engine import InstallerResult, InstallerStatus

logger = get_logger(__name__)


@dataclass
class DeploymentReport:
    """Complete deployment report."""
    report_id: str = ""
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    duration_seconds: float = 0.0
    system_info: Optional[Dict[str, Any]] = None
    environment_analysis: Optional[Dict[str, Any]] = None
    installation_results: Dict[str, Any] = field(default_factory=dict)
    errors: List[Dict[str, Any]] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    summary: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "report_id": self.report_id,
            "timestamp": self.timestamp,
            "duration_seconds": self.duration_seconds,
            "system_info": self.system_info,
            "environment_analysis": self.environment_analysis,
            "installation_results": self.installation_results,
            "errors": self.errors,
            "warnings": self.warnings,
            "summary": self.summary,
        }


class ReportingEngine:
    """
    Generates deployment reports in multiple formats.

    Supports JSON, HTML, and Markdown output formats. Tracks
    deployment history and provides summary statistics.
    """

    def __init__(self, output_dir: Optional[Path] = None) -> None:
        self.output_dir = output_dir or Path("data/reports")
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self._reports: List[DeploymentReport] = []

    def create_report(
        self,
        scan_result: Optional[ScanResult] = None,
        analysis: Optional[EnvironmentAnalysis] = None,
        install_results: Optional[Dict[str, InstallerResult]] = None,
        duration_seconds: float = 0.0,
    ) -> DeploymentReport:
        """
        Create a deployment report from scan, analysis, and installation results.

        Args:
            scan_result: Optional system scan result
            analysis: Optional environment analysis
            install_results: Optional installation results
            duration_seconds: Total deployment duration

        Returns:
            DeploymentReport with all available data
        """
        from uuid import uuid4

        report = DeploymentReport(
            report_id=str(uuid4()),
            duration_seconds=duration_seconds,
        )

        if scan_result:
            report.system_info = scan_result.to_dict()

        if analysis:
            report.environment_analysis = analysis.to_dict()
            report.warnings = analysis.warnings

        if install_results:
            report.installation_results = {
                name: result.to_dict()
                for name, result in install_results.items()
            }

            # Collect errors
            for name, result in install_results.items():
                if result.status == InstallerStatus.FAILED and result.error:
                    report.errors.append({
                        "tool": name,
                        "error": result.error,
                        "timestamp": result.timestamp,
                    })

        # Generate summary
        report.summary = self._generate_summary(report)

        self._reports.append(report)
        return report

    def _generate_summary(self, report: DeploymentReport) -> Dict[str, Any]:
        """Generate a summary of the deployment."""
        total = len(report.installation_results)
        successful = sum(
            1 for r in report.installation_results.values()
            if r.get("status") in (
                InstallerStatus.COMPLETED.value,
                InstallerStatus.ALREADY_INSTALLED.value,
            )
        )
        failed = sum(
            1 for r in report.installation_results.values()
            if r.get("status") == InstallerStatus.FAILED.value
        )
        skipped = sum(
            1 for r in report.installation_results.values()
            if r.get("status") == InstallerStatus.SKIPPED.value
        )

        return {
            "total_tools": total,
            "successful": successful,
            "failed": failed,
            "skipped": skipped,
            "errors_count": len(report.errors),
            "warnings_count": len(report.warnings),
            "duration_minutes": round(report.duration_seconds / 60, 2),
            "success_rate": round(
                (successful / total * 100) if total > 0 else 0, 1
            ),
        }

    def save_report(
        self, report: DeploymentReport, formats: Optional[List[str]] = None
    ) -> Dict[str, Path]:
        """
        Save a report to disk in specified formats.

        Args:
            report: The report to save
            formats: List of formats (default: ["json", "markdown"])

        Returns:
            Dictionary mapping format names to file paths
        """
        formats = formats or ["json", "markdown"]
        saved: Dict[str, Path] = {}

        for fmt in formats:
            if fmt == "json":
                path = self._save_json(report)
            elif fmt == "markdown":
                path = self._save_markdown(report)
            elif fmt == "html":
                path = self._save_html(report)
            else:
                logger.warning("Unsupported report format", format=fmt)
                continue

            saved[fmt] = path
            logger.info("Report saved", format=fmt, path=str(path))

        return saved

    def _save_json(self, report: DeploymentReport) -> Path:
        """Save report as JSON."""
        file_path = self.output_dir / f"report_{report.report_id[:8]}.json"
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(report.to_dict(), f, indent=2, default=str)
        return file_path

    def _save_markdown(self, report: DeploymentReport) -> Path:
        """Save report as Markdown."""
        file_path = self.output_dir / f"report_{report.report_id[:8]}.md"

        lines = [
            f"# Deployment Report: {report.report_id[:8]}",
            f"",
            f"**Timestamp:** {report.timestamp}",
            f"**Duration:** {report.summary.get('duration_minutes', 0)} minutes",
            f"**Success Rate:** {report.summary.get('success_rate', 0)}%",
            f"",
            "## Summary",
            f"",
            f"| Metric | Value |",
            f"|--------|-------|",
            f"| Total Tools | {report.summary.get('total_tools', 0)} |",
            f"| Successful | {report.summary.get('successful', 0)} |",
            f"| Failed | {report.summary.get('failed', 0)} |",
            f"| Skipped | {report.summary.get('skipped', 0)} |",
            f"| Errors | {report.summary.get('errors_count', 0)} |",
            f"| Warnings | {report.summary.get('warnings_count', 0)} |",
            f"",
        ]

        if report.errors:
            lines.extend([
                "## Errors",
                "",
            ])
            for error in report.errors:
                lines.append(f"- **{error.get('tool')}:** {error.get('error')}")
            lines.append("")

        if report.warnings:
            lines.extend([
                "## Warnings",
                "",
            ])
            for warning in report.warnings:
                lines.append(f"- {warning}")
            lines.append("")

        if report.installation_results:
            lines.extend([
                "## Installation Results",
                "",
                "| Tool | Status | Version | Error |",
                "|------|--------|---------|-------|",
            ])
            for name, result in report.installation_results.items():
                status = result.get("status", "unknown")
                version = result.get("version", "-")
                error = result.get("error", "-") or "-"
                lines.append(f"| {name} | {status} | {version} | {error} |")

        with open(file_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))

        return file_path

    def _save_html(self, report: DeploymentReport) -> Path:
        """Save report as HTML."""
        file_path = self.output_dir / f"report_{report.report_id[:8]}.html"

        summary = report.summary
        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Deployment Report - {report.report_id[:8]}</title>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 960px; margin: 0 auto; padding: 20px; background: #f5f5f5; }}
        .card {{ background: white; border-radius: 8px; padding: 20px; margin-bottom: 20px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }}
        h1 {{ color: #333; }}
        h2 {{ color: #555; border-bottom: 2px solid #eee; padding-bottom: 8px; }}
        .metric {{ display: inline-block; margin: 10px; padding: 15px; background: #f8f9fa; border-radius: 6px; text-align: center; min-width: 120px; }}
        .metric .value {{ font-size: 24px; font-weight: bold; color: #2196F3; }}
        .metric .label {{ font-size: 12px; color: #666; }}
        table {{ width: 100%; border-collapse: collapse; }}
        th, td {{ padding: 10px; text-align: left; border-bottom: 1px solid #eee; }}
        th {{ background: #f8f9fa; font-weight: 600; }}
        .status-completed {{ color: #4CAF50; }}
        .status-failed {{ color: #f44336; }}
        .status-skipped {{ color: #FF9800; }}
        .error {{ color: #f44336; background: #ffebee; padding: 10px; border-radius: 4px; margin: 5px 0; }}
        .warning {{ color: #FF9800; background: #fff3e0; padding: 10px; border-radius: 4px; margin: 5px 0; }}
    </style>
</head>
<body>
    <h1>Deployment Report</h1>
    <div class="card">
        <p><strong>Report ID:</strong> {report.report_id[:8]}</p>
        <p><strong>Timestamp:</strong> {report.timestamp}</p>
        <p><strong>Duration:</strong> {summary.get('duration_minutes', 0)} minutes</p>
        <p><strong>Success Rate:</strong> {summary.get('success_rate', 0)}%</p>
    </div>
    <div class="card">
        <h2>Summary</h2>
        <div class="metric"><div class="value">{summary.get('total_tools', 0)}</div><div class="label">Total Tools</div></div>
        <div class="metric"><div class="value" style="color:#4CAF50">{summary.get('successful', 0)}</div><div class="label">Successful</div></div>
        <div class="metric"><div class="value" style="color:#f44336">{summary.get('failed', 0)}</div><div class="label">Failed</div></div>
        <div class="metric"><div class="value" style="color:#FF9800">{summary.get('skipped', 0)}</div><div class="label">Skipped</div></div>
    </div>
"""

        if report.errors:
            html += '<div class="card"><h2>Errors</h2>'
            for error in report.errors:
                html += f'<div class="error"><strong>{error.get("tool")}:</strong> {error.get("error")}</div>'
            html += "</div>"

        if report.warnings:
            html += '<div class="card"><h2>Warnings</h2>'
            for warning in report.warnings:
                html += f'<div class="warning">{warning}</div>'
            html += "</div>"

        if report.installation_results:
            html += '<div class="card"><h2>Installation Results</h2><table><tr><th>Tool</th><th>Status</th><th>Version</th><th>Error</th></tr>'
            for name, result in report.installation_results.items():
                status = result.get("status", "unknown")
                status_class = f"status-{status}" if status in ("completed", "failed", "skipped") else ""
                html += f'<tr><td>{name}</td><td class="{status_class}">{status}</td><td>{result.get("version", "-")}</td><td>{result.get("error", "-") or "-"}</td></tr>'
            html += "</table></div>"

        html += "</body></html>"

        with open(file_path, "w", encoding="utf-8") as f:
            f.write(html)

        return file_path

    def list_reports(self) -> List[Dict[str, Any]]:
        """List all generated reports."""
        return [
            {
                "report_id": r.report_id,
                "timestamp": r.timestamp,
                "summary": r.summary,
            }
            for r in self._reports
        ]

    def get_last_report(self) -> Optional[DeploymentReport]:
        """Get the most recent report."""
        return self._reports[-1] if self._reports else None
