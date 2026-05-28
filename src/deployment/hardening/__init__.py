"""
Corax Orchestrator — Secondary Hardening Node.

Provides deployment survivability hardening through:
- Advanced environment validation with GPU/WSL/Windows feature detection
- Installer failure classification and repair script generation
- AI stack lifecycle management with health monitoring
- Diagnostics and support bundle creation
- Deployment recovery with safe-mode fallback
- Operational visibility and progress tracking
- Deployment intelligence and health scoring (Priority 1)
- Smart recovery with bounded retries and escalation (Priority 2)
- AI stack validation and readiness scoring (Priority 3)
- Clean machine simulation for survivability testing (Priority 4)
- Deployment visibility dashboard (Priority 6)

This package is the "hardening" layer that wraps all deployment
operations with retry logic, failure analysis, health checks,
automated recovery procedures, and operational intelligence.
"""

from src.deployment.hardening.environment import (
    EnvironmentHardening,
    EnvironmentHardeningResult,
)

from src.deployment.hardening.failure_classifier import (
    InstallerFailureClassifier,
    FailureAnalysisResult,
    RepairScript,
)

from src.deployment.hardening.ai_resilience import (
    AIResilienceManager,
    AIResilienceResult,
    ServiceHealth,
)

from src.deployment.hardening.support_bundle import (
    SupportBundleExporter,
    SupportBundleResult,
)

from src.deployment.hardening.recovery import (
    DeploymentRecoveryManager,
    RecoveryStrategy,
    RecoveryResult,
)

from src.deployment.hardening.deployment_intelligence import (
    DeploymentIntelligence,
    DeploymentHealthScore,
    DeploymentInsight,
    InstallerReliabilityScore,
)

from src.deployment.hardening.smart_recovery import (
    SmartRecoveryEngine,
    RetryBudget,
    RecoveryDecision,
    RecoveryAction,
    EscalationLevel,
)

from src.deployment.hardening.ai_validation import (
    AIValidationEngine,
    AIValidationResult,
    AIReadinessScore,
)

from src.deployment.hardening.clean_machine import (
    CleanMachineSimulator,
    SimulationResult,
    SimulationReport,
)

from src.deployment.hardening.deployment_visibility import (
    DeploymentVisibilityDashboard,
    DeploymentSnapshot,
    PhaseProgress,
    HealthIndicator,
    RiskIndicator,
)

__all__ = [
    # Original modules
    "EnvironmentHardening",
    "EnvironmentHardeningResult",
    "InstallerFailureClassifier",
    "FailureAnalysisResult",
    "RepairScript",
    "AIResilienceManager",
    "AIResilienceResult",
    "ServiceHealth",
    "SupportBundleExporter",
    "SupportBundleResult",
    "DeploymentRecoveryManager",
    "RecoveryStrategy",
    "RecoveryResult",
    # Priority 1: Deployment Intelligence
    "DeploymentIntelligence",
    "DeploymentHealthScore",
    "DeploymentInsight",
    "InstallerReliabilityScore",
    # Priority 2: Smart Recovery
    "SmartRecoveryEngine",
    "RetryBudget",
    "RecoveryDecision",
    "RecoveryAction",
    "EscalationLevel",
    # Priority 3: AI Validation
    "AIValidationEngine",
    "AIValidationResult",
    "AIReadinessScore",
    # Priority 4: Clean Machine Simulation
    "CleanMachineSimulator",
    "SimulationResult",
    "SimulationReport",
    # Priority 6: Deployment Visibility
    "DeploymentVisibilityDashboard",
    "DeploymentSnapshot",
    "PhaseProgress",
    "HealthIndicator",
    "RiskIndicator",
]
