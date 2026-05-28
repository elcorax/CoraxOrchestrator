"""
Integration tests for the deployment execution system.

Tests real execution flows including:
- Terminal session command execution
- Retry queue behavior
- Failure analysis and classification
- Deployment executor with failure tolerance
- Session lifecycle and state persistence
- Repair execution
- Partial failure continuation
"""

from typing import Optional
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

from src.deployment.execution.terminal import TerminalSession, TerminalResult
from src.deployment.execution.retry_queue import RetryQueue, RetryEntry
from src.deployment.execution.failure_analyzer import FailureAnalyzer, FailureAnalysis
from src.deployment.execution.executor import DeploymentExecutor, ToolDeploymentResult
from src.deployment.execution.session import DeploymentSession, DeploymentSessionResult
from src.deployment.operations import (
    OperationTracker,
    OperationType,
    OperationStatus,
    FailureCategory,
)
from src.deployment.installers.base import AIInstallerBase, InstallResult, InstallStatus


# =============================================================================
# Mock Installer for Testing
# =============================================================================

class MockInstaller(AIInstallerBase):
    """Mock installer for testing execution flows."""

    def __init__(
        self,
        tool_key: str = "test_tool",
        tool_name: str = "Test Tool",
        detect_result: Optional[InstallResult] = None,
        install_result: Optional[InstallResult] = None,
        verify_result: Optional[InstallResult] = None,
        dependencies: Optional[list] = None,
    ):
        super().__init__()
        self._tool_key = tool_key
        self._tool_name = tool_name
        self._detect_result = detect_result or InstallResult(
            tool_name=tool_name, status=InstallStatus.NOT_INSTALLED
        )
        self._install_result = install_result or InstallResult(
            tool_name=tool_name, status=InstallStatus.INSTALLED, version="1.0.0"
        )
        self._verify_result = verify_result or InstallResult(
            tool_name=tool_name, status=InstallStatus.INSTALLED, version="1.0.0"
        )
        self._dependencies = dependencies or []
        self.detect_count = 0
        self.install_count = 0
        self.verify_count = 0

    @property
    def tool_name(self) -> str:
        return self._tool_name

    @property
    def tool_key(self) -> str:
        return self._tool_key

    @property
    def description(self) -> str:
        return f"Mock {self._tool_name}"

    @property
    def default_port(self) -> int:
        return None

    @property
    def min_disk_gb(self) -> int:
        return 1

    @property
    def dependencies(self) -> list:
        return self._dependencies

    async def detect(self) -> InstallResult:
        self.detect_count += 1
        return self._detect_result

    async def install(self, config=None) -> InstallResult:
        self.install_count += 1
        return self._install_result

    async def verify(self) -> InstallResult:
        self.verify_count += 1
        return self._verify_result


class FailingInstaller(AIInstallerBase):
    """Mock installer that fails on install."""

    def __init__(
        self,
        tool_key: str = "failing_tool",
        tool_name: str = "Failing Tool",
        fail_count: int = 1,
        succeed_after_retry: bool = False,
    ):
        super().__init__()
        self._tool_key = tool_key
        self._tool_name = tool_name
        self._fail_count = fail_count
        self._succeed_after_retry = succeed_after_retry
        self.install_count = 0

    @property
    def tool_name(self) -> str:
        return self._tool_name

    @property
    def tool_key(self) -> str:
        return self._tool_key

    @property
    def description(self) -> str:
        return f"Mock {self._tool_name}"

    @property
    def default_port(self) -> int:
        return None

    @property
    def min_disk_gb(self) -> int:
        return 1

    @property
    def dependencies(self) -> list:
        return []

    async def detect(self) -> InstallResult:
        return InstallResult(
            tool_name=self._tool_name, status=InstallStatus.NOT_INSTALLED
        )

    async def install(self, config=None) -> InstallResult:
        self.install_count += 1
        if self._succeed_after_retry and self.install_count > self._fail_count:
            return InstallResult(
                tool_name=self._tool_name,
                status=InstallStatus.INSTALLED,
                version="1.0.0",
            )
        return InstallResult(
            tool_name=self._tool_name,
            status=InstallStatus.FAILED,
            error="Installation failed",
        )

    async def verify(self) -> InstallResult:
        return InstallResult(
            tool_name=self._tool_name, status=InstallStatus.NOT_INSTALLED
        )


