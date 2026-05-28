"""
Corax Orchestrator — Deployment Visibility Module (Priority 6).

Provides operational visibility into deployment state:
- Deployment-state summaries
- Health indicators
- Runtime risk indicators
- Installer-state indicators
- Deployment ETA
- Throughput metrics
- Retry counters
- Recovery-state visibility

Requirements:
Operators must understand system state instantly.
"""

from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
import json
import os
import time

from src.core.logging import get_logger

logger = get_logger(__name__)


# ------------------------------------------------------------------
# Data Types
# ------------------------------------------------------------------

@dataclass
class PhaseProgress:
    """Progress information for a deployment phase."""
    phase_name: str
    status: str  # pending, running, completed, failed, skipped
    progress_pct: float = 0.0  # 0.0 to 100.0
    current_step: str = ""
    completed_steps: int = 0
    total_steps: int = 0
    failed_steps: int = 0
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    duration_seconds: Optional[float] = None
    eta_seconds: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "phase_name": self.phase_name,
            "status": self.status,
            "progress_pct": round(self.progress_pct, 1),
            "current_step": self.current_step,
            "completed_steps": self.completed_steps,
            "total_steps": self.total_steps,
            "failed_steps": self.failed_steps,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "duration_seconds": round(self.duration_seconds, 1) if self.duration_seconds else None,
            "eta_seconds": round(self.eta_seconds, 1) if self.eta_seconds else None,
        }


@dataclass
class HealthIndicator:
    """A health indicator for a deployment component."""
    component: str
    status: str  # healthy, degraded, unhealthy, unknown
    message: str = ""
    metric_value: Optional[float] = None
    threshold: Optional[float] = None
    last_updated: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "component": self.component,
            "status": self.status,
            "message": self.message,
            "metric_value": self.metric_value,
            "threshold": self.threshold,
            "last_updated": self.last_updated,
        }


@dataclass
class RiskIndicator:
    """A risk indicator for the deployment environment."""
    risk: str
    level: str  # low, medium, high, critical
    description: str = ""
    mitigation: str = ""
    active: bool = True
    detected_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "risk": self.risk,
            "level": self.level,
            "description": self.description,
            "mitigation": self.mitigation,
            "active": self.active,
            "detected_at": self.detected_at,
        }


@dataclass
class DeploymentSnapshot:
    """Complete snapshot of deployment state at a point in time."""
    deployment_id: str
    overall_status: str  # pending, running, completed, failed, degraded
    phases: List[PhaseProgress]
    health_indicators: List[HealthIndicator]
    risk_indicators: List[RiskIndicator]
    retry_count: int = 0
    recovery_active: bool = False
    safe_mode_active: bool = False
    start_time: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    elapsed_seconds: float = 0.0
    estimated_remaining_seconds: Optional[float] = None
    throughput: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "deployment_id": self.deployment_id,
            "overall_status": self.overall_status,
            "phases": [p.to_dict() for p in self.phases],
            "health_indicators": [h.to_dict() for h in self.health_indicators],
            "risk_indicators": [r.to_dict() for r in self.risk_indicators],
            "retry_count": self.retry_count,
            "recovery_active": self.recovery_active,
            "safe_mode_active": self.safe_mode_active,
            "start_time": self.start_time,
            "elapsed_seconds": round(self.elapsed_seconds, 1),
            "estimated_remaining_seconds": round(self.estimated_remaining_seconds, 1)
                if self.estimated_remaining_seconds else None,
            "throughput": self.throughput,
        }


# ------------------------------------------------------------------
# Deployment Visibility Dashboard
# ------------------------------------------------------------------

