"""
Corax Orchestrator — Support Bundle Exporter Module.

Creates diagnostic support bundles for troubleshooting:
- System information collection (OS, hardware, environment)
- Log file aggregation from all Corax components
- Configuration snapshot (sanitized)
- Deployment history and failure records
- Network diagnostics
- Environment hardening results inclusion
- Archive creation for easy sharing
"""

from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field
from datetime import datetime, timezone
import glob
import json
import os
import platform
import shutil
import subprocess
import tempfile
import zipfile

from src.core.logging import get_logger

logger = get_logger(__name__)


@dataclass
class SupportBundleResult:
    """Result of a support bundle creation operation."""
    success: bool = False
    bundle_path: Optional[str] = None
    bundle_size_bytes: Optional[int] = None
    included_files: int = 0
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "bundle_path": self.bundle_path,
            "bundle_size_bytes": self.bundle_size_bytes,
            "bundle_size_mb": round(self.bundle_size_bytes / (1024 * 1024), 2)
                if self.bundle_size_bytes else None,
            "included_files": self.included_files,
            "errors": self.errors,
            "warnings": self.warnings,
            "timestamp": self.timestamp,
        }


class SupportBundleExporter:
    """
    Creates comprehensive support bundles for debugging deployment issues.

    Collects system info, logs, configs, and diagnostics into a
    compressed archive for sharing with support teams.
    """

    def __init__(self, output_dir: Optional[str] = None):
        self._output_dir = output_dir or os.path.join(
            tempfile.gettempdir(), "corax_support_bundles"
        )
        os.makedirs(self._output_dir, exist_ok=True)

    def create_bundle(
        self,
        include_logs: bool = True,
        include_config: bool = True,
        include_system_info: bool = True,
        include_deployment_history: bool = True,
        include_network_diags: bool = False,
        include_hardening_results: Optional[List[Dict[str, Any]]] = None,
        max_log_size_mb: int = 50,
        custom_data: Optional[Dict[str, Any]] = None,
    ) -> SupportBundleResult:
        """
        Create a support bundle archive.

        Args:
            include_logs: Include Corax log files
            include_config: Include configuration snapshot (sanitized)
            include_system_info: Include system information
            include_deployment_history: Include deployment history
            include_network_diags: Include network diagnostics
            include_hardening_results: Include environment hardening results
            max_log_size_mb: Maximum total log size to include
            custom_data: Additional data to include

        Returns:
            SupportBundleResult with bundle path and metadata
        """
        result = SupportBundleResult()
        bundle_name = (
            f"corax_support_bundle_"
            f"{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
        )
        work_dir = os.path.join(self._output_dir, bundle_name)
        os.makedirs(work_dir, exist_ok=True)

        try:
            files_added = 0

            # System information
            if include_system_info:
                sys_info_path = self._collect_system_info(work_dir)
                if sys_info_path:
                    files_added += 1

            # Log files
            if include_logs:
                log_count = self._collect_logs(work_dir, max_log_size_mb)
                files_added += log_count

            # Configuration snapshot
            if include_config:
                config_path = self._collect_config(work_dir)
                if config_path:
                    files_added += 1

            # Deployment history
            if include_deployment_history:
                history_path = self._collect_deployment_history(work_dir)
                if history_path:
                    files_added += 1

            # Network diagnostics
            if include_network_diags:
                net_path = self._collect_network_diagnostics(work_dir)
                if net_path:
                    files_added += 1

            # Hardening results
            if include_hardening_results:
                hard_path = self._save_hardening_results(
                    work_dir, include_hardening_results
                )
                if hard_path:
                    files_added += 1

            # Custom data
            if custom_data:
                custom_path = os.path.join(work_dir, "custom_data.json")
                with open(custom_path, "w", encoding="utf-8") as f:
                    json.dump(custom_data, f, indent=2, default=str)
                files_added += 1

            # Create archive
            archive_path = shutil.make_archive(
                base_name=os.path.join(self._output_dir, bundle_name),
                format="zip",
                root_dir=work_dir,
            )

            # Clean up working directory
            shutil.rmtree(work_dir, ignore_errors=True)

            # Get result metadata
            result.success = True
            result.bundle_path = archive_path
            result.bundle_size_bytes = os.path.getsize(archive_path)
            result.included_files = files_added

            logger.info(
                f"Support bundle created: {archive_path}",
                size_mb=round(result.bundle_size_bytes / (1024 * 1024), 2),
                files=files_added,
            )

        except Exception as e:
            result.errors.append(f"Failed to create support bundle: {e}")
            logger.error(f"Support bundle creation failed: {e}")

        return result

    def _collect_system_info(self, work_dir: str) -> Optional[str]:
        """Collect system information into a JSON file."""
        try:
            info = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "platform": {
                    "system": platform.system(),
                    "release": platform.release(),
                    "version": platform.version(),
                    "architecture": platform.machine(),
                    "processor": platform.processor(),
                    "hostname": platform.node(),
                },
                "python": {
                    "version": platform.python_version(),
                    "implementation": platform.python_implementation(),
                    "compiler": platform.python_compiler(),
                    "executable": os.environ.get("PYTHON_EXECUTABLE", ""),
                },
                "environment": {
                    "cwd": os.getcwd(),
                    "user": os.environ.get("USERNAME", ""),
                    "computer_name": os.environ.get("COMPUTERNAME", ""),
                    "os": os.environ.get("OS", ""),
                    "processor_architecture": os.environ.get(
                        "PROCESSOR_ARCHITECTURE", ""
                    ),
                    "number_of_processors": os.environ.get(
                        "NUMBER_OF_PROCESSORS", ""
                    ),
                },
            }

            # Add disk usage
            try:
                usage = shutil.disk_usage(os.getcwd())
                info["disk"] = {
                    "total_gb": round(usage.total / (1024 ** 3), 2),
                    "used_gb": round(usage.used / (1024 ** 3), 2),
                    "free_gb": round(usage.free / (1024 ** 3), 2),
                }
            except Exception:
                pass

            # Add memory info
            try:
                import psutil
                mem = psutil.virtual_memory()
                info["memory"] = {
                    "total_gb": round(mem.total / (1024 ** 3), 2),
                    "available_gb": round(mem.available / (1024 ** 3), 2),
                    "percent_used": mem.percent,
                }
            except ImportError:
                pass

            filepath = os.path.join(work_dir, "system_info.json")
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(info, f, indent=2, default=str)

            return filepath

        except Exception as e:
            logger.debug(f"Failed to collect system info: {e}")
            return None

    def _collect_logs(
        self, work_dir: str, max_size_mb: int = 50
    ) -> int:
        """Collect Corax log files."""
        log_dir = os.path.join(os.getcwd(), "logs")
        if not os.path.isdir(log_dir):
            # Try common log locations
            for candidate in [
                os.path.join(os.getcwd(), "..", "logs"),
                os.path.join(os.environ.get("LOCALAPPDATA", ""), "Corax", "logs"),
                os.path.join(os.environ.get("PROGRAMDATA", ""), "Corax", "logs"),
            ]:
                if os.path.isdir(candidate):
                    log_dir = candidate
                    break
            else:
                logger.debug("No log directory found")
                return 0

        log_output = os.path.join(work_dir, "logs")
        os.makedirs(log_output, exist_ok=True)

        count = 0
        total_size = 0
        max_bytes = max_size_mb * 1024 * 1024

        try:
            for filepath in sorted(glob.glob(os.path.join(log_dir, "*.log*"))):
                if total_size >= max_bytes:
                    break

                filename = os.path.basename(filepath)
                dest = os.path.join(log_output, filename)

                try:
                    file_size = os.path.getsize(filepath)
                    if total_size + file_size > max_bytes:
                        # Truncate if too large
                        self._copy_truncated(filepath, dest, max_bytes - total_size)
                        total_size = max_bytes
                    else:
                        shutil.copy2(filepath, dest)
                        total_size += file_size
                    count += 1
                except (OSError, IOError) as e:
                    logger.debug(f"Failed to copy log {filename}: {e}")

        except Exception as e:
            logger.debug(f"Log collection error: {e}")

        return count

    def _copy_truncated(
        self, src: str, dest: str, max_bytes: int
    ) -> None:
        """Copy a file but truncate to max_bytes from the end."""
        try:
            with open(src, "rb") as f_in:
                f_in.seek(-min(max_bytes, os.path.getsize(src)), os.SEEK_END)
                with open(dest, "wb") as f_out:
                    f_out.write(f_in.read())
        except (OSError, IOError) as e:
            logger.debug(f"Failed to truncate-copy log: {e}")

    def _collect_config(self, work_dir: str) -> Optional[str]:
        """Collect configuration files, sanitizing sensitive values."""
        config_dirs = [
            os.path.join(os.getcwd(), "config"),
            os.path.join(os.getcwd(), "..", "config"),
        ]

        config_output = os.path.join(work_dir, "config")
        os.makedirs(config_output, exist_ok=True)

        collected = False

        for config_dir in config_dirs:
            if not os.path.isdir(config_dir):
                continue

            try:
                for filepath in glob.glob(os.path.join(config_dir, "*.json")):
                    filename = os.path.basename(filepath)
                    dest = os.path.join(config_output, filename)

                    try:
                        with open(filepath, "r", encoding="utf-8") as f:
                            data = json.load(f)

                        # Sanitize sensitive values
                        sanitized = self._sanitize_config(data)

                        with open(dest, "w", encoding="utf-8") as f:
                            json.dump(sanitized, f, indent=2, default=str)

                        collected = True

                    except (json.JSONDecodeError, IOError) as e:
                        # Copy as-is if not JSON
                        try:
                            shutil.copy2(filepath, dest)
                            collected = True
                        except (OSError, IOError):
                            pass

            except Exception as e:
                logger.debug(f"Config collection error: {e}")

        if not collected:
            # Create a config manifest
            manifest = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "note": "No configuration files were found",
                "config_dirs_checked": config_dirs,
            }
            manifest_path = os.path.join(config_output, "config_manifest.json")
            with open(manifest_path, "w", encoding="utf-8") as f:
                json.dump(manifest, f, indent=2)
            return manifest_path

        return config_output

    def _sanitize_config(self, data: Any, depth: int = 0) -> Any:
        """Sanitize sensitive configuration values."""
        if depth > 10:
            return data

        SENSITIVE_KEYS = {
            "password", "passwd", "secret", "token", "api_key", "apikey",
            "api_secret", "access_key", "private_key", "auth_token",
            "connection_string", "ssh_key", "encryption_key",
        }

        if isinstance(data, dict):
            sanitized = {}
            for key, value in data.items():
                if any(s in key.lower() for s in SENSITIVE_KEYS):
                    sanitized[key] = "***REDACTED***"
                else:
                    sanitized[key] = self._sanitize_config(value, depth + 1)
            return sanitized
        elif isinstance(data, list):
            return [
                self._sanitize_config(item, depth + 1) for item in data
            ]
        else:
            return data

    def _collect_deployment_history(self, work_dir: str) -> Optional[str]:
        """Collect deployment history records."""
        history_path = os.path.join(
            os.getcwd(), "data", "deployment_history.json"
        )
        alt_path = os.path.join(
            os.environ.get("LOCALAPPDATA", ""),
            "Corax", "data", "deployment_history.json"
        )

        for path in [history_path, alt_path]:
            if os.path.isfile(path):
                try:
                    dest = os.path.join(work_dir, "deployment_history.json")
                    shutil.copy2(path, dest)
                    return dest
                except (OSError, IOError) as e:
                    logger.debug(f"Failed to copy deployment history: {e}")

        # Create a placeholder if no history exists
        placeholder = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "note": "No deployment history file found",
            "paths_checked": [history_path, alt_path],
        }
        placeholder_path = os.path.join(
            work_dir, "deployment_history_placeholder.json"
        )
        with open(placeholder_path, "w", encoding="utf-8") as f:
            json.dump(placeholder, f, indent=2)

        return placeholder_path

    def _collect_network_diagnostics(self, work_dir: str) -> Optional[str]:
        """Collect network diagnostic information."""
        net_output = os.path.join(work_dir, "network_diagnostics")
        os.makedirs(net_output, exist_ok=True)
        count = 0

        try:
            # DNS resolution test
            import socket
            hosts_to_test = [
                "google.com",
                "github.com",
                "huggingface.co",
                "pypi.org",
                "ollama.ai",
            ]

            dns_results = {}
            for host in hosts_to_test:
                try:
                    ip = socket.gethostbyname(host)
                    dns_results[host] = {"resolved": True, "ip": ip}
                except socket.gaierror:
                    dns_results[host] = {"resolved": False, "error": "DNS resolution failed"}

            dns_path = os.path.join(net_output, "dns_resolution.json")
            with open(dns_path, "w", encoding="utf-8") as f:
                json.dump(dns_results, f, indent=2)
            count += 1

        except Exception as e:
            logger.debug(f"DNS diagnostics failed: {e}")

        try:
            # Network config
            if platform.system() == "Windows":
                proc = subprocess.run(
                    ["ipconfig", "/all"],
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                if proc.returncode == 0:
                    path = os.path.join(net_output, "ipconfig.txt")
                    with open(path, "w", encoding="utf-8") as f:
                        f.write(proc.stdout)
                    count += 1
            else:
                proc = subprocess.run(
                    ["ifconfig"],
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                if proc.returncode == 0:
                    path = os.path.join(net_output, "ifconfig.txt")
                    with open(path, "w", encoding="utf-8") as f:
                        f.write(proc.stdout)
                    count += 1
        except Exception as e:
            logger.debug(f"Network config collection failed: {e}")

        try:
            # Routing table
            if platform.system() == "Windows":
                proc = subprocess.run(
                    ["route", "print"],
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
            else:
                proc = subprocess.run(
                    ["netstat", "-rn"],
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
            if proc.returncode == 0:
                path = os.path.join(net_output, "routing_table.txt")
                with open(path, "w", encoding="utf-8") as f:
                    f.write(proc.stdout)
                count += 1
        except Exception as e:
            logger.debug(f"Routing table collection failed: {e}")

        try:
            # Active connections
            if platform.system() == "Windows":
                proc = subprocess.run(
                    ["netstat", "-ano"],
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
            else:
                proc = subprocess.run(
                    ["netstat", "-tuln"],
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
            if proc.returncode == 0:
                path = os.path.join(net_output, "active_connections.txt")
                with open(path, "w", encoding="utf-8") as f:
                    f.write(proc.stdout)
                count += 1
        except Exception as e:
            logger.debug(f"Active connections collection failed: {e}")

        return net_output if count > 0 else None

    def _save_hardening_results(
        self,
        work_dir: str,
        hardening_results: List[Dict[str, Any]],
    ) -> Optional[str]:
        """Save environment hardening results into the bundle."""
        path = os.path.join(work_dir, "environment_hardening_results.json")
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(hardening_results, f, indent=2, default=str)
            return path
        except Exception as e:
            logger.debug(f"Failed to save hardening results: {e}")
            return None

    def list_bundles(self) -> List[Dict[str, Any]]:
        """List existing support bundles in the output directory."""
        bundles = []
        for filepath in sorted(
            glob.glob(os.path.join(self._output_dir, "*.zip")),
            key=os.path.getmtime,
            reverse=True,
        ):
            bundles.append({
                "path": filepath,
                "filename": os.path.basename(filepath),
                "size_bytes": os.path.getsize(filepath),
                "size_mb": round(os.path.getsize(filepath) / (1024 * 1024), 2),
                "created": datetime.fromtimestamp(
                    os.path.getmtime(filepath), tz=timezone.utc
                ).isoformat(),
            })
        return bundles

    def clean_old_bundles(self, max_age_days: int = 7) -> int:
        """Remove support bundles older than max_age_days."""
        count = 0
        cutoff = datetime.now(timezone.utc).timestamp() - (max_age_days * 86400)

        for filepath in glob.glob(os.path.join(self._output_dir, "*.zip")):
            try:
                if os.path.getmtime(filepath) < cutoff:
                    os.remove(filepath)
                    count += 1
            except OSError as e:
                logger.debug(f"Failed to clean bundle {filepath}: {e}")

        return count