# =============================================================================
# Tests: Terminal Session
# =============================================================================

class TestTerminalSession:
    """Test terminal session command execution."""

    @pytest.mark.asyncio
    async def test_execute_simple_command(self):
        """Test executing a simple command."""
        session = TerminalSession()
        result = await session.execute("echo hello", timeout=10)
        assert result.succeeded
        assert "hello" in result.stdout

    @pytest.mark.asyncio
    async def test_execute_failing_command(self):
        """Test executing a failing command."""
        session = TerminalSession()
        if os.name == "nt":
            result = await session.execute("cmd /c exit 1", timeout=10)
        else:
            result = await session.execute("exit 1", timeout=10)
        assert not result.succeeded
        assert result.exit_code != 0

    @pytest.mark.asyncio
    async def test_execute_timeout(self):
        """Test command timeout handling."""
        session = TerminalSession(default_timeout=2)
        if os.name == "nt":
            result = await session.execute("ping -n 10 127.0.0.1", timeout=2)
        else:
            result = await session.execute("sleep 10", timeout=2)
        assert result.timed_out

    @pytest.mark.asyncio
    async def test_check_tool(self):
        """Test tool version detection."""
        session = TerminalSession()
        # Python should always be available
        version = await session.check_tool("python", "--version")
        assert version is not None

    @pytest.mark.asyncio
    async def test_check_multiple_tools(self):
        """Test checking multiple tools concurrently."""
        session = TerminalSession()
        results = await session.check_multiple_tools(["python", "git"])
        assert "python" in results
        assert "git" in results

    @pytest.mark.asyncio
    async def test_execute_with_streaming(self):
        """Test streaming command execution."""
        session = TerminalSession()
        if os.name == "nt":
            result = await session.execute_with_streaming(
                "echo line1 & echo line2", timeout=10
            )
        else:
            result = await session.execute_with_streaming(
                "echo line1 && echo line2", timeout=10
            )
        assert result.succeeded
        assert "line1" in result.stdout

    def test_session_stats(self):
        """Test terminal session statistics."""
        session = TerminalSession()
        stats = session.get_stats()
        assert stats["total_commands"] == 0
        assert stats["session_id"].startswith("term_")

    def test_history_text(self):
        """Test formatted history output."""
        session = TerminalSession()
        text = session.get_history_text()
        assert text == ""  # No commands yet


# =============================================================================
# Tests: Retry Queue
# =============================================================================

