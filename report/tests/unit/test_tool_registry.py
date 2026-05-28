"""
Tests for the Tool Registry module.
"""

import pytest
from src.modules.tool_registry import (
    ToolRegistry,
    ToolMetadata,
    ToolDependency,
    ToolCategory,
)


class TestToolRegistry:
    """Test suite for ToolRegistry."""

    def test_registry_has_builtins(self):
        """Test that built-in tools are loaded."""
        registry = ToolRegistry()
        tools = registry.get_all()
        assert len(tools) > 0

    def test_get_known_tool(self):
        """Test getting a known tool."""
        registry = ToolRegistry()
        tool = registry.get("ollama")
        assert tool is not None
        assert tool.name == "ollama"
        assert tool.display_name == "Ollama"

    def test_get_unknown_tool(self):
        """Test getting an unknown tool returns None."""
        registry = ToolRegistry()
        tool = registry.get("nonexistent_tool")
        assert tool is None

    def test_get_by_category(self):
        """Test filtering tools by category."""
        registry = ToolRegistry()
        ai_tools = registry.get_by_category(ToolCategory.AI_PLATFORM)
        assert len(ai_tools) > 0
        for tool in ai_tools:
            assert tool.category == ToolCategory.AI_PLATFORM

    def test_search_by_name(self):
        """Test searching tools by name."""
        registry = ToolRegistry()
        results = registry.search("ollama")
        assert len(results) > 0
        assert any("ollama" in r.name for r in results)

    def test_search_by_tag(self):
        """Test searching tools by tag."""
        registry = ToolRegistry()
        results = registry.search("llm")
        assert len(results) > 0

    def test_register_custom_tool(self):
        """Test registering a custom tool."""
        registry = ToolRegistry()
        custom = ToolMetadata(
            name="custom_tool",
            display_name="Custom Tool",
            description="A custom tool for testing",
            category=ToolCategory.UTILITY,
        )
        registry.register(custom)
        assert registry.get("custom_tool") is not None

    def test_get_dependencies(self):
        """Test getting tool dependencies."""
        registry = ToolRegistry()
        deps = registry.get_dependencies("open_interpreter")
        assert len(deps) > 0
        assert any(d.name == "python" for d in deps)

    def test_get_install_order(self):
        """Test topological sort for install order."""
        registry = ToolRegistry()
        order = registry.get_install_order(["open_interpreter", "comfy_ui"])
        # Python should come before tools that depend on it
        python_pos = order.index("python") if "python" in order else -1
        comfy_pos = order.index("comfy_ui") if "comfy_ui" in order else -1
        if python_pos >= 0 and comfy_pos >= 0:
            assert python_pos < comfy_pos

    def test_is_supported_on_platform(self):
        """Test platform compatibility check."""
        registry = ToolRegistry()
        assert registry.is_supported_on_platform("ollama", "windows") is True
        assert registry.is_supported_on_platform("lm_studio", "linux") is False
