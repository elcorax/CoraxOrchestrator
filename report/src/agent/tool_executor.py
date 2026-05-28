"""
Corax Orchestrator - Tool Executor.

Provides a unified interface for executing tools and actions
within the agent runtime. Acts as a bridge between the execution
engine and the underlying system modules.
"""

from typing import Dict, Any, List, Optional, Callable, Awaitable
import asyncio

from src.core.logging import get_logger
from src.core.exceptions import CoraxError

logger = get_logger(__name__)


class ToolExecutor:
    """
    Executes tools and actions on behalf of the agent.

    Provides:
    - Tool registration and discovery
    - Unified execution interface
    - Result formatting and error handling
    - Execution timeout support
    - Integration with system modules
    """

    def __init__(self) -> None:
        self._tools: Dict[str, Callable[..., Awaitable[Any]]] = {}
        self._tool_metadata: Dict[str, Dict[str, Any]] = {}

    def register_tool(
        self,
        name: str,
        executor: Callable[..., Awaitable[Any]],
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Register a tool for execution.

        Args:
            name: Tool name (used as action_type in workflows)
            executor: Async function that executes the tool
            metadata: Tool metadata (description, parameters, etc.)
        """
        self._tools[name] = executor
        self._tool_metadata[name] = metadata or {
            "name": name,
            "description": f"Tool: {name}",
            "parameters": {},
        }
        logger.debug("Tool registered", tool=name)

    async def execute(
        self,
        tool_name: str,
        parameters: Optional[Dict[str, Any]] = None,
        timeout: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Execute a tool with the given parameters.

        Args:
            tool_name: Name of the tool to execute
            parameters: Tool parameters
            timeout: Execution timeout in seconds

        Returns:
            Tool execution result

        Raises:
            CoraxError: If tool not found or execution fails
        """
        executor = self._tools.get(tool_name)
        if not executor:
            raise CoraxError(
                message=f"Tool '{tool_name}' not registered",
                recovery_hint="Register the tool before execution",
            )

        logger.info("Executing tool", tool=tool_name)

        try:
            if timeout:
                result = await asyncio.wait_for(
                    executor(**(parameters or {})),
                    timeout=timeout,
                )
            else:
                result = await executor(**(parameters or {}))

            return {
                "status": "success",
                "tool": tool_name,
                "result": result,
            }

        except asyncio.TimeoutError:
            logger.error("Tool execution timed out", tool=tool_name)
            return {
                "status": "timeout",
                "tool": tool_name,
                "error": f"Execution timed out after {timeout}s",
            }

        except Exception as e:
            logger.error("Tool execution failed", tool=tool_name, error=str(e))
            return {
                "status": "error",
                "tool": tool_name,
                "error": str(e),
            }

    def get_tool(self, name: str) -> Optional[Dict[str, Any]]:
        """Get metadata for a registered tool."""
        return self._tool_metadata.get(name)

    def list_tools(self) -> List[Dict[str, Any]]:
        """List all registered tools with metadata."""
        return [
            {"name": name, **meta}
            for name, meta in self._tool_metadata.items()
        ]

    def has_tool(self, name: str) -> bool:
        """Check if a tool is registered."""
        return name in self._tools