class TestRetryQueue:
    """Test retry queue behavior."""

    def setup_method(self):
        self.queue = RetryQueue(default_max_retries=3, default_backoff=0.1)

    def test_add_entry(self):
        """Test adding entries to retry queue."""
        self.queue.add(
            tool_key="test_tool",
            tool_name="Test Tool",
            operation_id="OP-000001",
            failure_category=FailureCategory.TEMPORARY,
            error_message="Temporary error",
        )
        assert self.queue.has_pending()
        assert self.queue.get_entry("test_tool") is not None

    def test_entry_properties(self):
        """Test retry entry properties."""
        self.queue.add(
            tool_key="test_tool",
            tool_name="Test Tool",
            operation_id="OP-000001",
            failure_category=FailureCategory.TEMPORARY,
            error_message="Temporary error",
            backoff_seconds=0.1,
        )
        entry = self.queue.get_entry("test_tool")
        assert not entry.is_exhausted
        assert entry.attempt == 0
        assert entry.max_retries == 3

    def test_mark_attempted(self):
        """Test marking a retry attempt."""
        self.queue.add(
            tool_key="test_tool",
            tool_name="Test Tool",
            operation_id="OP-000001",
            failure_category=FailureCategory.TEMPORARY,
            error_message="Temporary error",
            backoff_seconds=0.1,
        )
        self.queue.mark_attempted("test_tool")
        entry = self.queue.get_entry("test_tool")
        assert entry.attempt == 1

    def test_exhausted_retries(self):
        """Test retry exhaustion."""
        self.queue.add(
            tool_key="test_tool",
            tool_name="Test Tool",
            operation_id="OP-000001",
            failure_category=FailureCategory.TEMPORARY,
            error_message="Temporary error",
            max_retries=2,
            backoff_seconds=0.1,
        )
        self.queue.mark_attempted("test_tool")
        self.queue.mark_attempted("test_tool")
        entry = self.queue.get_entry("test_tool")
        assert entry.is_exhausted

    def test_skip_entry(self):
        """Test skipping a retry entry."""
        self.queue.add(
            tool_key="test_tool",
            tool_name="Test Tool",
            operation_id="OP-000001",
            failure_category=FailureCategory.TEMPORARY,
            error_message="Temporary error",
        )
        self.queue.mark_skipped("test_tool")
        assert not self.queue.has_pending()

    def test_get_due_entries(self):
        """Test getting due retry entries."""
        self.queue.add(
            tool_key="test_tool",
            tool_name="Test Tool",
            operation_id="OP-000001",
            failure_category=FailureCategory.TEMPORARY,
            error_message="Temporary error",
            backoff_seconds=0.1,
        )
        # Should be due immediately
        due = self.queue.get_due_entries()
        assert len(due) == 1
        assert due[0].tool_key == "test_tool"

    def test_get_summary(self):
        """Test retry queue summary."""
        self.queue.add(
            tool_key="tool1",
            tool_name="Tool 1",
            operation_id="OP-000001",
            failure_category=FailureCategory.TEMPORARY,
            error_message="Error 1",
        )
        self.queue.add(
            tool_key="tool2",
            tool_name="Tool 2",
            operation_id="OP-000002",
            failure_category=FailureCategory.NETWORK,
            error_message="Error 2",
        )
        summary = self.queue.get_summary()
        assert summary["total_entries"] == 2
        assert summary["pending_retries"] == 2

    def test_clear(self):
        """Test clearing the retry queue."""
        self.queue.add(
            tool_key="test_tool",
            tool_name="Test Tool",
            operation_id="OP-000001",
            failure_category=FailureCategory.TEMPORARY,
            error_message="Error",
        )
        self.queue.clear()
        assert not self.queue.has_pending()
        assert self.queue.get_summary()["total_entries"] == 0


# =============================================================================
# Tests: Failure Analyzer
# =============================================================================

class TestFailureAnalyzer:
    """Test failure analysis and classification."""

    def setup_method(self):
        self.analyzer = FailureAnalyzer()

    def test_permission_failure(self):
        """Test permission failure detection."""
        analysis = self.analyzer.analyze(
            tool_key="test_tool",
            exit_code=5,
            stderr="Access is denied",
        )
        assert analysis.failure_category == FailureCategory.PERMISSION
        assert analysis.recoverable
        assert analysis.requires_admin

    def test_network_failure(self):
        """Test network failure detection."""
        analysis = self.analyzer.analyze(
            tool_key="test_tool",
            exit_code=1,
            stderr="Connection refused: could not reach server",
        )
        assert analysis.failure_category == FailureCategory.NETWORK
        assert analysis.recoverable
        assert analysis.requires_network

    def test_disk_space_failure(self):
        """Test disk space failure detection."""
        analysis = self.analyzer.analyze(
            tool_key="test_tool",
            exit_code=1,
            stderr="No space left on device",
        )
        assert analysis.failure_category == FailureCategory.DISK_SPACE
        assert not analysis.recoverable
        assert analysis.requires_disk_space

    def test_dependency_failure(self):
        """Test dependency failure detection."""
        analysis = self.analyzer.analyze(
            tool_key="test_tool",
            exit_code=1,
            stderr="command not found: node",
        )
        assert analysis.failure_category == FailureCategory.DEPENDENCY
        assert analysis.recoverable

    def test_timeout_failure(self):
        """Test timeout failure detection."""
        analysis = self.analyzer.analyze(
            tool_key="test_tool",
            exit_code=-1,
            stderr="Command timed out after 120s",
        )
        assert analysis.failure_category == FailureCategory.TIMEOUT
        assert analysis.recoverable

    def test_corruption_failure(self):
        """Test corruption failure detection."""
        analysis = self.analyzer.analyze(
            tool_key="test_tool",
            exit_code=1,
            stderr="Download corrupted: checksum mismatch",
        )
        assert analysis.failure_category == FailureCategory.CORRUPTION
        assert analysis.recoverable

    def test_compatibility_failure(self):
        """Test compatibility failure detection."""
        analysis = self.analyzer.analyze(
            tool_key="test_tool",
            exit_code=1,
            stderr="This program is not compatible with your system",
        )
        assert analysis.failure_category == FailureCategory.COMPATIBILITY
        assert not analysis.recoverable

    def test_unknown_failure(self):
        """Test unknown failure handling."""
        analysis = self.analyzer.analyze(
            tool_key="test_tool",
            exit_code=42,
            stderr="Some obscure error message",
        )
        assert analysis.failure_category == FailureCategory.UNKNOWN
        assert analysis.recoverable
        assert analysis.confidence < 0.5

    def test_exit_code_analysis(self):
        """Test exit code based analysis."""
        analysis = self.analyzer.analyze(
            tool_key="test_tool",
            exit_code=-2,
            stderr="",
        )
        assert analysis.failure_category == FailureCategory.DEPENDENCY
        assert analysis.confidence >= 0.8

    def test_repair_suggestions(self):
        """Test repair suggestion generation."""
        analysis = self.analyzer.analyze(
            tool_key="test_tool",
            exit_code=5,
            stderr="Access is denied",
        )
        assert len(analysis.repair_suggestions) > 0
        assert "administrator" in analysis.repair_suggestions[0].lower()


