"""
Corax Orchestrator — Deployment Intelligence Module (Priority 1).

Provides intelligent deployment analysis:
- Deployment health scoring
- Installer reliability scoring
- Recovery frequency tracking
- Deployment bottleneck detection
- Install duration analytics
- Retry heatmaps
- Deployment failure statistics
- Environment risk indicators
- Operator recommendations
- Unstable installer detection
"""

from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
import json
import os
import statistics
import time

from src.core.logging import get_logger

logger = get_logger(__name__)


@dataclass
class DeploymentInsight:
    """A single actionable insight for operators."""
    category: str  # risk, performance, reliability, recommendation
    severity: str  # info, warning, critical
    message: str
    detail: str = ""
    metric_value: Optional[float] = None
    threshold: Optional[float] = None
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "category": self.category,
            "severity": self.severity,
            "message": self.message,
            "detail": self.detail,
            "metric_value": self.metric_value,
            "threshold": self.threshold,
            "timestamp": self.timestamp,
        }


@dataclass
class InstallerReliabilityScore:
    """Reliability score for a specific installer."""
    tool_key: str
    total_attempts: int
    success_count: int
    failure_count: int
    success_rate: float  # 0.0 to 1.0
    avg_duration_seconds: float
    stddev_duration_seconds: float
    recent_failures: int  # last 10 attempts
    is_unstable: bool
    recommendation: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "tool_key": self.tool_key,
            "total_attempts": self.total_attempts,
            "success_count": self.success_count,
            "failure_count": self.failure_count,
            "success_rate": round(self.success_rate, 3),
            "avg_duration_seconds": round(self.avg_duration_seconds, 1),
            "stddev_duration_seconds": round(self.stddev_duration_seconds, 1),
            "recent_failures": self.recent_failures,
            "is_unstable": self.is_unstable,
            "recommendation": self.recommendation,
        }


@dataclass
class DeploymentHealthScore:
    """Overall deployment health assessment."""
    score: float  # 0.0 to 1.0
    grade: str  # A, B, C, D, F
    component_scores: Dict[str, float]
    insights: List[DeploymentInsight]
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "score": round(self.score, 3),
            "grade": self.grade,
            "component_scores": {
                k: round(v, 3) for k, v in self.component_scores.items()
            },
            "insights": [i.to_dict() for i in self.insights],
            "timestamp": self.timestamp,
        }


