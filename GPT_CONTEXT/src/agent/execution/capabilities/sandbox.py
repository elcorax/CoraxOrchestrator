"""
Corax Orchestrator - Sandbox Capability.

Provides secure execution boundaries for the autonomous agent.
Enforces path protection, command allowlisting/blocklisting,
and permission-based execution control.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, Any, List, Optional, Set, Callable
from pathlib import Path
import asyncio
import os
import fnmatch
import re

from src.agent.execution.capabilities.base import (
    CapabilityBase,
    CapabilityResult,
    CapabilityError,
    ExecutionContext,
)
from src.core.logging import get_logger

logger = get_logger(__name__)


class ExecutionPermission(Enum):
    """Permission levels for execution."""
    ALLOWED = "allowed"
    DENIED = "denied"
    REQUIRES_APPROVAL = "requires_approval"
    SANDBOXED = "sandboxed"


@dataclass
class PathProtectionRule:
    """
    A rule for protecting file system paths.

    Defines which paths the agent can read, write, or execute
    within, and which are restricted.
    """
    path: str
    allow_read: bool = True
    allow_write: bool = False
    allow_execute: bool = False
    recursive: bool = True
    description: str = ""

    def matches(self, target_path: str) -> bool:
        """Check if a path matches this rule."""
        if self.recursive:
            return target_path.startswith(self.path)
        return target_path == self.path


@dataclass
class SandboxPolicy:
    """
    Security policy for the sandbox.

    Defines what the agent is allowed to do, including
    allowed commands, blocked commands, protected paths,
    and network access rules.
    """
    allowed_commands: List[str] = field(default_factory=lambda: [
        "python", "pip", "node", "npm", "git", "docker",
        "powershell", "cmd", "where", "which", "echo",
        "dir", "ls", "cd", "pwd", "type", "cat",
        "mkdir", "copy", "move", "del", "rm",
    ])
    blocked_commands: List[str] = field(default_factory=lambda: [
        "format", "fdisk", "dd", "shutdown", "reboot",
        "init", "rm -rf /", "rm -rf ~",
    ])
    blocked_patterns: List[str] = field(default_factory=lambda: [
        r"rm\s+-rf\s+[/~]",
        r">\s*/dev/sd",
        r"mkfs\.",
        r"dd\s+if=",
    ])
    protected_paths: List[PathProtectionRule] = field(default_factory=lambda: [
        PathProtectionRule(
            path=r"C:\Windows\System32" if os.name == "nt" else "/etc",
            allow_read=True,
            allow_write=False,
            allow_execute=False,
            description="System directory protection",
        ),
        PathProtectionRule(
            path=r"C:\Program Files" if os.name == "nt" else "/usr",
            allow_read=True,
            allow_write=False,
            allow_execute=False,
            description="Program files protection",
        ),
    ])
    max_command_length: int = 10000
    allow_network_access: bool = True
    allowed_domains: List[str] = field(default_factory=lambda: [
        "*.github.com", "*.python.org", "*.npmjs.com",
        "*.docker.com", "*.google.com", "*.microsoft.com",
    ])
    blocked_domains: List[str] = field(default_factory=list)
    max_file_size_mb: int = 100
    allow_environment_override: bool = True


class SandboxCapability(CapabilityBase):
    """
    Sandbox capability for secure execution.

    Provides:
    - Command allowlisting and blocklisting
    - Path protection rules
    - Permission-based execution control
    - Command validation and sanitization
    - Network access control
    - File size limits
    - Security event logging
    """

    def __init__(self) -> None:
        super().__init__()
        self._policy: Optional[SandboxPolicy] = None
        self._approval_callbacks: List[Callable] = []
        self._violations: List[Dict[str, Any]] = []

    @property
    def name(self) -> str:
        return "sandbox"

    @property
    def version(self) -> str:
        return "1.0.0"

    @property
    def description(self) -> str:
        return (
            "Secure execution boundaries providing command validation, "
            "path protection, and permission-based execution control "
            "for safe autonomous operation."
        )

    async def initialize(self, context: ExecutionContext) -> None:
        """Initialize the sandbox capability."""
        self._context = context
        self._policy = SandboxPolicy()
        self._initialized = True
        logger.info("Sandbox capability initialized")

    async def shutdown(self) -> None:
        """Shutdown the sandbox."""
        self._initialized = False
        logger.info("Sandbox capability shut down")

    async def health_check(self) -> Dict[str, Any]:
        """Check sandbox capability health."""
        return {
            "healthy": self._initialized,
            "policy_active": self._policy is not None,
            "violation_count": len(self._violations),
            "initialized": self._initialized,
        }

    async def get_capabilities(self) -> List[Dict[str, Any]]:
        """List sandbox operations."""
        return [
            {
                "name": "check_command",
                "description": "Check if a command is allowed",
                "parameters": ["command"],
            },
            {
                "name": "check_path",
                "description": "Check if a path operation is allowed",
                "parameters": ["path", "operation"],
            },
            {
                "name": "check_network",
                "description": "Check if a network request is allowed",
                "parameters": ["domain", "port"],
            },
            {
                "name": "get_policy",
                "description": "Get the current sandbox policy",
                "parameters": [],
            },
            {
                "name": "update_policy",
                "description": "Update the sandbox policy",
                "parameters": ["policy_updates"],
            },
            {
                "name": "get_violations",
                "description": "Get security violation history",
                "parameters": ["limit"],
            },
            {
                "name": "request_approval",
                "description": "Request approval for a restricted operation",
                "parameters": ["operation", "reason"],
            },
        ]

    # --- Command Validation ---

    async def check_command(self, command: str) -> CapabilityResult:
        """
        Check if a command is allowed by the sandbox policy.

        Args:
            command: The command to validate

        Returns:
            CapabilityResult with permission status
        """
        if not self._policy:
            return CapabilityResult(
                success=True,
                capability=self.name,
                data={"permission": ExecutionPermission.ALLOWED.value},
            )

        # Check command length
        if len(command) > self._policy.max_command_length:
            self._log_violation("command_too_long", command)
            return CapabilityResult(
                success=False,
                capability=self.name,
                error=f"Command exceeds max length of {self._policy.max_command_length}",
                data={"permission": ExecutionPermission.DENIED.value},
            )

        # Extract base command
        base_cmd = command.strip().split()[0].lower() if command.strip() else ""

        # Check blocked patterns
        for pattern in self._policy.blocked_patterns:
            if re.search(pattern, command, re.IGNORECASE):
                self._log_violation("blocked_pattern", command, pattern)
                return CapabilityResult(
                    success=False,
                    capability=self.name,
                    error=f"Command matches blocked pattern: {pattern}",
                    data={"permission": ExecutionPermission.DENIED.value},
                )

        # Check blocked commands
        for blocked in self._policy.blocked_commands:
            if command.strip().lower().startswith(blocked.lower()):
                self._log_violation("blocked_command", command, blocked)
                return CapabilityResult(
                    success=False,
                    capability=self.name,
                    error=f"Command is blocked: {blocked}",
                    data={"permission": ExecutionPermission.DENIED.value},
                )

        # Check allowed commands
        if self._policy.allowed_commands:
            is_allowed = any(
                command.strip().lower().startswith(allowed.lower())
                for allowed in self._policy.allowed_commands
            )
            if not is_allowed:
                # Check if it requires approval
                if self._context and self._context.mode == "safe":
                    return CapabilityResult(
                        success=False,
                        capability=self.name,
                        error=f"Command not in allowlist: {base_cmd}",
                        data={
                            "permission": ExecutionPermission.REQUIRES_APPROVAL.value,
                            "command": command,
                        },
                    )

        return CapabilityResult(
            success=True,
            capability=self.name,
            data={"permission": ExecutionPermission.ALLOWED.value},
        )

    # --- Path Validation ---

    async def check_path(
        self,
        path: str,
        operation: str = "read",
    ) -> CapabilityResult:
        """
        Check if a path operation is allowed.

        Args:
            path: The file system path
            operation: The operation (read, write, execute)

        Returns:
            CapabilityResult with permission status
        """
        if not self._policy:
            return CapabilityResult(
                success=True,
                capability=self.name,
                data={"permission": ExecutionPermission.ALLOWED.value},
            )

        abs_path = os.path.abspath(path)

        for rule in self._policy.protected_paths:
            if rule.matches(abs_path):
                if operation == "read" and not rule.allow_read:
                    return CapabilityResult(
                        success=False,
                        capability=self.name,
                        error=f"Read access denied to protected path: {path}",
                        data={"permission": ExecutionPermission.DENIED.value},
                    )
                elif operation == "write" and not rule.allow_write:
                    return CapabilityResult(
                        success=False,
                        capability=self.name,
                        error=f"Write access denied to protected path: {path}",
                        data={"permission": ExecutionPermission.DENIED.value},
                    )
                elif operation == "execute" and not rule.allow_execute:
                    return CapabilityResult(
                        success=False,
                        capability=self.name,
                        error=f"Execute access denied to protected path: {path}",
                        data={"permission": ExecutionPermission.DENIED.value},
                    )

        return CapabilityResult(
            success=True,
            capability=self.name,
            data={"permission": ExecutionPermission.ALLOWED.value},
        )

    # --- Network Validation ---

    async def check_network(
        self,
        domain: str,
        port: Optional[int] = None,
    ) -> CapabilityResult:
        """
        Check if a network request is allowed.

        Args:
            domain: The domain to check
            port: The port to check

        Returns:
            CapabilityResult with permission status
        """
        if not self._policy:
            return CapabilityResult(
                success=True,
                capability=self.name,
                data={"permission": ExecutionPermission.ALLOWED.value},
            )

        if not self._policy.allow_network_access:
            return CapabilityResult(
                success=False,
                capability=self.name,
                error="Network access is disabled",
                data={"permission": ExecutionPermission.DENIED.value},
            )

        # Check blocked domains
        for blocked in self._policy.blocked_domains:
            if fnmatch.fnmatch(domain, blocked):
                return CapabilityResult(
                    success=False,
                    capability=self.name,
                    error=f"Domain is blocked: {domain}",
                    data={"permission": ExecutionPermission.DENIED.value},
                )

        # Check allowed domains
        if self._policy.allowed_domains:
            is_allowed = any(
                fnmatch.fnmatch(domain, allowed)
                for allowed in self._policy.allowed_domains
            )
            if not is_allowed:
                return CapabilityResult(
                    success=False,
                    capability=self.name,
                    error=f"Domain not in allowlist: {domain}",
                    data={
                        "permission": ExecutionPermission.REQUIRES_APPROVAL.value,
                        "domain": domain,
                    },
                )

        return CapabilityResult(
            success=True,
            capability=self.name,
            data={"permission": ExecutionPermission.ALLOWED.value},
        )

    # --- Policy Management ---

    async def get_policy(self) -> Dict[str, Any]:
        """Get the current sandbox policy."""
        if not self._policy:
            return {"active": False}
        return {
            "active": True,
            "allowed_commands": self._policy.allowed_commands,
            "blocked_commands": self._policy.blocked_commands,
            "protected_paths": [
                {
                    "path": r.path,
                    "allow_read": r.allow_read,
                    "allow_write": r.allow_write,
                    "allow_execute": r.allow_execute,
                    "description": r.description,
                }
                for r in self._policy.protected_paths
            ],
            "allow_network_access": self._policy.allow_network_access,
            "allowed_domains": self._policy.allowed_domains,
            "max_command_length": self._policy.max_command_length,
        }

    async def update_policy(self, policy_updates: Dict[str, Any]) -> CapabilityResult:
        """
        Update the sandbox policy.

        Args:
            policy_updates: Dict with policy fields to update

        Returns:
            CapabilityResult
        """
        if not self._policy:
            return CapabilityResult(
                success=False,
                capability=self.name,
                error="Sandbox not initialized",
            )

        try:
            for key, value in policy_updates.items():
                if hasattr(self._policy, key):
                    setattr(self._policy, key, value)

            logger.info("Sandbox policy updated", updates=list(policy_updates.keys()))

            return CapabilityResult(
                success=True,
                capability=self.name,
                data={"updated_fields": list(policy_updates.keys())},
            )

        except Exception as e:
            return CapabilityResult(
                success=False,
                capability=self.name,
                error=str(e),
            )

    # --- Violation Tracking ---

    async def get_violations(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Get security violation history."""
        return self._violations[-limit:]

    # --- Approval Requests ---

    async def request_approval(
        self,
        operation: str,
        reason: str,
    ) -> CapabilityResult:
        """
        Request approval for a restricted operation.

        Args:
            operation: Description of the operation
            reason: Why the operation is needed

        Returns:
            CapabilityResult
        """
        request = {
            "operation": operation,
            "reason": reason,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        # Notify approval callbacks
        for callback in self._approval_callbacks:
            try:
                callback(request)
            except Exception as e:
                logger.error("Approval callback error", error=str(e))

        return CapabilityResult(
            success=True,
            capability=self.name,
            data={
                "message": "Approval request submitted",
                "request": request,
            },
        )

    def on_approval_request(self, callback: Callable[[Dict[str, Any]], None]) -> None:
        """Register a callback for approval requests."""
        self._approval_callbacks.append(callback)

    # --- Internal Methods ---

    def _log_violation(
        self,
        violation_type: str,
        command: str,
        pattern: Optional[str] = None,
    ) -> None:
        """Log a security violation."""
        violation = {
            "type": violation_type,
            "command": command[:200],
            "pattern": pattern,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        self._violations.append(violation)
        logger.warning(
            "Sandbox violation",
            violation_type=violation_type,
            command=command[:100],
        )