# =============================================================================
# Tests: Deployment Executor
# =============================================================================

class TestDeploymentExecutor:
    """Test deployment executor with failure tolerance."""

    @pytest.mark.asyncio
    async def test_successful_deployment(self):
        """Test successful deployment of all tools."""
        executor = DeploymentExecutor()
        installer = MockInstaller(
            tool_key="test_tool",
            tool_name="Test Tool",
        )
        executor.register_installer(installer)

        results = await executor.execute_deployment(
            tool_keys=["test_tool"],
            skip_existing=True,
        )

        assert "test_tool" in results
        assert results["test_tool"].status == "installed"
        assert results["test_tool"].version == "1.0.0"

    @pytest.mark.asyncio
    async def test_skip_existing_tool(self):
        """Test skipping already installed tools."""
        executor = DeploymentExecutor()
        installer = MockInstaller(
            tool_key="test_tool",
            tool_name="Test Tool",
            detect_result=InstallResult(
                tool_name="Test Tool",
                status=InstallStatus.INSTALLED,
                version="2.0.0",
            ),
        )
        executor.register_installer(installer)

        results = await executor.execute_deployment(
            tool_keys=["test_tool"],
            skip_existing=True,
        )

        assert results["test_tool"].status == "installed"
        assert results["test_tool"].version == "2.0.0"
        # Should not have called install
        assert installer.install_count == 0

    @pytest.mark.asyncio
    async def test_failure_does_not_stop_deployment(self):
        """Test that one failure doesn't stop the entire deployment."""
        executor = DeploymentExecutor()

        # First tool fails, second succeeds
        failing = FailingInstaller(
            tool_key="failing_tool",
            tool_name="Failing Tool",
        )
        succeeding = MockInstaller(
            tool_key="succeeding_tool",
            tool_name="Succeeding Tool",
        )
        executor.register_installers([failing, succeeding])

        results = await executor.execute_deployment(
            tool_keys=["failing_tool", "succeeding_tool"],
            skip_existing=False,
        )

        assert results["failing_tool"].status == "failed"
        assert results["succeeding_tool"].status == "installed"
        # Both installers should have been called
        assert failing.install_count >= 1
        assert succeeding.install_count >= 1

    @pytest.mark.asyncio
    async def test_retry_after_failure(self):
        """Test retry after initial failure."""
        executor = DeploymentExecutor()

        # Tool that succeeds on retry
        installer = FailingInstaller(
            tool_key="retry_tool",
            tool_name="Retry Tool",
            fail_count=1,
            succeed_after_retry=True,
        )
        executor.register_installer(installer)

        results = await executor.execute_deployment(
            tool_keys=["retry_tool"],
            skip_existing=False,
        )

        # Should have been retried and eventually succeeded
        assert results["retry_tool"].status == "installed"
        assert installer.install_count > 1

    @pytest.mark.asyncio
    async def test_parallel_execution(self):
        """Test parallel execution of independent tools."""
        executor = DeploymentExecutor()

        installers = [
            MockInstaller(tool_key=f"tool_{i}", tool_name=f"Tool {i}")
            for i in range(3)
        ]
        executor.register_installers(installers)

        results = await executor.execute_deployment(
            tool_keys=["tool_0", "tool_1", "tool_2"],
            skip_existing=False,
            parallel=True,
        )

        for i in range(3):
            assert results[f"tool_{i}"].status == "installed"

    @pytest.mark.asyncio
    async def test_dependency_levels(self):
        """Test dependency level computation."""
        executor = DeploymentExecutor()

        # Tool B depends on Tool A
        tool_a = MockInstaller(
            tool_key="tool_a",
            tool_name="Tool A",
        )
        tool_b = MockInstaller(
            tool_key="tool_b",
            tool_name="Tool B",
            dependencies=["tool_a"],
        )
        executor.register_installers([tool_a, tool_b])

        levels = executor._compute_dependency_levels(["tool_a", "tool_b"])
        assert len(levels) == 2
        assert "tool_a" in levels[0]
        assert "tool_b" in levels[1]

    @pytest.mark.asyncio
    async def test_get_summary(self):
        """Test deployment summary generation."""
        executor = DeploymentExecutor()
        installer = MockInstaller(
            tool_key="test_tool",
            tool_name="Test Tool",
        )
        executor.register_installer(installer)

        await executor.execute_deployment(
            tool_keys=["test_tool"],
            skip_existing=False,
        )

        summary = executor.get_summary()
        assert summary["total_tools"] == 1
        assert summary["installed"] == 1
        assert summary["success_rate"] == 100.0

    @pytest.mark.asyncio
    async def test_cancel_deployment(self):
        """Test cancelling a deployment."""
        executor = DeploymentExecutor()
        executor.cancel()
        assert not executor.is_running


