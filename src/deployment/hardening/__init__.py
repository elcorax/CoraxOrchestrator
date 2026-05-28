"""
Corax Orchestrator — Secondary Hardening Node.

Provides deployment survivability hardening through:
- Advanced environment validation with GPU/WSL/Windows feature detection
- Installer failure classification and repair script generation
- AI stack lifecycle management with health monitoring
- Diagnostics and support bundle creation
- Deployment recovery with safe-mode fallback
- Operational visibility and progress tracking

This package is the "hardening" layer that wraps all deployment
operations with retry logic, failure analysis, health checks,
and automated recovery procedures.
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

__all__ = [
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
]
