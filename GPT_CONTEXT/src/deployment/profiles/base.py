"""
Corax Orchestrator - Deployment Profile Base.

Defines deployment profiles that specify which tools and models
to install for different use cases.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Any, List, Optional


class DeploymentProfileType(Enum):
    """Types of deployment profiles."""
    MINIMAL_AI = "minimal_ai"
    CODING_WORKSTATION = "coding_workstation"
    FULL_AI_LAB = "full_ai_lab"
    AGENT_DEVELOPMENT = "agent_development"
    IMAGE_VIDEO_AI = "image_video_ai"
    FULL_DEV_WORKSTATION = "full_dev_workstation"
    AI_DEV_WORKSTATION = "ai_dev_workstation"
    CUSTOM = "custom"



@dataclass
class ProfileConfig:
    """
    Configuration for a deployment profile.

    Attributes:
        name: Display name
        description: Human-readable description
        tools: List of tool keys to install
        models: List of model IDs to pull
        install_configs: Per-tool installation configurations
        post_install_hooks: Scripts to run after installation
        requires_docker: Whether Docker is required
        requires_gpu: Whether GPU is recommended
        estimated_disk_gb: Estimated disk space needed
    """
    name: str
    description: str
    tools: List[str] = field(default_factory=list)
    models: List[str] = field(default_factory=list)
    install_configs: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    post_install_hooks: List[str] = field(default_factory=list)
    requires_docker: bool = False
    requires_gpu: bool = False
    estimated_disk_gb: int = 10


class DeploymentProfile:
    """
    A deployment profile defining what to install and configure.

    Profiles are the primary way users express deployment intent,
    mapping natural language requests to concrete installation plans.
    """

    # Built-in profile definitions
    PROFILES: Dict[DeploymentProfileType, ProfileConfig] = {
        DeploymentProfileType.MINIMAL_AI: ProfileConfig(
            name="Minimal AI Setup",
            description="Lightweight local AI setup with Ollama and basic models",
            tools=["ollama"],
            models=["llama3.2:3b", "nomic-embed-text"],
            install_configs={
                "ollama": {"keep_alive": "5m"},
            },
            estimated_disk_gb=5,
        ),
        DeploymentProfileType.CODING_WORKSTATION: ProfileConfig(
            name="Coding Workstation",
            description="Full AI coding setup with code models and IDE integration",
            tools=["ollama", "open_webui", "open_interpreter"],
            models=[
                "llama3.1:8b",
                "qwen2.5-coder:7b",
                "codegemma:2b",
                "nomic-embed-text",
            ],
            install_configs={
                "ollama": {"keep_alive": "30m"},
                "open_webui": {"ollama_url": "http://localhost:11434"},
                "open_interpreter": {
                    "model": "ollama/qwen2.5-coder:7b",
                    "auto_run": False,
                },
            },
            estimated_disk_gb=20,
        ),
        DeploymentProfileType.FULL_AI_LAB: ProfileConfig(
            name="Full AI Lab",
            description="Complete local AI environment with all tools and models",
            tools=["ollama", "lm_studio", "open_webui", "anythingllm", "open_interpreter"],
            models=[
                "llama3.1:8b",
                "qwen2.5-coder:7b",
                "mistral:7b",
                "codegemma:2b",
                "nomic-embed-text",
                "mxbai-embed-large",
            ],
            install_configs={
                "ollama": {"keep_alive": "1h"},
                "open_webui": {"ollama_url": "http://localhost:11434"},
                "anythingllm": {"llm_provider": "ollama", "ollama_endpoint": "http://localhost:11434"},
                "open_interpreter": {"model": "ollama/mistral:7b"},
            },
            estimated_disk_gb=40,
        ),
        DeploymentProfileType.AGENT_DEVELOPMENT: ProfileConfig(
            name="Agent Development Environment",
            description="Environment for building and testing AI agents",
            tools=["ollama", "open_webui", "open_interpreter"],
            models=[
                "llama3.1:8b",
                "qwen2.5-coder:7b",
                "deepseek-r1:7b",
                "codegemma:2b",
                "nomic-embed-text",
            ],
            install_configs={
                "ollama": {"keep_alive": "1h"},
                "open_webui": {"ollama_url": "http://localhost:11434"},
                "open_interpreter": {
                    "model": "ollama/qwen2.5-coder:7b",
                    "auto_run": False,
                    "verbose": True,
                },
            },
            estimated_disk_gb=25,
        ),
        DeploymentProfileType.IMAGE_VIDEO_AI: ProfileConfig(
            name="Image/Video AI Workstation",
            description="Image and video generation setup with ComfyUI",
            tools=["ollama", "comfyui"],
            models=[
                "llama3.2:3b",
                "nomic-embed-text",
            ],
            install_configs={
                "comfyui": {},
            },
            requires_gpu=True,
            estimated_disk_gb=30,
        ),
        DeploymentProfileType.FULL_DEV_WORKSTATION: ProfileConfig(
            name="Full Developer Workstation",
            description="Complete development environment with Git, Python, Node.js, VS Code, Docker, and Java",
            tools=[
                "git", "python", "nodejs", "vscode", "docker", "java",
            ],
            models=[],
            install_configs={
                "python": {"version": "3.12"},
                "nodejs": {"version": "22"},
                "docker": {"backend": "wsl-2"},
            },
            requires_docker=True,
            estimated_disk_gb=25,
        ),
        DeploymentProfileType.AI_DEV_WORKSTATION: ProfileConfig(
            name="AI Developer Workstation",
            description="Complete AI development environment with all developer tools and AI runtimes",
            tools=[
                "git", "python", "nodejs", "vscode", "windsurf",
                "docker", "java", "flutter",
                "ollama", "open_webui", "open_interpreter",
            ],
            models=[
                "llama3.1:8b",
                "qwen2.5-coder:7b",
                "deepseek-r1:7b",
                "codegemma:2b",
                "nomic-embed-text",
                "mxbai-embed-large",
            ],
            install_configs={
                "python": {"version": "3.12"},
                "nodejs": {"version": "22"},
                "ollama": {"keep_alive": "1h"},
                "open_webui": {"ollama_url": "http://localhost:11434"},
                "open_interpreter": {
                    "model": "ollama/qwen2.5-coder:7b",
                    "auto_run": False,
                },
                "docker": {"backend": "wsl-2"},
            },
            requires_docker=True,
            estimated_disk_gb=60,
        ),
    }


    def __init__(self, profile_type: DeploymentProfileType) -> None:
        self.type = profile_type
        self.config = self.PROFILES[profile_type]

    @classmethod
    def get_all(cls) -> List["DeploymentProfile"]:
        """Get all built-in profiles."""
        return [cls(pt) for pt in DeploymentProfileType if pt != DeploymentProfileType.CUSTOM]

    @classmethod
    def get_by_name(cls, name: str) -> Optional["DeploymentProfile"]:
        """Get a profile by its type name."""
        name = name.lower().replace(" ", "_")
        for pt in DeploymentProfileType:
            if pt.value == name:
                return cls(pt)
        return None

    @classmethod
    def match_intent(cls, query: str) -> Optional["DeploymentProfile"]:
        """
        Match a natural language query to a deployment profile.

        Args:
            query: Natural language request (e.g., "setup a full AI coding workstation")

        Returns:
            Best matching profile or None
        """
        query = query.lower()

        # Score each profile
        scores = {}
        for profile_type, config in cls.PROFILES.items():
            score = 0
            keywords = {
                "minimal_ai": ["minimal", "lightweight", "basic", "simple", "small"],
                "coding_workstation": ["coding", "code", "developer", "programming", "workstation"],
                "full_ai_lab": ["full", "complete", "lab", "everything", "all"],
                "agent_development": ["agent", "development", "build", "create"],
                "image_video_ai": ["image", "video", "generation", "stable diffusion", "comfyui"],
            }

            for keyword in keywords.get(profile_type.value, []):
                if keyword in query:
                    score += 1

            if score > 0:
                scores[profile_type] = score

        if not scores:
            return None

        best = max(scores, key=scores.get)
        return cls(best)

    def to_dict(self) -> Dict[str, Any]:
        """Export profile as dictionary."""
        return {
            "type": self.type.value,
            "name": self.config.name,
            "description": self.config.description,
            "tools": self.config.tools,
            "models": self.config.models,
            "install_configs": self.config.install_configs,
            "requires_docker": self.config.requires_docker,
            "requires_gpu": self.config.requires_gpu,
            "estimated_disk_gb": self.config.estimated_disk_gb,
        }