class DeploymentIntelligence:
    """
    Provides intelligent deployment analysis and insights.

    Analyzes deployment history to produce health scores, reliability
    metrics, bottleneck detection, and actionable recommendations.
    All analysis is read-only — it never modifies deployment state.
    """

    def __init__(self):
        self._history: List[Dict[str, Any]] = []
        self._installer_stats: Dict[str, List[Dict[str, Any]]] = {}

    # ------------------------------------------------------------------
    # Deployment Health Scoring
    # ------------------------------------------------------------------

    def calculate_health_score(
        self,
        deployment_results: List[Dict[str, Any]],
        recovery_results: Optional[List[Dict[str, Any]]] = None,
        environment_risks: Optional[List[str]] = None,
    ) -> DeploymentHealthScore:
        """
        Calculate overall deployment health score (0.0 to 1.0).

        Factors:
        - Step success rate (40% weight)
        - Recovery effectiveness (25% weight)
        - Environment risk (20% weight)
        - Duration efficiency (15% weight)
        """
        insights: List[DeploymentInsight] = []
        component_scores: Dict[str, float] = {}

        # --- Step success rate (40%) ---
        if deployment_results:
            total = len(deployment_results)
            successful = sum(
                1 for r in deployment_results if r.get("success", False)
            )
            success_rate = successful / total if total > 0 else 0.0
        else:
            success_rate = 1.0

        component_scores["step_success_rate"] = success_rate

        if success_rate < 0.5:
            insights.append(DeploymentInsight(
                category="reliability",
                severity="critical",
                message="Deployment step success rate is critically low",
                detail=f"Only {successful}/{total} steps succeeded",
                metric_value=success_rate,
                threshold=0.5,
            ))
        elif success_rate < 0.8:
            insights.append(DeploymentInsight(
                category="reliability",
                severity="warning",
                message="Deployment step success rate is below target",
                detail=f"{successful}/{total} steps succeeded (target: 80%+)",
                metric_value=success_rate,
                threshold=0.8,
            ))

        # --- Recovery effectiveness (25%) ---
        if recovery_results:
            recovery_total = len(recovery_results)
            recovery_success = sum(
                1 for r in recovery_results if r.get("success", False)
            )
            recovery_rate = recovery_success / recovery_total if recovery_total > 0 else 0.0
        else:
            recovery_rate = 1.0

        component_scores["recovery_effectiveness"] = recovery_rate

        if recovery_rate < 0.3:
            insights.append(DeploymentInsight(
                category="reliability",
                severity="critical",
                message="Recovery mechanisms are failing",
                detail=f"Only {recovery_success}/{recovery_total} recoveries succeeded",
                metric_value=recovery_rate,
                threshold=0.3,
            ))

        # --- Environment risk (20%) ---
        env_risks = environment_risks or []
        risk_penalty = len(env_risks) * 0.1
        env_score = max(0.0, 1.0 - risk_penalty)
        component_scores["environment"] = env_score

        if env_risks:
            for risk in env_risks[:3]:
                insights.append(DeploymentInsight(
                    category="risk",
                    severity="warning",
                    message=f"Environment risk detected: {risk}",
                ))

        # --- Duration efficiency (15%) ---
        if deployment_results:
            durations = [
                r.get("duration_ms", 0) for r in deployment_results
                if r.get("duration_ms") is not None
            ]
            if durations:
                avg_duration = statistics.mean(durations)
                # Penalize very slow steps (>30s average)
                if avg_duration > 30000:
                    duration_score = max(0.0, 1.0 - (avg_duration - 30000) / 120000)
                else:
                    duration_score = 1.0
            else:
                duration_score = 1.0
        else:
            duration_score = 1.0

        component_scores["duration_efficiency"] = duration_score

        # --- Composite score ---
        weights = {
            "step_success_rate": 0.40,
            "recovery_effectiveness": 0.25,
            "environment": 0.20,
            "duration_efficiency": 0.15,
        }

        composite = sum(
            component_scores.get(component, 0.0) * weight
            for component, weight in weights.items()
        )
        composite = max(0.0, min(1.0, composite))

        # Grade assignment
        if composite >= 0.9:
            grade = "A"
        elif composite >= 0.8:
            grade = "B"
        elif composite >= 0.6:
            grade = "C"
        elif composite >= 0.4:
            grade = "D"
        else:
            grade = "F"

        return DeploymentHealthScore(
            score=composite,
            grade=grade,
            component_scores=component_scores,
            insights=insights,
        )

    # ------------------------------------------------------------------
    # Installer Reliability Scoring
    # ------------------------------------------------------------------

    def calculate_installer_reliability(
        self,
        tool_key: str,
        install_attempts: List[Dict[str, Any]],
    ) -> InstallerReliabilityScore:
        """
        Calculate reliability score for a specific installer.

        Analyzes success/failure history to detect unstable installers
        and provide recommendations.
        """
        if not install_attempts:
            return InstallerReliabilityScore(
                tool_key=tool_key,
                total_attempts=0,
                success_count=0,
                failure_count=0,
                success_rate=1.0,
                avg_duration_seconds=0.0,
                stddev_duration_seconds=0.0,
                recent_failures=0,
                is_unstable=False,
                recommendation="No installation history available",
            )

        total = len(install_attempts)
        successes = [a for a in install_attempts if a.get("success", False)]
        failures = [a for a in install_attempts if not a.get("success", False)]
        success_count = len(successes)
        failure_count = len(failures)
        success_rate = success_count / total if total > 0 else 0.0

        # Duration statistics
        durations = [
            a.get("duration_ms", 0) / 1000.0 for a in successes
            if a.get("duration_ms") is not None
        ]
        avg_duration = statistics.mean(durations) if durations else 0.0
        stddev_duration = statistics.stdev(durations) if len(durations) > 1 else 0.0

        # Recent failures (last 10 attempts)
        recent = install_attempts[-10:] if len(install_attempts) >= 10 else install_attempts
        recent_failures = sum(1 for a in recent if not a.get("success", False))

        # Unstable detection
        is_unstable = (
            failure_count >= 3
            and success_rate < 0.6
        ) or (
            recent_failures >= 4
        )

        # Recommendation
        if is_unstable:
            recommendation = (
                f"Installer '{tool_key}' is unstable "
                f"(success rate: {success_rate:.0%}). "
                "Consider checking network connectivity, disk space, "
                "and AV exclusions."
            )
        elif success_rate >= 0.9:
            recommendation = f"Installer '{tool_key}' is reliable."
        elif success_rate >= 0.7:
            recommendation = (
                f"Installer '{tool_key}' has moderate reliability "
                f"({success_rate:.0%}). Monitor for issues."
            )
        else:
            recommendation = (
                f"Installer '{tool_key}' has low reliability "
                f"({success_rate:.0%}). Investigate failures."
            )

        return InstallerReliabilityScore(
            tool_key=tool_key,
            total_attempts=total,
            success_count=success_count,
            failure_count=failure_count,
            success_rate=success_rate,
            avg_duration_seconds=avg_duration,
            stddev_duration_seconds=stddev_duration,
            recent_failures=recent_failures,
            is_unstable=is_unstable,
            recommendation=recommendation,
        )

    # ------------------------------------------------------------------
    # Deployment Bottleneck Detection
    # ------------------------------------------------------------------

    def detect_bottlenecks(
        self,
        step_timings: Dict[str, List[float]],
    ) -> List[Dict[str, Any]]:
        """
        Detect deployment bottlenecks from step timing data.

        Args:
            step_timings: Dict mapping step name to list of durations (ms)

        Returns:
            List of bottleneck findings sorted by severity
        """
        bottlenecks = []

        for step_name, timings in step_timings.items():
            if not timings:
                continue

            avg_time = statistics.mean(timings)
            max_time = max(timings)

            # Steps averaging > 30s are bottlenecks
            if avg_time > 30000:
                bottlenecks.append({
                    "step": step_name,
                    "type": "duration",
                    "severity": "high" if avg_time > 60000 else "medium",
                    "avg_duration_ms": round(avg_time, 1),
                    "max_duration_ms": round(max_time, 1),
                    "recommendation": (
                        f"Step '{step_name}' averages {avg_time/1000:.1f}s. "
                        "Consider parallelization or optimization."
                    ),
                })

            # High variance indicates instability
            if len(timings) > 1:
                stdev = statistics.stdev(timings)
                if stdev > avg_time * 0.5:  # CV > 50%
                    bottlenecks.append({
                        "step": step_name,
                        "type": "variance",
                        "severity": "medium",
                        "avg_duration_ms": round(avg_time, 1),
                        "stddev_duration_ms": round(stdev, 1),
                        "recommendation": (
                            f"Step '{step_name}' has high duration variance. "
                            "May be affected by external factors."
                        ),
                    })

        return sorted(
            bottlenecks,
            key=lambda b: {"high": 3, "medium": 2, "low": 1}.get(b["severity"], 0),
            reverse=True,
        )

    # ------------------------------------------------------------------
    # Retry Heatmap
    # ------------------------------------------------------------------

    def generate_retry_heatmap(
        self,
        retry_records: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """
        Generate a heatmap of retry activity for analysis.

        Args:
            retry_records: List of retry records with step_name, attempt,
                          success, duration_ms

        Returns:
            Heatmap data structured by step and attempt number
        """
        heatmap: Dict[str, Dict[int, int]] = {}
        step_totals: Dict[str, int] = {}
        step_failures: Dict[str, int] = {}

        for record in retry_records:
            step = record.get("step_name", "unknown")
            attempt = record.get("attempt", 1)
            success = record.get("success", False)

            if step not in heatmap:
                heatmap[step] = {}
                step_totals[step] = 0
                step_failures[step] = 0

            heatmap[step][attempt] = heatmap[step].get(attempt, 0) + 1
            step_totals[step] += 1
            if not success:
                step_failures[step] += 1

        # Calculate hot spots
        hotspots = []
        for step, attempts in heatmap.items():
            total = step_totals.get(step, 0)
            failures = step_failures.get(step, 0)

            # Steps requiring 3+ retries are hot spots
            high_retry_attempts = sum(
                count for attempt, count in attempts.items() if attempt >= 3
            )
            if high_retry_attempts > 0:
                hotspots.append({
                    "step": step,
                    "high_retry_count": high_retry_attempts,
                    "total_attempts": total,
                    "failure_count": failures,
                    "failure_rate": round(failures / total, 3) if total > 0 else 0,
                })

        return {
            "heatmap": {
                step: dict(attempts) for step, attempts in heatmap.items()
            },
            "hotspots": sorted(
                hotspots,
                key=lambda h: h["high_retry_count"],
                reverse=True,
            ),
            "total_records": len(retry_records),
        }

    # ------------------------------------------------------------------
    # Failure Statistics
    # ------------------------------------------------------------------

    def calculate_failure_statistics(
        self,
        failure_records: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """
        Calculate deployment failure statistics.

        Args:
            failure_records: List of failure records with category,
                            tool_key, and timestamp

        Returns:
            Failure statistics breakdown
        """
        if not failure_records:
            return {
                "total_failures": 0,
                "by_category": {},
                "by_tool": {},
                "most_common_category": None,
                "most_common_tool": None,
                "failure_rate_trend": [],
            }

        total = len(failure_records)

        # By category
        by_category: Dict[str, int] = {}
        for record in failure_records:
            cat = record.get("failure_category", "unknown")
            by_category[cat] = by_category.get(cat, 0) + 1

        # By tool
        by_tool: Dict[str, int] = {}
        for record in failure_records:
            tool = record.get("tool_key", "unknown")
            by_tool[tool] = by_tool.get(tool, 0) + 1

        # Most common
        most_common_cat = max(by_category, key=by_category.get) if by_category else None
        most_common_tool = max(by_tool, key=by_tool.get) if by_tool else None

        # Trend (failures per time window)
        sorted_records = sorted(
            failure_records,
            key=lambda r: r.get("timestamp", ""),
        )
        trend: List[Dict[str, Any]] = []
        if sorted_records:
            window_count = 0
            window_start = sorted_records[0].get("timestamp", "")
            for record in sorted_records:
                trend.append({
                    "timestamp": record.get("timestamp", ""),
                    "category": record.get("failure_category", "unknown"),
                    "tool": record.get("tool_key", "unknown"),
                })

        return {
            "total_failures": total,
            "by_category": dict(
                sorted(by_category.items(), key=lambda x: x[1], reverse=True)
            ),
            "by_tool": dict(
                sorted(by_tool.items(), key=lambda x: x[1], reverse=True)
            ),
            "most_common_category": most_common_cat,
            "most_common_tool": most_common_tool,
            "failure_timeline": trend[-50:],  # Last 50 failures
        }

    # ------------------------------------------------------------------
    # Environment Risk Indicators
    # ------------------------------------------------------------------

    def assess_environment_risk(
        self,
        hardening_results: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """
        Assess environment risk from hardening check results.

        Returns:
            Risk assessment with indicators and recommendations
        """
        risk_indicators: List[Dict[str, Any]] = []
        risk_score = 0.0
        total_checks = len(hardening_results)

        if total_checks == 0:
            return {
                "risk_score": 0.5,
                "risk_level": "unknown",
                "indicators": [{
                    "check": "none",
                    "risk": "unknown",
                    "message": "No environment hardening data available",
                }],
                "recommendations": ["Run environment hardening checks"],
            }

        failed_checks = 0
        for check in hardening_results:
            check_name = check.get("check_name", "unknown")
            passed = check.get("passed", False)
            errors = check.get("errors", [])
            warnings = check.get("warnings", [])
            recommendations = check.get("recommendations", [])

            if not passed:
                failed_checks += 1
                risk_indicators.append({
                    "check": check_name,
                    "risk": "high",
                    "message": f"Check '{check_name}' failed",
                    "details": errors[:3] if errors else warnings[:3],
                    "recommendations": recommendations[:2],
                })
            elif warnings:
                risk_indicators.append({
                    "check": check_name,
                    "risk": "low",
                    "message": f"Check '{check_name}' passed with warnings",
                    "details": warnings[:3],
                })

        # Calculate risk score
        if total_checks > 0:
            risk_score = failed_checks / total_checks

        risk_level = (
            "critical" if risk_score >= 0.5
            else "high" if risk_score >= 0.3
            else "medium" if risk_score >= 0.1
            else "low"
        )

        return {
            "risk_score": round(risk_score, 3),
            "risk_level": risk_level,
            "total_checks": total_checks,
            "failed_checks": failed_checks,
            "indicators": risk_indicators,
            "recommendations": self._generate_risk_recommendations(
                risk_indicators
            ),
        }

    def _generate_risk_recommendations(
        self,
        indicators: List[Dict[str, Any]],
    ) -> List[str]:
        """Generate recommendations based on risk indicators."""
        recs = []
        high_risk = [i for i in indicators if i.get("risk") == "high"]

        if len(high_risk) >= 3:
            recs.append(
                "Multiple high-risk environment issues detected. "
                "Resolve critical items before deployment."
            )
        elif len(high_risk) >= 1:
            recs.append(
                "Address high-risk environment issues for reliable deployment."
            )

        for indicator in high_risk:
            for r in indicator.get("recommendations", []):
                if r not in recs:
                    recs.append(r)

        return recs

    # ------------------------------------------------------------------
    # Operator Recommendations
    # ------------------------------------------------------------------

    def generate_recommendations(
        self,
        health_score: DeploymentHealthScore,
        installer_scores: List[InstallerReliabilityScore],
        bottlenecks: List[Dict[str, Any]],
        failure_stats: Dict[str, Any],
    ) -> List[DeploymentInsight]:
        """
        Generate comprehensive operator recommendations from all analyses.
        """
        recommendations: List[DeploymentInsight] = []

        # Health-based recommendations
        if health_score.grade in ("D", "F"):
            recommendations.append(DeploymentInsight(
                category="recommendation",
                severity="critical",
                message="Deployment health is critically low",
                detail="Review all failing steps and environment issues",
                metric_value=health_score.score,
                threshold=0.6,
            ))

        # Unstable installer recommendations
        for score in installer_scores:
            if score.is_unstable:
                recommendations.append(DeploymentInsight(
                    category="recommendation",
                    severity="warning",
                    message=f"Unstable installer: {score.tool_key}",
                    detail=score.recommendation,
                    metric_value=score.success_rate,
                    threshold=0.6,
                ))

        # Bottleneck recommendations
        for b in bottlenecks[:3]:
            recommendations.append(DeploymentInsight(
                category="recommendation",
                severity="warning" if b["severity"] == "high" else "info",
                message=f"Bottleneck detected: {b['step']}",
                detail=b["recommendation"],
            ))

        # Failure pattern recommendations
        most_common = failure_stats.get("most_common_category")
        if most_common and failure_stats.get("total_failures", 0) >= 3:
            recommendations.append(DeploymentInsight(
                category="recommendation",
                severity="info",
                message=f"Most common failure: {most_common}",
                detail=f"Found in {failure_stats['by_category'].get(most_common, 0)} failures",
            ))

        return recommendations

    # ------------------------------------------------------------------
    # Full Analysis Report
    # ------------------------------------------------------------------

    def generate_full_report(
        self,
        deployment_results: List[Dict[str, Any]],
        recovery_results: Optional[List[Dict[str, Any]]] = None,
        retry_records: Optional[List[Dict[str, Any]]] = None,
        failure_records: Optional[List[Dict[str, Any]]] = None,
        installer_histories: Optional[Dict[str, List[Dict[str, Any]]]] = None,
        hardening_results: Optional[List[Dict[str, Any]]] = None,
        step_timings: Optional[Dict[str, List[float]]] = None,
    ) -> Dict[str, Any]:
        """
        Generate a complete deployment intelligence report.

        Combines all analytics into a single structured report.
        """
        # Health score
        health = self.calculate_health_score(
            deployment_results=deployment_results,
            recovery_results=recovery_results,
            environment_risks=None,
        )

        # Installer reliability
        installer_scores: List[InstallerReliabilityScore] = []
        if installer_histories:
            for tool_key, history in installer_histories.items():
                score = self.calculate_installer_reliability(tool_key, history)
                installer_scores.append(score)

        # Bottlenecks
        bottlenecks = self.detect_bottlenecks(
            step_timings or {}
        )

        # Failure statistics
        failure_stats = self.calculate_failure_statistics(
            failure_records or []
        )

        # Environment risk
        env_risk = self.assess_environment_risk(
            hardening_results or []
        )

        # Retry heatmap
        retry_heatmap = self.generate_retry_heatmap(
            retry_records or []
        )

        # Recommendations
        recommendations = self.generate_recommendations(
            health_score=health,
            installer_scores=installer_scores,
            bottlenecks=bottlenecks,
            failure_stats=failure_stats,
        )

        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "health_score": health.to_dict(),
            "installer_reliability": [
                s.to_dict() for s in installer_scores
            ],
            "bottlenecks": bottlenecks,
            "failure_statistics": failure_stats,
            "environment_risk": env_risk,
            "retry_heatmap": retry_heatmap,
            "recommendations": [r.to_dict() for r in recommendations],
            "unstable_installers": [
                s.tool_key for s in installer_scores if s.is_unstable
            ],
        }
