"""
Corax Orchestrator — AI Stack Resilience Manager.

Provides lifecycle management and health monitoring for AI services:
- Service health checks with timeout and retry
- Automatic restart of failed AI services
- Resource monitoring (memory, GPU, disk)
- Graceful shutdown and startup sequencing
- Health status reporting for operational visibility
"""

from typing import Dict, Any, List, Optional, Callable, Awaitable
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
import json
import os
import platform
import subprocess
import time

from src.core.logging import get_logger

logger = get_logger(__name__)


@dataclass
class ServiceHealth:
    """Health status of an AI service."""
    service_name: str
    running: bool
    pid: Optional[int] = None
    port: Optional[int] = None
    memory_mb: Optional[float] = None
    cpu_percent: Optional[float] = None
    uptime_seconds: Optional[float] = None
    last_check: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    errors: List[str] = field(default_factory=list)
    healthy: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "service_name": self.service_name,
            "running": self.running,
            "pid": self.pid,
            "port": self.port,
            "memory_mb": round(self.memory_mb, 2) if self.memory_mb else None,
            "cpu_percent": round(self.cpu_percent, 2) if self.cpu_percent else None,
            "uptime_seconds": round(self.uptime_seconds, 2) if self.uptime_seconds else None,
            "last_check": self.last_check,
            "errors": self.errors,
            "healthy": self.healthy,
        }


@dataclass
class AIResilienceResult:
    """Result from an AI resilience operation."""
    success: bool = False
    operation: str = ""
    service_name: str = ""
    details: Dict[str, Any] = field(default_factory=dict)
    errors: List[str] = field(default_factory=list)
    duration_ms: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "operation": self.operation,
            "service_name": self.service_name,
            "details": self.details,
            "errors": self.errors,
            "duration_ms": round(self.duration_ms, 2),
        }