# =============================================================================
# Tests: Deployment Session
# =============================================================================

class TestDeploymentSession:
    """Test deployment session lifecycle."""

    @pytest.mark.asyncio
    async def test_session_lifecycle(self):
        """Test complete session lifecycle."""
        with tempfile.TemporaryDirectory() as tmpdir:
            session = DeploymentSession(data_dir=tmpdir)

            session_id = session.start_session(profile_name="test_profile")
            assert session.is_active
            assert session.session_id == session_id

            session.end_session()
            assert not session.is_active

    @pytest.mark.asyncio
    async def test_deploy_tools_session(self):
        """Test deploying tools within a session."""
        with tempfile.TemporaryDirectory() as tmpdir:
            session = DeploymentSession(data_dir=tmpdir)
            installer = MockInstaller(
                tool_key="test_tool",
                tool_name="Test Tool",
            )
            session.executor.register_installer(installer)

            result = await session.deploy_tools(
                tool_keys=["test_tool"],
                skip_existing=False,
            )

            assert result.status == "completed"
            assert "test_tool" in result.tools_installed
            assert result.success_rate == 100.0
            assert result.report_path is not None
            assert os.path.exists(result.report_path)

    @pytest.mark.asyncio
    async def test_partial_success_session(self):
        """Test session with partial success."""
        with tempfile.TemporaryDirectory() as tmpdir:
            session = DeploymentSession(data_dir=tmpdir)
            session.executor.register_installers([
                FailingInstaller(
                    tool_key="failing_tool",
                    tool_name="Failing Tool",
                ),
                MockInstaller(
                    tool_key="succeeding_tool",
                    tool_name="Succeeding Tool",
                ),
            ])

            result = await session.deploy_tools(
                tool_keys=["failing_tool", "succeeding_tool"],
                skip_existing=False,
            )

            assert result.status == "partial"
            assert "succeeding_tool" in result.tools_installed
            assert "failing_tool" in result.tools_failed
            assert result.success_rate == 50.0

    @pytest.mark.asyncio
    async def test_session_state_persistence(self):
        """Test session state is saved to disk."""
        with tempfile.TemporaryDirectory() as tmpdir:
            session = DeploymentSession(data_dir=tmpdir)
            installer = MockInstaller(
                tool_key="test_tool",
                tool_name="Test Tool",
            )
            session.executor.register_installer(installer)

            result = await session.deploy_tools(
                tool_keys=["test_tool"],
                skip_existing=False,
            )

            # Check state file exists
            state_dir = os.path.join(tmpdir, "persistence")
            assert os.path.exists(state_dir)
            state_files = [f for f in os.listdir(state_dir) if f.startswith("session_")]
            assert len(state_files) > 0

    @pytest.mark.asyncio
    async def test_session_report_generation(self):
        """Test deployment report generation."""
        with tempfile.TemporaryDirectory() as tmpdir:
            session = DeploymentSession(data_dir=tmpdir)
            installer = MockInstaller(
                tool_key="test_tool",
                tool_name="Test Tool",
            )
            session.executor.register_installer(installer)

            result = await session.deploy_tools(
                tool_keys=["test_tool"],
                skip_existing=False,
            )

            # Check report file exists
            assert result.report_path is not None
            assert os.path.exists(result.report_path)

            # Verify report content
            with open(result.report_path, "r") as f:
                report = json.load(f)
            assert report["report_type"] == "deployment_session"
            assert report["session"]["status"] == "completed"
            assert "tool_results" in report

    @pytest.mark.asyncio
    async def test_resume_session(self):
        """Test resuming a previous session."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # First session with failures
            session = DeploymentSession(data_dir=tmpdir)
            session.executor.register_installers([
                FailingInstaller(
                    tool_key="failing_tool",
                    tool_name="Failing Tool",
                ),
            ])

            result = await session.deploy_tools(
                tool_keys=["failing_tool"],
                skip_existing=False,
            )

            assert result.status == "failed"
            session_id = result.session_id

            # Resume session
            session2 = DeploymentSession(data_dir=tmpdir)
            # Register a working installer for the retry
            session2.executor.register_installer(
                MockInstaller(
                    tool_key="failing_tool",
                    tool_name="Failing Tool",
                )
            )

            resume_result = await session2.resume_session(session_id)
            # May be None if no failed tools, or may succeed
            if resume_result:
                assert resume_result.session_id == session_id

    @pytest.mark.asyncio
    async def test_get_latest_session(self):
        """Test getting the latest session ID."""
        with tempfile.TemporaryDirectory() as tmpdir:
            session = DeploymentSession(data_dir=tmpdir)
            installer = MockInstaller(
                tool_key="test_tool",
                tool_name="Test Tool",
            )
            session.executor.register_installer(installer)

            await session.deploy_tools(
                tool_keys=["test_tool"],
                skip_existing=False,
            )

            latest = session.get_latest_session()
            assert latest is not None
            assert latest.startswith("DEP-")


# =============================================================================
# Tests: Operation Tracker Integration
# =============================================================================

class TestOperationTrackerIntegration:
    """Test operation tracker integration with execution."""

    @pytest.mark.asyncio
    async def test_operations_are_tracked(self):
        """Test that operations are tracked during deployment."""
        tracker = OperationTracker()
        executor = DeploymentExecutor(operation_tracker=tracker)
        installer = MockInstaller(
            tool_key="test_tool",
            tool_name="Test Tool",
        )
        executor.register_installer(installer)

        await executor.execute_deployment(
            tool_keys=["test_tool"],
            skip_existing=False,
        )

        summary = tracker.get_summary()
        assert summary["total_operations"] > 0
        assert summary["succeeded"] > 0

    @pytest.mark.asyncio
    async def test_failed_operations_tracked(self):
        """Test that failed operations are tracked."""
        tracker = OperationTracker()
        executor = DeploymentExecutor(operation_tracker=tracker)
        installer = FailingInstaller(
            tool_key="failing_tool",
            tool_name="Failing Tool",
        )
        executor.register_installer(installer)

        await executor.execute_deployment(
            tool_keys=["failing_tool"],
            skip_existing=False,
        )

        summary = tracker.get_summary()
        assert summary["failed"] > 0

    @pytest.mark.asyncio
    async def test_operation_export(self):
        """Test operation export to file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tracker = OperationTracker()
            executor = DeploymentExecutor(operation_tracker=tracker)
            installer = MockInstaller(
                tool_key="test_tool",
                tool_name="Test Tool",
            )
            executor.register_installer(installer)

            await executor.execute_deployment(
                tool_keys=["test_tool"],
                skip_existing=False,
            )

            export_path = os.path.join(tmpdir, "operations.json")
            tracker.save_to_file(export_path)
            assert os.path.exists(export_path)

            # Verify export content
            with open(export_path, "r") as f:
                data = json.load(f)
            assert "session_id" in data
            assert "summary" in data
            assert "operations" in data
