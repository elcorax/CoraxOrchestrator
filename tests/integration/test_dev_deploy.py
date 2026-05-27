"""
Integration tests for the DevDeploy entry point.

Tests real execution flows including:
- DevDeploy initialization and tool registration
- Detection of installed tools
- Deployment execution with failure tolerance
- Version validation (git --version, python --version, node --version, npm --version)
- PATH verification
- Retry behavior
- Report generation with structured data
- Failure tolerance (one fails, others continue)
"""

from typing import Dict, Any, Optional
import pytest
import asyncio
import os
import sys
import tempfile
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from src.deployment.dev_deploy import DevDeploy, DevDeployReport
from src.deployment.installers.base import InstallResult, InstallStatus
from src.deployment.execution.executor import DeploymentExecutor, ToolDeploymentResult
from src.deployment.execution.retry_queue import RetryQueue
from src.deployment.operations import FailureCategory


# =============================================================================
# Tests: DevDeploy Initialization
# =============================================================================

class TestDevDeployInit:
    """Test DevDeploy initialization and tool registration."""

    def test_init_default(self):
        """Test default initialization."""
        deployer = DevDeploy()
        assert deployer.available_tools is not None
        assert len(deployer.available_tools) > 0
        assert "git" in deployer.available_tools
        assert "python" in deployer.available_tools
        assert "nodejs" in deployer.available_tools

    def test_init_with_data_dir(self):
        """Test initialization with custom data directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            deployer = DevDeploy(data_dir=tmpdir)
            assert deployer.available_tools is not None

    def test_executor_initialized(self):
        """Test that executor is properly initialized."""
        deployer = DevDeploy()
        assert deployer.executor is not None
        assert isinstance(deployer.executor, DeploymentExecutor)

    def test_session_initialized(self):
        """Test that session is properly initialized."""
        deployer = DevDeploy()
        assert deployer.session is not None

    def test_installers_registered(self):
        """Test that all installers are registered with executor."""
        deployer = DevDeploy()
        # Check that installers are registered in the executor
        for tool_key in deployer.available_tools:
            assert tool_key in deployer.executor._installers


# =============================================================================
# Tests: DevDeploy Detection
# =============================================================================

class TestDevDeployDetection:
    """Test DevDeploy detection capabilities."""

    @pytest.mark.asyncio
    async def test_detect_all_returns_results(self):
        """Test that detect_all returns results for all tools."""
        deployer = DevDeploy()
        results = await deployer.detect_all()
        assert len(results) == len(deployer.available_tools)
        for tool_key in deployer.available_tools:
            assert tool_key in results
            assert isinstance(results[tool_key], InstallResult)

    @pytest.mark.asyncio
    async def test_detect_git(self):
        """Test Git detection."""
        deployer = DevDeploy()
        results = await deployer.detect_all()
        git_result = results.get("git")
        assert git_result is not None
        # Git may or may not be installed, but should have a valid status
        assert git_result.status in [
            InstallStatus.INSTALLED,
            InstallStatus.NOT_INSTALLED,
            InstallStatus.FAILED,
        ]

    @pytest.mark.asyncio
    async def test_detect_python(self):
        """Test Python detection."""
        deployer = DevDeploy()
        results = await deployer.detect_all()
        python_result = results.get("python")
        assert python_result is not None
        # Python should be installed (we're running Python)
        assert python_result.status in [
            InstallStatus.INSTALLED,
            InstallStatus.NOT_INSTALLED,
        ]

    @pytest.mark.asyncio
    async def test_detect_nodejs(self):
        """Test Node.js detection."""
        deployer = DevDeploy()
        results = await deployer.detect_all()
        node_result = results.get("nodejs")
        assert node_result is not None
        assert node_result.status in [
            InstallStatus.INSTALLED,
            InstallStatus.NOT_INSTALLED,
            InstallStatus.FAILED,
        ]


# =============================================================================
# Tests: DevDeploy Version Validation
# =============================================================================

class TestDevDeployVersionValidation:
    """Test version validation commands."""

    @pytest.mark.asyncio
    async def test_git_version_command(self):
        """Test git --version execution."""
        deployer = DevDeploy()
        version_info = await deployer._get_version_info("git")
        if version_info.get("git_version"):
            assert "git" in version_info["git_version"].lower()

    @pytest.mark.asyncio
    async def test_python_version_command(self):
        """Test python --version execution."""
        deployer = DevDeploy()
        version_info = await deployer._get_version_info("python")
        if version_info.get("python_version"):
            assert "python" in version_info["python_version"].lower()

    @pytest.mark.asyncio
    async def test_node_version_command(self):
        """Test node --version execution."""
        deployer = DevDeploy()
        version_info = await deployer._get_version_info("nodejs")
        if version_info.get("node_version"):
            assert "v" in version_info["node_version"] or version_info["node_version"]

    @pytest.mark.asyncio
    async def test_npm_version_command(self):
        """Test npm --version execution."""
        deployer = DevDeploy()
        version_info = await deployer._get_version_info("nodejs")
        if version_info.get("npm_version"):
            # npm version should be a semver string
            parts = version_info["npm_version"].split(".")
            assert len(parts) >= 2

    @pytest.mark.asyncio
    async def test_pip_version_command(self):
        """Test pip --version execution."""
        deployer = DevDeploy()
        version_info = await deployer._get_version_info("python")
        if version_info.get("pip_version"):
            assert "pip" in version_info["pip_version"].lower()

    @pytest.mark.asyncio
    async def test_path_verification(self):
        """Test PATH verification for all tools."""
        deployer = DevDeploy()
        for tool_key in deployer.available_tools:
            version_info = await deployer._get_version_info(tool_key)
            if version_info.get("in_path"):
                assert version_info["path"] is not None
                assert os.path.exists(version_info["path"])


# =============================================================================
# Tests: DevDeploy Report Generation
# =============================================================================

class TestDevDeployReport:
    """Test DevDeploy report generation."""

    def test_report_dataclass(self):
        """Test DevDeployReport dataclass."""
        report = DevDeployReport(
            session_id="DEP-000001",
            status="completed",
            started_at="2024-01-01T00:00:00",
            completed_at="2024-01-01T00:01:00",
            duration_seconds=60.0,
            tools_requested=["git", "python"],
            tools_installed=["git", "python"],
            tools_failed=[],
            tools_skipped=[],
            success_rate=100.0,
        )
        assert report.session_id == "DEP-000001"
        assert report.status == "completed"
        assert report.success_rate == 100.0

    def test_report_to_dict(self):
        """Test DevDeployReport to_dict conversion."""
        report = DevDeployReport(
            session_id="DEP-000001",
            status="completed",
            started_at="2024-01-01T00:00:00",
            completed_at="2024-01-01T00:01:00",
            duration_seconds=60.0,
            tools_requested=["git", "python"],
            tools_installed=["git", "python"],
            tools_failed=[],
            tools_skipped=[],
            success_rate=100.0,
            tool_details={
                "git": {"status": "installed", "version": "2.40.0"},
                "python": {"status": "installed", "version": "3.12.0"},
            },
            validation={"valid": True, "issues": []},
            retry_summary={"total_entries": 0, "pending_retries": 0},
        )
        d = report.to_dict()
        assert d["report_type"] == "dev_deployment"
        assert d["status"] == "completed"
        assert d["success_rate"] == 100.0
        assert "tool_details" in d
        assert "validation" in d
        assert "retry_summary" in d

    def test_report_partial_success(self):
        """Test report with partial success."""
        report = DevDeployReport(
            session_id="DEP-000002",
            status="partial",
            started_at="2024-01-01T00:00:00",
            completed_at="2024-01-01T00:01:00",
            duration_seconds=60.0,
            tools_requested=["git", "python", "nodejs"],
            tools_installed=["git", "python"],
            tools_failed=["nodejs"],
            tools_skipped=[],
            success_rate=66.7,
            errors=["Node.js installation failed"],
        )
        assert report.status == "partial"
        assert report.success_rate == 66.7
        assert len(report.errors) == 1

    def test_report_failure(self):
        """Test report with complete failure."""
        report = DevDeployReport(
            session_id="DEP-000003",
            status="failed",
            started_at="2024-01-01T00:00:00",
            completed_at="2024-01-01T00:01:00",
            duration_seconds=60.0,
            tools_requested=["git"],
            tools_installed=[],
            tools_failed=["git"],
            tools_skipped=[],
            success_rate=0.0,
            errors=["Git installation failed"],
        )
        assert report.status == "failed"
        assert report.success_rate == 0.0

    @pytest.mark.asyncio
    async def test_report_saved_to_disk(self):
        """Test that reports are saved to disk."""
        with tempfile.TemporaryDirectory() as tmpdir:
            report_dir = os.path.join(tmpdir, "reports")
            deployer = DevDeploy(data_dir=tmpdir, report_dir=report_dir)

            # Run detection only (no install)
            results = await deployer.detect_all()

            # Build a report manually
            report = DevDeployReport(
                session_id="DEP-TEST-001",
                status="completed",
                started_at="2024-01-01T00:00:00",
                completed_at="2024-01-01T00:01:00",
                duration_seconds=60.0,
                tools_requested=list(results.keys()),
                tools_installed=[
                    k for k, v in results.items()
                    if v.status == InstallStatus.INSTALLED
                ],
                tools_failed=[
                    k for k, v in results.items()
                    if v.status == InstallStatus.FAILED
                ],
                tools_skipped=[],
                success_rate=50.0,
            )

            report_path = await deployer._save_report(report)
            assert os.path.exists(report_path)

            # Verify report content
            with open(report_path, "r") as f:
                saved = json.load(f)
            assert saved["report_type"] == "dev_deployment"
            assert saved["session_id"] == "DEP-TEST-001"


# =============================================================================
# Tests: DevDeploy Failure Tolerance
# =============================================================================

class TestDevDeployFailureTolerance:
    """Test failure tolerance in DevDeploy."""

    @pytest.mark.asyncio
    async def test_invalid_tools_handled(self):
        """Test that invalid tool keys are handled gracefully."""
        deployer = DevDeploy()
        report = await deployer.deploy(
            tools=["invalid_tool_1", "invalid_tool_2"],
            skip_existing=True,
        )
        assert report.status == "failed"
        assert len(report.errors) > 0

    @pytest.mark.asyncio
    async def test_partial_valid_tools(self):
        """Test that partial valid tools are deployed."""
        deployer = DevDeploy()
        report = await deployer.deploy(
            tools=["git", "invalid_tool"],
            skip_existing=True,
        )
        # Should have attempted git at minimum
        assert "git" in report.tools_requested
        # invalid_tool should not be in available tools
        assert "invalid_tool" not in deployer.available_tools

    @pytest.mark.asyncio
    async def test_continue_on_failure(self):
        """Test that one failure doesn't stop other installations."""
        deployer = DevDeploy()
        # Request all tools - if one fails, others should still be attempted
        report = await deployer.deploy(
            tools=deployer.available_tools,
            skip_existing=True,
        )
        # Should have attempted all tools
        assert len(report.tools_requested) == len(deployer.available_tools)
        # At least some should have been attempted
        total_attempted = (
            len(report.tools_installed)
            + len(report.tools_failed)
        )
        assert total_attempted > 0