class AIResilienceManager:
    """
    Manages the lifecycle and health of AI services.

    Supports:
    - Ollama (local LLM server)
    - LM Studio (local model server)
    - ComfyUI (image generation workflow)
    - AnythingLLM (document-aware chat)
    - Open WebUI (web interface for LLMs)
    - Docker containers running AI services
    """

    # Service definitions: name -> (health check command, start command, port)
    SERVICES: Dict[str, Dict[str, Any]] = {
        "ollama": {
            "health_cmd": ["ollama", "list"],
            "start_cmd": ["ollama", "serve"],
            "port": 11434,
            "process_name": "ollama",
            "max_restart_attempts": 3,
            "health_check_timeout": 15,
            "startup_timeout": 60,
            "health_endpoint": "http://localhost:11434/api/tags",
        },
        "lm_studio": {
            "health_cmd": None,  # LM Studio is GUI-based; check port
            "start_cmd": None,
            "port": 1234,
            "process_name": "LM Studio",
            "max_restart_attempts": 1,
            "health_check_timeout": 10,
            "startup_timeout": 120,
            "health_endpoint": "http://localhost:1234/v1/models",
        },
        "comfyui": {
            "health_cmd": None,
            "start_cmd": None,
            "port": 8188,
            "process_name": "ComfyUI",
            "max_restart_attempts": 2,
            "health_check_timeout": 15,
            "startup_timeout": 90,
            "health_endpoint": "http://localhost:8188/api/v1/status",
        },
        "open_webui": {
            "health_cmd": None,
            "start_cmd": None,
            "port": 3000,
            "process_name": "open-webui",
            "max_restart_attempts": 2,
            "health_check_timeout": 15,
            "startup_timeout": 60,
            "health_endpoint": "http://localhost:3000/health",
        },
        "anythingllm": {
            "health_cmd": None,
            "start_cmd": None,
            "port": 3001,
            "process_name": "anythingllm",
            "max_restart_attempts": 2,
            "health_check_timeout": 15,
            "startup_timeout": 60,
            "health_endpoint": "http://localhost:3001/api/health",
        },
    }

    def __init__(self):
        self._health_cache: Dict[str, ServiceHealth] = {}
        self._restart_counts: Dict[str, int] = {}
        self._start_times: Dict[str, datetime] = {}

    def check_service_health(
        self, service_name: str, use_cache: bool = True
    ) -> ServiceHealth:
        """
        Check the health of an AI service.

        Args:
            service_name: Name of the service (e.g., 'ollama', 'comfyui')
            use_cache: Whether to use a cached result (within 30 seconds)

        Returns:
            ServiceHealth with current status
        """
        # Use cached result if recent
        if use_cache and service_name in self._health_cache:
            cached = self._health_cache[service_name]
            last = cached.last_check
            if isinstance(last, str):
                try:
                    last_dt = datetime.fromisoformat(last)
                    if (datetime.now(timezone.utc) - last_dt).total_seconds() < 30:
                        return cached
                except ValueError:
                    pass

        service_config = self.SERVICES.get(service_name)
        if not service_config:
            return ServiceHealth(
                service_name=service_name,
                running=False,
                healthy=False,
                errors=[f"Unknown service: {service_name}"],
            )

        health = self._perform_health_check(service_name, service_config)
        self._health_cache[service_name] = health
        return health

    def _perform_health_check(
        self, service_name: str, config: Dict[str, Any]
    ) -> ServiceHealth:
        """Perform the actual health check for a service."""
        health = ServiceHealth(service_name=service_name, running=False)

        # 1. Check if the process is running
        pid = self._find_process(config.get("process_name", service_name))
        if pid:
            health.running = True
            health.pid = pid

        # 2. Check if the port is listening
        port = config.get("port")
        if port:
            health.port = port
            port_open = self._check_port(port)
            if port_open and not health.running:
                # Process might be running under a different name
                health.running = True

        # 3. Try the health endpoint if available
        endpoint = config.get("health_endpoint")
        endpoint_ok = False
        if endpoint and health.running:
            endpoint_ok = self._check_endpoint(endpoint, config.get("health_check_timeout", 10))

        # 4. Try the CLI health command if available
        cmd = config.get("health_cmd")
        cmd_ok = False
        if cmd and health.running:
            cmd_ok = self._run_health_command(cmd, config.get("health_check_timeout", 10))

        # 5. Get resource usage if psutil is available
        if health.running and health.pid:
            mem, cpu, uptime = self._get_process_stats(health.pid)
            health.memory_mb = mem
            health.cpu_percent = cpu
            health.uptime_seconds = uptime

        # Determine overall health
        if config.get("health_cmd") or config.get("health_endpoint"):
            # If we have an explicit health check, use it
            if cmd is not None:
                health.healthy = cmd_ok
            elif endpoint is not None:
                health.healthy = endpoint_ok
            else:
                health.healthy = health.running
        else:
            # Without explicit check, running on port is sufficient
            if port:
                health.healthy = self._check_port(port)
            else:
                health.healthy = health.running

        if not health.healthy and health.running:
            health.errors.append(
                f"Service {service_name} is running but not responding to health checks"
            )

        return health

    def _find_process(self, process_name: str) -> Optional[int]:
        """Find a process by name, return PID or None."""
        if platform.system() == "Windows":
            try:
                proc = subprocess.run(
                    ["tasklist", "/FI", f"IMAGENAME eq {process_name}.exe", "/FO", "CSV", "/NH"],
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
                if proc.returncode == 0 and proc.stdout.strip():
                    # Parse CSV: "image","pid",...
                    lines = proc.stdout.strip().splitlines()
                    for line in lines:
                        parts = line.split(",")
                        if len(parts) >= 2:
                            try:
                                pid = int(parts[1].strip().strip('"'))
                                return pid
                            except ValueError:
                                continue
            except (subprocess.TimeoutExpired, OSError) as e:
                logger.debug(f"Failed to find process {process_name}: {e}")

        # Unix-like (including WSL)
        try:
            proc = subprocess.run(
                ["pgrep", "-x", process_name],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if proc.returncode == 0 and proc.stdout.strip():
                return int(proc.stdout.strip().splitlines()[0])
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
            pass

        return None

    def _check_port(self, port: int) -> bool:
        """Check if a port is open by attempting a socket connection."""
        try:
            import socket
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(3)
            result = sock.connect_ex(("127.0.0.1", port))
            sock.close()
            return result == 0
        except Exception:
            return False

    def _check_endpoint(
        self, url: str, timeout: int = 10
    ) -> bool:
        """Check if an HTTP endpoint is responding."""
        try:
            import urllib.request
            req = urllib.request.Request(url, method="GET")
            resp = urllib.request.urlopen(req, timeout=timeout)
            return resp.status < 500
        except Exception:
            return False

    def _run_health_command(
        self, cmd: List[str], timeout: int = 10
    ) -> bool:
        """Run a health check command and return True on success."""
        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            return proc.returncode == 0
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
            return False

    def _get_process_stats(
        self, pid: int
    ) -> tuple:
        """Get memory, CPU, and uptime for a process."""
        mem_mb = None
        cpu_percent = None
        uptime_seconds = None

        try:
            import psutil
            try:
                proc = psutil.Process(pid)
                mem_mb = proc.memory_info().rss / (1024 * 1024)
                cpu_percent = proc.cpu_percent(interval=0.1)
                create_time = proc.create_time()
                uptime_seconds = time.time() - create_time
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
        except ImportError:
            pass

        return mem_mb, cpu_percent, uptime_seconds

    def check_all_services(
        self, service_names: Optional[List[str]] = None
    ) -> Dict[str, ServiceHealth]:
        """
        Check health of all (or specified) AI services.

        Args:
            service_names: List of services to check, or None for all

        Returns:
            Dict mapping service name to ServiceHealth
        """
        names = service_names or list(self.SERVICES.keys())
        results = {}
        for name in names:
            results[name] = self.check_service_health(name)
        return results

    def get_healthy_services(
        self, service_names: Optional[List[str]] = None
    ) -> List[str]:
        """Get list of services that are currently healthy."""
        healths = self.check_all_services(service_names)
        return [name for name, h in healths.items() if h.healthy]

    def get_unhealthy_services(
        self, service_names: Optional[List[str]] = None
    ) -> List[str]:
        """Get list of services that are unhealthy."""
        healths = self.check_all_services(service_names)
        return [name for name, h in healths.items() if not h.healthy]

    def restart_service(self, service_name: str) -> AIResilienceResult:
        """
        Attempt to restart an AI service.

        Returns:
            AIResilienceResult with restart outcome
        """
        start = time.time()
        result = AIResilienceResult(
            operation="restart",
            service_name=service_name,
        )

        service_config = self.SERVICES.get(service_name)
        if not service_config:
            result.errors.append(f"Unknown service: {service_name}")
            result.duration_ms = (time.time() - start) * 1000
            return result

        # Check restart limits
        max_restarts = service_config.get("max_restart_attempts", 3)
        current_restarts = self._restart_counts.get(service_name, 0)
        if current_restarts >= max_restarts:
            result.errors.append(
                f"Max restart attempts ({max_restarts}) reached for {service_name}"
            )
            result.duration_ms = (time.time() - start) * 1000
            return result

        logger.info(
            f"Restarting AI service: {service_name} "
            f"(attempt {current_restarts + 1}/{max_restarts})"
        )

        try:
            # Kill existing process
            self._kill_service(service_name, service_config)

            # Start the service
            start_cmd = service_config.get("start_cmd")
            if start_cmd:
                self._start_service(service_name, start_cmd)

            # Wait for service to become healthy
            startup_timeout = service_config.get("startup_timeout", 60)
            healthy = self._wait_for_healthy(
                service_name, timeout=startup_timeout
            )

            if healthy:
                result.success = True
                result.details = {
                    "startup_timeout": startup_timeout,
                    "restart_attempt": current_restarts + 1,
                }
                logger.info(f"AI service {service_name} restarted successfully")
            else:
                result.errors.append(
                    f"Service {service_name} did not become healthy within "
                    f"{startup_timeout}s"
                )

        except Exception as e:
            result.errors.append(f"Restart failed: {e}")
            logger.error(f"Failed to restart AI service {service_name}: {e}")

        self._restart_counts[service_name] = current_restarts + 1
        result.duration_ms = (time.time() - start) * 1000
        return result

    def _kill_service(
        self, service_name: str, config: Dict[str, Any]
    ) -> None:
        """Kill a running service process."""
        process_name = config.get("process_name", service_name)

        if platform.system() == "Windows":
            try:
                subprocess.run(
                    ["taskkill", "/F", "/IM", f"{process_name}.exe"],
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
            except subprocess.TimeoutExpired:
                pass
        else:
            try:
                subprocess.run(
                    ["pkill", "-x", process_name],
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
            except (subprocess.TimeoutExpired, FileNotFoundError):
                pass

        # Also kill any process on the service's port
        port = config.get("port")
        if port and platform.system() == "Windows":
            try:
                proc = subprocess.run(
                    ["netstat", "-ano", "|", "findstr", f":{port}"],
                    capture_output=True,
                    text=True,
                    timeout=10,
                    shell=True,
                )
                if proc.stdout:
                    for line in proc.stdout.splitlines():
                        parts = line.strip().split()
                        if len(parts) >= 5 and "LISTENING" in line:
                            try:
                                pid = int(parts[4])
                                subprocess.run(
                                    ["taskkill", "/F", "/PID", str(pid)],
                                    capture_output=True,
                                    text=True,
                                    timeout=10,
                                )
                            except (ValueError, subprocess.TimeoutExpired):
                                pass
            except Exception:
                pass

        time.sleep(2)  # Allow process to fully terminate

    def _start_service(
        self, service_name: str, start_cmd: List[str]
    ) -> None:
        """Start an AI service as a background process."""
        try:
            if platform.system() == "Windows":
                # Start as a detached background process
                startup_info = subprocess.STARTUPINFO()
                startup_info.dwFlags |= subprocess.STARTF_USESHOWWINDOW

                proc = subprocess.Popen(
                    start_cmd,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    startupinfo=startup_info,
                    creationflags=subprocess.CREATE_NO_WINDOW,
                )
            else:
                proc = subprocess.Popen(
                    start_cmd,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )

            self._start_times[service_name] = datetime.now(timezone.utc)
            logger.info(
                f"Started AI service {service_name} (PID: {proc.pid})"
            )

        except FileNotFoundError:
            logger.warning(
                f"Could not start {service_name}: command not found. "
                "The service may need to be started manually."
            )
        except Exception as e:
            logger.error(f"Failed to start {service_name}: {e}")

    def _wait_for_healthy(
        self, service_name: str, timeout: int = 60, interval: int = 5
    ) -> bool:
        """
        Wait for a service to become healthy.

        Args:
            service_name: Name of the service
            timeout: Maximum wait time in seconds
            interval: Check interval in seconds

        Returns:
            True if the service became healthy within timeout
        """
        deadline = time.time() + timeout
        while time.time() < deadline:
            health = self.check_service_health(service_name, use_cache=False)
            if health.healthy:
                return True
            time.sleep(interval)

        return False

    def get_health_report(
        self, service_names: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Get a comprehensive health report for AI services.

        Returns a structured report with service status, resource usage,
        and any issues detected.
        """
        healths = self.check_all_services(service_names)
        healthy_count = sum(1 for h in healths.values() if h.healthy)
        total_count = len(healths)

        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "summary": {
                "total_services": total_count,
                "healthy": healthy_count,
                "unhealthy": total_count - healthy_count,
                "all_healthy": healthy_count == total_count,
            },
            "services": {
                name: h.to_dict() for name, h in healths.items()
            },
            "restart_attempts": dict(self._restart_counts),
        }