class DeploymentVisibilityDashboard:
    """
    Provides real-time visibility into deployment state.

    Generates structured snapshots that operators can use to
    understand system state instantly. All methods are read-only
    and never modify deployment state.
    """

    def __init__(self):
        self._snapshot_history: List[DeploymentSnapshot] = []
        self._phase_timings: Dict[str, List[float]] = {}
        self._step_timings: Dict[str, List[float]] = {}

    # ------------------------------------------------------------------
    # Phase Progress
    # ------------------------------------------------------------------

    def create_phase_progress(
        self,
        phase_name: str,
        status: str,
        completed_steps: int = 0,
        total_steps: int = 1,
        failed_steps: int = 0,
        current_step: str = "",
        started_at: Optional[str] = None,
    ) -> PhaseProgress:
        """
        Create a phase progress indicator.

        Args:
            phase_name: Name of the deployment phase
            status: pending, running, completed, failed, skipped
            completed_steps: Number of completed steps
            total_steps: Total steps in this phase
            failed_steps: Number of failed steps
            current_step: Currently executing step
            started_at: ISO timestamp when phase started
        """
        progress_pct = (
            (completed_steps / total_steps) * 100.0
            if total_steps > 0 else 0.0
        )

        duration_seconds = None
        eta_seconds = None

        if started_at:
            try:
                start_dt = datetime.fromisoformat(started_at)
                elapsed = (datetime.now(timezone.utc) - start_dt).total_seconds()
                duration_seconds = elapsed

                # Estimate remaining time
                if progress_pct > 0 and status == "running":
                    eta_seconds = (elapsed / progress_pct) * (100.0 - progress_pct)
            except (ValueError, TypeError):
                pass

        return PhaseProgress(
            phase_name=phase_name,
            status=status,
            progress_pct=min(progress_pct, 100.0),
            current_step=current_step,
            completed_steps=completed_steps,
            total_steps=total_steps,
            failed_steps=failed_steps,
            started_at=started_at,
            duration_seconds=duration_seconds,
            eta_seconds=eta_seconds,
        )

    # ------------------------------------------------------------------
    # Health Indicators
    # ------------------------------------------------------------------

    def create_health_indicator(
        self,
        component: str,
        status: str,
        message: str = "",
        metric_value: Optional[float] = None,
        threshold: Optional[float] = None,
    ) -> HealthIndicator:
        """
        Create a health indicator for a deployment component.

        Args:
            component: Component name (e.g., 'installer', 'network', 'disk')
            status: healthy, degraded, unhealthy, unknown
            message: Human-readable status message
            metric_value: Current metric value
            threshold: Threshold for healthy operation
        """
        return HealthIndicator(
            component=component,
            status=status,
            message=message or f"Component '{component}' is {status}",
            metric_value=metric_value,
            threshold=threshold,
        )

    # ------------------------------------------------------------------
    # Risk Indicators
    # ------------------------------------------------------------------

    def create_risk_indicator(
        self,
        risk: str,
        level: str,
        description: str = "",
        mitigation: str = "",
    ) -> RiskIndicator:
        """
        Create a risk indicator.

        Args:
            risk: Risk identifier
            level: low, medium, high, critical
            description: Description of the risk
            mitigation: How to mitigate
        """
        return RiskIndicator(
            risk=risk,
            level=level,
            description=description,
            mitigation=mitigation,
        )

    # ------------------------------------------------------------------
    # Throughput Metrics
    # ------------------------------------------------------------------

    def calculate_throughput(
        self,
        completed_items: int,
        elapsed_seconds: float,
        item_name: str = "steps",
    ) -> Dict[str, Any]:
        """
        Calculate throughput metrics.

        Args:
            completed_items: Number of completed items
            elapsed_seconds: Time elapsed in seconds
            item_name: Name of the items being counted

        Returns:
            Throughput metrics with rate, average, projections
        """
        if elapsed_seconds <= 0:
            return {
                "item_name": item_name,
                "rate_per_minute": 0.0,
                "average_time_per_item": 0.0,
                "projection": "Insufficient data",
            }

        rate_per_minute = (completed_items / elapsed_seconds) * 60.0
        avg_time_per_item = elapsed_seconds / completed_items if completed_items > 0 else 0.0

        return {
            "item_name": item_name,
            "completed": completed_items,
            "elapsed_seconds": round(elapsed_seconds, 1),
            "rate_per_minute": round(rate_per_minute, 2),
            "average_time_per_item": round(avg_time_per_item, 2),
            "projection": (
                f"{rate_per_minute:.1f} {item_name}/minute"
                if rate_per_minute > 0
                else "Not started"
            ),
        }

    # ------------------------------------------------------------------
    # ETA Calculation
    # ------------------------------------------------------------------

    def estimate_completion(
        self,
        total_steps: int,
        completed_steps: int,
        elapsed_seconds: float,
    ) -> Dict[str, Any]:
        """
        Estimate time to completion.

        Args:
            total_steps: Total number of steps
            completed_steps: Steps completed so far
            elapsed_seconds: Time elapsed

        Returns:
            ETA estimation with remaining time and completion time
        """
        remaining_steps = total_steps - completed_steps

        if completed_steps == 0 or elapsed_seconds <= 0:
            return {
                "total_steps": total_steps,
                "completed_steps": completed_steps,
                "remaining_steps": remaining_steps,
                "progress_pct": 0.0,
                "estimated_remaining_seconds": None,
                "estimated_completion_time": None,
                "note": "Not enough data to estimate completion",
            }

        progress_pct = (completed_steps / total_steps) * 100.0
        avg_time_per_step = elapsed_seconds / completed_steps
        estimated_remaining = remaining_steps * avg_time_per_step
        estimated_completion = datetime.now(timezone.utc) + timedelta(
            seconds=estimated_remaining
        )

        return {
            "total_steps": total_steps,
            "completed_steps": completed_steps,
            "remaining_steps": remaining_steps,
            "progress_pct": round(progress_pct, 1),
            "estimated_remaining_seconds": round(estimated_remaining, 1),
            "estimated_completion_time": estimated_completion.isoformat(),
            "note": (
                f"{progress_pct:.0f}% complete, "
                f"~{estimated_remaining:.0f}s remaining"
                if estimated_remaining > 0
                else "Complete"
            ),
        }

    # ------------------------------------------------------------------
    # Retry Counters
    # ------------------------------------------------------------------

    def create_retry_summary(
        self,
        retry_records: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """
        Create a summary of retry activity.

        Args:
            retry_records: List of retry records with step_name,
                          attempt, success, duration_ms
        """
        total_retries = len(retry_records)
        if total_retries == 0:
            return {
                "total_retries": 0,
                "active_retries": 0,
                "steps_with_retries": 0,
                "summary": "No retries recorded",
            }

        # Count per step
        per_step: Dict[str, Dict[str, int]] = {}
        for record in retry_records:
            step = record.get("step_name", "unknown")
            success = record.get("success", False)
            if step not in per_step:
                per_step[step] = {"total": 0, "success": 0, "failures": 0}
            per_step[step]["total"] += 1
            if success:
                per_step[step]["success"] += 1
            else:
                per_step[step]["failures"] += 1

        steps_with_retries = len(per_step)
        total_failures = sum(v["failures"] for v in per_step.values())

        return {
            "total_retries": total_retries,
            "active_retries": 0,  # All retries have completed
            "steps_with_retries": steps_with_retries,
            "per_step": per_step,
            "total_failures": total_failures,
            "summary": (
                f"{total_retries} retries across {steps_with_retries} steps, "
                f"{total_failures} unresolved failures"
            ),
        }

    # ------------------------------------------------------------------
    # Recovery State Visibility
    # ------------------------------------------------------------------

    def create_recovery_summary(
        self,
        recovery_active: bool,
        safe_mode_active: bool,
        recovery_history: List[Dict[str, Any]],
        retry_budget: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Create a summary of recovery state.

        Args:
            recovery_active: Whether recovery is currently active
            safe_mode_active: Whether safe mode is active
            recovery_history: List of recovery records
            retry_budget: Current retry budget state
        """
        total_recoveries = len(recovery_history)
        successful_recoveries = sum(
            1 for r in recovery_history
            if r.get("decision", {}).get("should_retry", False)
        )

        return {
            "recovery_active": recovery_active,
            "safe_mode": safe_mode_active,
            "total_recovery_attempts": total_recoveries,
            "successful_recoveries": successful_recoveries,
            "failed_recoveries": total_recoveries - successful_recoveries,
            "recovery_rate": (
                round(successful_recoveries / total_recoveries, 3)
                if total_recoveries > 0 else 0.0
            ),
            "retry_budget": retry_budget or {},
            "status_label": (
                "RECOVERY ACTIVE" if recovery_active
                else "SAFE MODE" if safe_mode_active
                else "NORMAL"
            ),
            "recent_actions": recovery_history[-5:] if recovery_history else [],
        }

    # ------------------------------------------------------------------
    # Full Snapshot
    # ------------------------------------------------------------------

    def create_snapshot(
        self,
        deployment_id: str,
        phases: List[PhaseProgress],
        health_indicators: Optional[List[HealthIndicator]] = None,
        risk_indicators: Optional[List[RiskIndicator]] = None,
        retry_count: int = 0,
        recovery_active: bool = False,
        safe_mode_active: bool = False,
        start_time: Optional[str] = None,
        throughput: Optional[Dict[str, Any]] = None,
    ) -> DeploymentSnapshot:
        """
        Create a complete deployment state snapshot.

        This is the main method for generating a visibility snapshot
        that operators can read instantly.
        """
        start = start_time or datetime.now(timezone.utc).isoformat()

        elapsed_seconds = 0.0
        try:
            start_dt = datetime.fromisoformat(start)
            elapsed_seconds = (
                datetime.now(timezone.utc) - start_dt
            ).total_seconds()
        except (ValueError, TypeError):
            pass

        # Determine overall status
        statuses = [p.status for p in phases]
        if all(s == "completed" for s in statuses):
            overall_status = "completed"
        elif any(s == "failed" for s in statuses):
            overall_status = "failed" if all(
                s == "failed" or s == "completed" for s in statuses
            ) else "degraded"
        elif any(s == "running" for s in statuses):
            overall_status = "running"
        elif all(s == "pending" for s in statuses):
            overall_status = "pending"
        elif any(s == "failed" for s in statuses):
            overall_status = "degraded"
        else:
            overall_status = "running"

        # Estimate remaining time
        total_steps = sum(p.total_steps for p in phases)
        completed_steps = sum(p.completed_steps for p in phases)
        eta = self.estimate_completion(
            total_steps=total_steps,
            completed_steps=completed_steps,
            elapsed_seconds=elapsed_seconds,
        )

        snapshot = DeploymentSnapshot(
            deployment_id=deployment_id,
            overall_status=overall_status,
            phases=phases,
            health_indicators=health_indicators or [],
            risk_indicators=risk_indicators or [],
            retry_count=retry_count,
            recovery_active=recovery_active,
            safe_mode_active=safe_mode_active,
            start_time=start,
            elapsed_seconds=elapsed_seconds,
            estimated_remaining_seconds=eta.get("estimated_remaining_seconds"),
            throughput=throughput,
        )

        self._snapshot_history.append(snapshot)
        return snapshot

    # ------------------------------------------------------------------
    # Snapshot History
    # ------------------------------------------------------------------

    def get_snapshot_history(
        self, max_snapshots: int = 10
    ) -> List[Dict[str, Any]]:
        """Get recent snapshot history."""
        return [
            s.to_dict() for s in self._snapshot_history[-max_snapshots:]
        ]

    def get_latest_snapshot(self) -> Optional[DeploymentSnapshot]:
        """Get the most recent snapshot."""
        return self._snapshot_history[-1] if self._snapshot_history else None

    # ------------------------------------------------------------------
    # Quick Status String
    # ------------------------------------------------------------------

    def get_status_string(
        self, snapshot: Optional[DeploymentSnapshot] = None
    ) -> str:
        """
        Generate a one-line status string for quick operator reference.

        Args:
            snapshot: Deployment snapshot, or None for latest

        Returns:
            Human-readable status string
        """
        snap = snapshot or self.get_latest_snapshot()
        if not snap:
            return "NO DEPLOYMENT DATA"

        parts = [
            f"[{snap.overall_status.upper()}]",
            f"ID: {snap.deployment_id}",
        ]

        # Safe mode indicator
        if snap.safe_mode_active:
            parts.append("[SAFE MODE]")

        # Recovery indicator
        if snap.recovery_active:
            parts.append("[RECOVERING]")

        # Progress
        total = sum(p.total_steps for p in snap.phases)
        completed = sum(p.completed_steps for p in snap.phases)
        parts.append(f"{completed}/{total} steps")

        # ETA
        if snap.estimated_remaining_seconds is not None:
            eta_min = int(snap.estimated_remaining_seconds / 60)
            eta_sec = int(snap.estimated_remaining_seconds % 60)
            parts.append(f"ETA: {eta_min}m{eta_sec}s")

        # Retries
        if snap.retry_count > 0:
            parts.append(f"Retries: {snap.retry_count}")

        # Health
        unhealthy = [
            h.component for h in snap.health_indicators
            if h.status in ("unhealthy", "degraded")
        ]
        if unhealthy:
            parts.append(f"Issues: {', '.join(unhealthy)}")

        return " | ".join(parts)

    def get_health_summary(
        self, snapshot: Optional[DeploymentSnapshot] = None
    ) -> Dict[str, Any]:
        """
        Get a summary of health indicators.

        Args:
            snapshot: Deployment snapshot, or None for latest
        """
        snap = snapshot or self.get_latest_snapshot()
        if not snap:
            return {"status": "unknown", "components": {}}

        components = {}
        for indicator in snap.health_indicators:
            components[indicator.component] = indicator.status

        statuses = list(components.values())
        if all(s == "healthy" for s in statuses):
            overall = "healthy"
        elif any(s == "unhealthy" for s in statuses):
            overall = "unhealthy"
        elif any(s == "degraded" for s in statuses):
            overall = "degraded"
        else:
            overall = "unknown"

        return {
            "status": overall,
            "components": components,
            "unhealthy_count": sum(1 for s in statuses if s == "unhealthy"),
            "degraded_count": sum(1 for s in statuses if s == "degraded"),
        }

    def get_risk_summary(
        self, snapshot: Optional[DeploymentSnapshot] = None
    ) -> Dict[str, Any]:
        """
        Get a summary of risk indicators.

        Args:
            snapshot: Deployment snapshot, or None for latest
        """
        snap = snapshot or self.get_latest_snapshot()
        if not snap:
            return {"level": "unknown", "risks": []}

        active_risks = [r for r in snap.risk_indicators if r.active]
        levels = [r.level for r in active_risks]

        if "critical" in levels:
            level = "critical"
        elif "high" in levels:
            level = "high"
        elif "medium" in levels:
            level = "medium"
        elif "low" in levels:
            level = "low"
        else:
            level = "none"

        return {
            "level": level,
            "active_risks": len(active_risks),
            "risks": [
                {
                    "risk": r.risk,
                    "level": r.level,
                    "description": r.description,
                }
                for r in active_risks
            ],
        }

    def get_progress_summary(
        self, snapshot: Optional[DeploymentSnapshot] = None
    ) -> Dict[str, Any]:
        """
        Get a summary of overall progress.

        Args:
            snapshot: Deployment snapshot, or None for latest
        """
        snap = snapshot or self.get_latest_snapshot()
        if not snap:
            return {"progress_pct": 0.0, "status": "unknown"}

        total_steps = sum(p.total_steps for p in snap.phases)
        completed_steps = sum(p.completed_steps for p in snap.phases)
        progress_pct = (
            (completed_steps / total_steps) * 100.0
            if total_steps > 0 else 0.0
        )

        return {
            "progress_pct": round(progress_pct, 1),
            "total_steps": total_steps,
            "completed_steps": completed_steps,
            "failed_steps": sum(p.failed_steps for p in snap.phases),
            "status": snap.overall_status,
            "elapsed_seconds": snap.elapsed_seconds,
            "estimated_remaining_seconds": snap.estimated_remaining_seconds,
        }
