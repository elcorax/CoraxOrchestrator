"""
Tests for the exception hierarchy.
"""

import pytest
from src.core.exceptions import (
    CoraxError,
    ConfigurationError,
    DetectionError,
    InstallationError,
    PermissionError,
    ModelError,
    PersistenceError,
    PlatformError,
    RecoveryError,
)


class TestExceptions:
    """Test suite for custom exceptions."""

    def test_corax_error_base(self):
        """Test base CoraxError."""
        error = CoraxError("Test error")
        assert str(error) == "Test error"
        assert error.code == "UNKNOWN_ERROR"
        assert error.recoverable is False

    def test_corax_error_with_code(self):
        """Test CoraxError with explicit code."""
        error = CoraxError("Test error", code="CUSTOM_CODE")
        assert error.code == "CUSTOM_CODE"

    def test_corax_error_recoverable(self):
        """Test CoraxError with recoverable flag."""
        error = CoraxError("Test error", recoverable=True)
        assert error.recoverable is True

    def test_configuration_error(self):
        """Test ConfigurationError."""
        error = ConfigurationError("Bad config", config_key="test_key")
        assert error.code == "CONFIG_ERROR"
        assert error.details["config_key"] == "test_key"

    def test_detection_error(self):
        """Test DetectionError."""
        error = DetectionError("Detection failed", target="gpu")
        assert error.code == "DETECTION_ERROR"
        assert error.details["target"] == "gpu"

    def test_installation_error(self):
        """Test InstallationError."""
        error = InstallationError("Install failed", tool_name="ollama")
        assert error.code == "INSTALL_ERROR"
        assert error.details["tool_name"] == "ollama"

    def test_permission_error(self):
        """Test PermissionError."""
        error = PermissionError(
            "Access denied",
            required_privilege="admin",
        )
        assert error.code == "PERMISSION_ERROR"
        assert error.details["required_privilege"] == "admin"

    def test_model_error(self):
        """Test ModelError."""
        error = ModelError(
            "Model not found",
            model_name="llama3.2",
            provider="ollama",
        )
        assert error.code == "MODEL_ERROR"
        assert error.details["model_name"] == "llama3.2"
        assert error.details["provider"] == "ollama"

    def test_persistence_error(self):
        """Test PersistenceError."""
        error = PersistenceError(
            "Write failed",
            store="/tmp/store",
            operation="write",
        )
        assert error.code == "PERSISTENCE_ERROR"
        assert error.details["store"] == "/tmp/store"
        assert error.details["operation"] == "write"

    def test_platform_error(self):
        """Test PlatformError."""
        error = PlatformError(
            "Unsupported platform",
            platform="unknown",
            operation="detect",
        )
        assert error.code == "PLATFORM_ERROR"
        assert error.details["platform"] == "unknown"
        assert error.details["operation"] == "detect"

    def test_recovery_error(self):
        """Test RecoveryError."""
        original = CoraxError("Original error")
        error = RecoveryError(
            "Recovery failed",
            original_error=original,
            recovery_attempts=3,
        )
        assert error.code == "RECOVERY_ERROR"
        assert error.details["original_error"] == str(original)
        assert error.details["recovery_attempts"] == 3

    def test_error_hierarchy(self):
        """Test that all errors inherit from CoraxError."""
        errors = [
            ConfigurationError("test"),
            DetectionError("test"),
            InstallationError("test"),
            PermissionError("test"),
            ModelError("test"),
            PersistenceError("test"),
            PlatformError("test"),
            RecoveryError("test"),
        ]
        for error in errors:
            assert isinstance(error, CoraxError)

    def test_error_to_dict(self):
        """Test serialization to dictionary."""
        error = CoraxError("Test error", code="TEST", details={"key": "val"}, recoverable=True)
        d = error.to_dict()
        assert d["error"] == "CoraxError"
        assert d["code"] == "TEST"
        assert d["message"] == "Test error"
        assert d["details"]["key"] == "val"
        assert d["recoverable"] is True
