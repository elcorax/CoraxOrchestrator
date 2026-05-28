"""
Corax Orchestrator - Local AI Infrastructure Deployment Layer.

This package provides real deployment capabilities for transforming
a clean computer into a complete AI development workstation.

Modules:
    installers - AI runtime installers (Ollama, LM Studio, Open WebUI, etc.)
    models - Model registry, recommendations, and download management
    profiles - Deployment presets (Minimal, Coding, Full AI Lab, etc.)
    verification - Health checks, endpoint testing, service verification
    integration - IDE integration (VS Code, Windsurf) and API configuration
    repair - Broken installation detection and automatic repair
    config - Deployment configuration management
"""

from src.deployment.orchestrator import DeploymentOrchestrator
from src.deployment.profiles.base import DeploymentProfile, DeploymentProfileType, ProfileConfig
from src.deployment.profiles.manager import ProfileManager
from src.deployment.verification.base import VerificationResult, VerificationStatus
from src.deployment.verification.health import HealthChecker
from src.deployment.integration.base import IntegrationConfig, IntegrationResult, IntegrationType
from src.deployment.integration.manager import IntegrationManager
from src.deployment.repair.base import RepairAction, RepairResult, RepairStatus
from src.deployment.repair.engine import RepairEngine
from src.deployment.config.base import DeploymentConfig, DeploymentSettings, DeploymentMode
from src.deployment.config.manager import DeploymentConfigManager
from src.deployment.models.registry import ModelRegistry
from src.deployment.models.recommender import ModelRecommender
from src.deployment.operations import OperationTracker, OperationType, OperationStatus, FailureCategory
from src.deployment.windows_utils import WindowsUtils
from src.deployment.macos_utils import MacOSUtils
from src.deployment.validation import EnvironmentValidator, ValidationResult, ValidationIssue
from src.deployment.preflight import EnvironmentPreflight, PreflightResult
from src.deployment.persistence import (
    save_repair_history,
    get_repair_history,
    save_deployment_checkpoint,
    load_latest_checkpoint,
    clear_checkpoints,
    save_operation_record,
    get_operation_history,
    list_persisted_sessions,
    cleanup_old_records,
)
from src.deployment.portable import (
    PortableDeployment,
    PortableConfig,
)
from src.deployment.unattended import UnattendedDeployment, UnattendedConfig, UnattendedResult
from src.deployment.autonomous import AutonomousDeploymentEngine, AutonomousModeState, autonomous_deployer
from src.deployment.ai_stack import AIStackDeployer, AIStackResult
from src.deployment.execution import (
    TerminalSession,
    TerminalResult,
    RetryQueue,
    RetryEntry,
    FailureAnalyzer,
    FailureAnalysis,
    DeploymentExecutor,
    DeploymentSession,
    DeploymentSessionResult,
    ToolDeploymentResult,
)

__all__ = [
    "DeploymentOrchestrator",
    "DeploymentProfile",
    "DeploymentProfileType",
    "ProfileConfig",
    "ProfileManager",
    "VerificationResult",
    "VerificationStatus",
    "HealthChecker",
    "IntegrationConfig",
    "IntegrationResult",
    "IntegrationType",
    "IntegrationManager",
    "RepairAction",
    "RepairResult",
    "RepairStatus",
    "RepairEngine",
    "DeploymentConfig",
    "DeploymentSettings",
    "DeploymentMode",
    "DeploymentConfigManager",
    "ModelRegistry",
    "ModelRecommender",
    "OperationTracker",
    "OperationType",
    "OperationStatus",
    "FailureCategory",
    "WindowsUtils",
    "MacOSUtils",
    "EnvironmentValidator",
    "ValidationResult",
    "ValidationIssue",
    "UnattendedDeployment",
    "UnattendedConfig",
    "UnattendedResult",
    "AutonomousDeploymentEngine",
    "AutonomousModeState",
    "autonomous_deployer",
    "AIStackDeployer",
    "AIStackResult",
    "TerminalSession",
    "TerminalResult",
    "RetryQueue",
    "RetryEntry",
    "FailureAnalyzer",
    "FailureAnalysis",
    "DeploymentExecutor",
    "DeploymentSession",
    "DeploymentSessionResult",
    "ToolDeploymentResult",
    "EnvironmentPreflight",
    "PreflightResult",
    "save_repair_history",
    "get_repair_history",
    "save_deployment_checkpoint",
    "load_latest_checkpoint",
    "clear_checkpoints",
    "save_operation_record",
    "get_operation_history",
    "list_persisted_sessions",
    "cleanup_old_records",
    "PortableDeployment",
    "PortableConfig",
]



