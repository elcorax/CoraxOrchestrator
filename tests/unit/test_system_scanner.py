"""
Tests for the System Scanner module.
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from src.modules.system_scanner import SystemScanner, ScanResult, HardwareSpecs, SoftwareInventory


class TestSystemScanner:
    """Test suite for SystemScanner."""

    @pytest.mark.asyncio
    async def test_scan_returns_scan_result(self):
        """Test that scan() returns a ScanResult."""
        scanner = SystemScanner()
        with patch.object(scanner, '_scan_hardware', return_value=HardwareSpecs()):
            with patch.object(scanner, '_scan_software', return_value=SoftwareInventory()):
                result = await scanner.scan()
                assert isinstance(result, ScanResult)

    @pytest.mark.asyncio
    async def test_scan_includes_timestamp(self):
        """Test that scan result includes a timestamp."""
        scanner = SystemScanner()
        with patch.object(scanner, '_scan_hardware', return_value=HardwareSpecs()):
            with patch.object(scanner, '_scan_software', return_value=SoftwareInventory()):
                result = await scanner.scan()
                assert result.timestamp is not None

    def test_scan_result_to_dict(self):
        """Test ScanResult serialization."""
        result = ScanResult()
        data = result.to_dict()
        assert "timestamp" in data
        assert "platform" in data
        assert "hardware" in data
        assert "software" in data
        assert "errors" in data

    def test_hardware_specs_defaults(self):
        """Test HardwareSpecs default values."""
        specs = HardwareSpecs()
        assert specs.cpu == {}
        assert specs.memory == {}
        assert specs.disks == []
        assert specs.gpus == []
        assert specs.network == {}

    def test_software_inventory_defaults(self):
        """Test SoftwareInventory default values."""
        inventory = SoftwareInventory()
        assert inventory.operating_system == {}
        assert inventory.installed_applications == []
        assert inventory.development_tools == {}
        assert inventory.package_managers == []
        assert inventory.runtimes == {}

    def test_get_last_result_none_initially(self):
        """Test that get_last_result returns None before scan."""
        scanner = SystemScanner()
        assert scanner.get_last_result() is None
