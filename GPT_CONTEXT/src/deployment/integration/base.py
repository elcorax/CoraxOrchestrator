"""
Corax Orchestrator - Integration Base.

Defines integration configurations and results for
connecting AI tools together into a cohesive workflow.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Any, List, Optional
from datetime import datetime


class IntegrationType(Enum):
    """Types of tool integrations."""
    OLLAMA_WEBUI = "ollama_webui"  # Ollama -> Open WebUI
    OLLAMA_INTERPRETER = "ollama_interpreter"  # Ollama -> Open Interpreter
    OLLAMA_ANYTHINGLLM = "ollama_anythingllm"  # Ollama -> AnythingLLM
    LMSTUDIO_WEBUI = "lmstudio_webui"  # LM Studio -> Open WebUI
    LMSTUDIO_INTERPRETER = "lmstudio_interpreter"  # LM Studio -> Open Interpreter
    OLLAMA_COMFYUI = "ollama_comfyui"  # Ollama -> ComfyUI (for prompt gen)
    CUSTOM = "custom"


@dataclass
class IntegrationConfig:
    """
    Configuration for connecting two AI tools.

    Attributes:
        integration_type: Type of integration
        source_tool: Source tool key
        target_tool: Target tool key
        source_config: Configuration for the source connection
        target_config: Configuration for the target connection
        description: Human-readable description
    """
    integration_type: IntegrationType
    source_tool: str
    target_tool: str
    source_config: Dict[str, Any] = field(default_factory=dict)
    target_config: Dict[str, Any] = field(default_factory=dict)
    description: str = ""


@dataclass
class IntegrationResult:
    """
    Result of an integration attempt.

    Attributes:
        integration_type: Type of integration
        success: Whether integration succeeded
        message: Human-readable result
        details: Additional integration details
        timestamp: When integration was performed
    """
    integration_type: IntegrationType
    success: bool
    message: str = ""
    details: Dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "integration_type": self.integration_type.value,
            "success": self.success,
            "message": self.message,
            "details": self.details,
            "timestamp": self.timestamp.isoformat(),
        }
