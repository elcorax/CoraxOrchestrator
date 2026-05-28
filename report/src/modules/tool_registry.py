"""
Corax Orchestrator - Tool Registry Module.

Maintains a registry of all supported tools, their metadata,
installation requirements, and dependency relationships.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Any, List, Optional, Set, Type

from src.core.logging import get_logger
from src.core.exceptions import ConfigurationError

logger = get_logger(__name__)


class ToolCategory(Enum):
    """Categories of supported tools."""
    AI_PLATFORM = "ai_platform"
    AI_TOOL = "ai_tool"
    IDE = "ide"
    RUNTIME = "runtime"
    CONTAINER = "container"
    VERSION_CONTROL = "version_control"
    PACKAGE_MANAGER = "package_manager"
    UTILITY = "utility"


@dataclass
class ToolDependency:
    """A dependency relationship between tools."""
    name: str
    required: bool = True
    min_version: Optional[str] = None


@dataclass
class ToolMetadata:
    """Metadata for a registered tool."""
    name: str
    display_name: str
    description: str
    category: ToolCategory
    version: str = "0.0.0"
    homepage: str = ""
    download_url: str = ""
    install_instructions: str = ""
    dependencies: List[ToolDependency] = field(default_factory=list)
    supported_platforms: List[str] = field(default_factory=lambda: ["windows", "macos", "linux"])
    min_ram_gb: int = 0
    min_disk_gb: int = 0
    requires_admin: bool = False
    checksum: Optional[str] = None
    tags: List[str] = field(default_factory=list)
    installer_class: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "display_name": self.display_name,
            "description": self.description,
            "category": self.category.value,
            "version": self.version,
            "homepage": self.homepage,
            "download_url": self.download_url,
            "dependencies": [
                {"name": d.name, "required": d.required, "min_version": d.min_version}
                for d in self.dependencies
            ],
            "supported_platforms": self.supported_platforms,
            "min_ram_gb": self.min_ram_gb,
            "min_disk_gb": self.min_disk_gb,
            "requires_admin": self.requires_admin,
            "tags": self.tags,
        }


# Built-in tool definitions
BUILTIN_TOOLS: Dict[str, ToolMetadata] = {
    "lm_studio": ToolMetadata(
        name="lm_studio",
        display_name="LM Studio",
        description="Local AI model runner with GUI for downloading and running LLMs",
        category=ToolCategory.AI_PLATFORM,
        homepage="https://lmstudio.ai",
        download_url="https://releases.lmstudio.ai/",
        min_ram_gb=8,
        min_disk_gb=10,
        supported_platforms=["windows", "macos"],
        tags=["llm", "inference", "gui"],
    ),
    "ollama": ToolMetadata(
        name="ollama",
        display_name="Ollama",
        description="Local LLM runner with CLI and API for managing AI models",
        category=ToolCategory.AI_PLATFORM,
        homepage="https://ollama.ai",
        download_url="https://ollama.ai/download",
        min_ram_gb=8,
        min_disk_gb=5,
        tags=["llm", "inference", "cli", "api"],
    ),
    "open_webui": ToolMetadata(
        name="open_webui",
        display_name="Open WebUI",
        description="Self-hosted WebUI for LLMs, compatible with Ollama",
        category=ToolCategory.AI_TOOL,
        homepage="https://openwebui.com",
        download_url="https://github.com/open-webui/open-webui",
        dependencies=[
            ToolDependency(name="ollama", required=False),
            ToolDependency(name="docker", required=False),
        ],
        min_ram_gb=4,
        min_disk_gb=2,
        tags=["webui", "chat", "interface"],
    ),
    "anything_llm": ToolMetadata(
        name="anything_llm",
        display_name="AnythingLLM",
        description="All-in-one AI desktop app with RAG capabilities",
        category=ToolCategory.AI_TOOL,
        homepage="https://anythingllm.com",
        download_url="https://anythingllm.com/download",
        min_ram_gb=8,
        min_disk_gb=5,
        tags=["rag", "desktop", "documents"],
    ),
    "open_interpreter": ToolMetadata(
        name="open_interpreter",
        display_name="Open Interpreter",
        description="Natural language interface for computer control using LLMs",
        category=ToolCategory.AI_TOOL,
        homepage="https://openinterpreter.com",
        download_url="https://github.com/open-interpreter/open-interpreter",
        dependencies=[
            ToolDependency(name="python", required=True, min_version="3.10.0"),
        ],
        min_ram_gb=4,
        min_disk_gb=1,
        tags=["automation", "cli", "agent"],
    ),
    "comfy_ui": ToolMetadata(
        name="comfy_ui",
        display_name="ComfyUI",
        description="Powerful and modular stable diffusion GUI with workflow editor",
        category=ToolCategory.AI_TOOL,
        homepage="https://github.com/comfyanonymous/ComfyUI",
        download_url="https://github.com/comfyanonymous/ComfyUI",
        dependencies=[
            ToolDependency(name="python", required=True, min_version="3.10.0"),
            ToolDependency(name="git", required=True),
        ],
        min_ram_gb=8,
        min_disk_gb=10,
        tags=["stable-diffusion", "image-generation", "workflow"],
    ),
    "vs_code": ToolMetadata(
        name="vs_code",
        display_name="Visual Studio Code",
        description="Lightweight but powerful source code editor",
        category=ToolCategory.IDE,
        homepage="https://code.visualstudio.com",
        download_url="https://code.visualstudio.com/download",
        min_ram_gb=2,
        min_disk_gb=1,
        tags=["editor", "development"],
    ),
    "windsurf": ToolMetadata(
        name="windsurf",
        display_name="Windsurf",
        description="AI-powered IDE with agentic development capabilities",
        category=ToolCategory.IDE,
        homepage="https://codeium.com/windsurf",
        download_url="https://codeium.com/windsurf/download",
        min_ram_gb=4,
        min_disk_gb=2,
        tags=["editor", "ai", "development"],
    ),
    "docker": ToolMetadata(
        name="docker",
        display_name="Docker",
        description="Container platform for developing, shipping, and running applications",
        category=ToolCategory.CONTAINER,
        homepage="https://docker.com",
        download_url="https://docker.com/products/docker-desktop",
        requires_admin=True,
        min_ram_gb=4,
        min_disk_gb=10,
        tags=["container", "devops", "deployment"],
    ),
    "git": ToolMetadata(
        name="git",
        display_name="Git",
        description="Distributed version control system",
        category=ToolCategory.VERSION_CONTROL,
        homepage="https://git-scm.com",
        download_url="https://git-scm.com/downloads",
        min_disk_gb=0.5,
        tags=["vcs", "version-control"],
    ),
    "python": ToolMetadata(
        name="python",
        display_name="Python",
        description="High-level programming language for AI/ML development",
        category=ToolCategory.RUNTIME,
        homepage="https://python.org",
        download_url="https://python.org/downloads",
        min_disk_gb=1,
        tags=["language", "runtime", "ai"],
    ),
    "nodejs": ToolMetadata(
        name="nodejs",
        display_name="Node.js",
        description="JavaScript runtime for building web applications",
        category=ToolCategory.RUNTIME,
        homepage="https://nodejs.org",
        download_url="https://nodejs.org/download",
        min_disk_gb=1,
        tags=["language", "runtime", "web"],
    ),
}


class ToolRegistry:
    """
    Registry of all supported tools and their metadata.

    Provides lookup, dependency resolution, and filtering capabilities
    for the installer engine and other modules.
    """

    def __init__(self) -> None:
        self._tools: Dict[str, ToolMetadata] = {}
        self._load_builtins()

    def _load_builtins(self) -> None:
        """Load built-in tool definitions."""
        for name, metadata in BUILTIN_TOOLS.items():
            self.register(metadata)
        logger.info(f"Loaded {len(BUILTIN_TOOLS)} built-in tools")

    def register(self, metadata: ToolMetadata) -> None:
        """
        Register a tool in the registry.

        Args:
            metadata: ToolMetadata for the tool to register
        """
        self._tools[metadata.name] = metadata
        logger.debug(f"Registered tool: {metadata.name}")

    def get(self, name: str) -> Optional[ToolMetadata]:
        """
        Get tool metadata by name.

        Args:
            name: Tool name identifier

        Returns:
            ToolMetadata if found, None otherwise
        """
        return self._tools.get(name)

    def get_all(self) -> Dict[str, ToolMetadata]:
        """Get all registered tools."""
        return dict(self._tools)

    def get_by_category(self, category: ToolCategory) -> List[ToolMetadata]:
        """
        Get all tools in a category.

        Args:
            category: ToolCategory to filter by

        Returns:
            List of ToolMetadata in the category
        """
        return [
            tool for tool in self._tools.values()
            if tool.category == category
        ]

    def get_dependencies(
        self, tool_name: str, recursive: bool = True
    ) -> List[ToolDependency]:
        """
        Get dependencies for a tool.

        Args:
            tool_name: Name of the tool
            recursive: Whether to resolve transitive dependencies

        Returns:
            List of ToolDependency objects
        """
        tool = self.get(tool_name)
        if not tool:
            return []

        deps = list(tool.dependencies)

        if recursive:
            resolved: Set[str] = {tool_name}
            queue = [d.name for d in deps if d.name not in resolved]

            while queue:
                current = queue.pop(0)
                if current in resolved:
                    continue
                resolved.add(current)

                current_tool = self.get(current)
                if current_tool:
                    for dep in current_tool.dependencies:
                        if dep.name not in resolved:
                            deps.append(dep)
                            queue.append(dep.name)

        return deps

    def get_install_order(self, tool_names: List[str]) -> List[str]:
        """
        Get the correct installation order for a list of tools
        based on their dependency graph (topological sort).

        Args:
            tool_names: List of tool names to install

        Returns:
            List of tool names in dependency order
        """
        # Build adjacency list
        graph: Dict[str, List[str]] = {}
        for name in tool_names:
            tool = self.get(name)
            if tool:
                graph[name] = [
                    d.name for d in tool.dependencies
                    if d.required and d.name in tool_names
                ]

        # Topological sort (Kahn's algorithm)
        in_degree = {name: 0 for name in graph}
        for name in graph:
            for dep in graph[name]:
                if dep in in_degree:
                    in_degree[dep] = in_degree.get(dep, 0) + 1

        queue = [name for name, degree in in_degree.items() if degree == 0]
        result = []

        while queue:
            node = queue.pop(0)
            result.append(node)
            for dep in graph.get(node, []):
                if dep in in_degree:
                    in_degree[dep] -= 1
                    if in_degree[dep] == 0:
                        queue.append(dep)

        # Add any remaining tools not in the graph
        for name in tool_names:
            if name not in result:
                result.append(name)

        return result

    def is_supported_on_platform(self, tool_name: str, platform: str) -> bool:
        """
        Check if a tool is supported on the given platform.

        Args:
            tool_name: Name of the tool
            platform: Platform string (e.g., "windows", "macos", "linux")

        Returns:
            True if supported on the platform
        """
        tool = self.get(tool_name)
        if not tool:
            return False
        return platform.lower() in [p.lower() for p in tool.supported_platforms]

    def search(self, query: str) -> List[ToolMetadata]:
        """
        Search for tools by name, display name, or tags.

        Args:
            query: Search query string

        Returns:
            List of matching ToolMetadata
        """
        query = query.lower()
        results = []

        for tool in self._tools.values():
            if (
                query in tool.name.lower()
                or query in tool.display_name.lower()
                or any(query in tag.lower() for tag in tool.tags)
                or query in tool.description.lower()
            ):
                results.append(tool)

        return results
