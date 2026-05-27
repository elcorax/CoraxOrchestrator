"""
Tests for the Environment Analyzer module.
"""

import pytest
from src.modules.environment_analyzer import EnvironmentAnalyzer, EnvironmentAnalysis, ToolStatus
from src.modules.system_scanner import ScanResult, HardwareSpecs, SoftwareInventory


class TestEnvironmentAnalyzer:
    """Test suite for EnvironmentAnalyzer."""

    def test_analyze_returns_analysis(self):
        """Test that analyze() returns an EnvironmentAnalysis."""
        scan_result = ScanResult()
        analyzer = EnvironmentAnalyzer()
        analysis = analyzer.analyze(scan_result)
        assert isinstance(analysis, EnvironmentAnalysis)

    def test_analysis_has_score(self):
        """Test that analysis includes a readiness score."""
        scan_result = ScanResult()
        analyzer = EnvironmentAnalyzer()
        analysis = analyzer.analyze(scan_result)
        assert 0 <= analysis.score <= 100

    def test_analysis_to_dict(self):
        """Test EnvironmentAnalysis serialization."""
        analysis = EnvironmentAnalysis()
        data = analysis.to_dict()
        assert "system_ready" in data
        assert "hardware_compatible" in data
        assert "hardware_issues" in data
        assert "tools" in data
        assert "missing_tools" in data
        assert "score" in data

    def test_tool_status_to_dict(self):
        """Test ToolStatus serialization."""
        status = ToolStatus(
            name="python",
            installed=True,
            version="3.11.0",
            compatible=True,
            status_message="Installed",
        )
        data = status.to_dict()
        assert data["name"] == "python"
        assert data["installed"] is True
        assert data["version"] == "3.11.0"

    def test_get_last_analysis_none_initially(self):
        """Test that get_last_analysis returns None before analysis."""
        analyzer = EnvironmentAnalyzer()
        assert analyzer.get_last_analysis() is None

    def test_analysis_with_hardware_issues(self):
        """Test analysis with insufficient hardware."""
        scan_result = ScanResult()
        scan_result.hardware.memory = {"total_gb": 8}  # Below 16 GB minimum
        scan_result.hardware.disks = [{"free_gb": 20}]  # Below 50 GB minimum
        scan_result.hardware.cpu = {"cores": 2}  # Below 4 cores minimum

        analyzer = EnvironmentAnalyzer()
        analysis = analyzer.analyze(scan_result)

        assert len(analysis.hardware_issues) > 0
        assert analysis.hardware_compatible is False
        assert analysis.score < 100