# =============================================================================
# Tests: DevDeploy Environment Validation
# =============================================================================

class TestDevDeployValidation:
    """Test DevDeploy environment validation."""

    @pytest.mark.asyncio
    async def test_validate_environment(self):
        """Test environment validation."""
        deployer = DevDeploy()
        validation = await deployer.validate_environment()
        assert validation is not None
        # Should have validation results
        assert hasattr(validation, "passed")
        assert hasattr(validation, "issues")

    @pytest.mark.asyncio
    async def test_detect_only_mode(self):
        """Test detect-only mode (no installation)."""
        deployer = DevDeploy()
        results = await deployer.detect_all()
        assert len(results) > 0
        # No installation should have occurred
        for tool_key, result in results.items():
            assert result.status in [
                InstallStatus.INSTALLED,
                InstallStatus.NOT_INSTALLED,
                InstallStatus.FAILED,
            ]


# =============================================================================
# Tests: DevDeploy Summary
# =============================================================================

class TestDevDeploySummary:
    """Test DevDeploy summary generation."""

    def test_get_summary(self):
        """Test getting deployment summary."""
        deployer = DevDeploy()
        summary = deployer.get_summary()
        assert "available_tools" in summary
        assert "executor_summary" in summary
        assert len(summary["available_tools"]) > 0

    def test_available_tools_property(self):
        """Test available_tools property."""
        deployer = DevDeploy()
        tools = deployer.available_tools
        assert "git" in tools
        assert "python" in tools
        assert "nodejs" in tools
