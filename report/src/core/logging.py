"""
Corax Orchestrator - Structured Logging System.

Provides production-grade structured logging with:
- Structured JSON output for log aggregation
- Console output with Rich formatting
- Async log file writing
- Log rotation
- Correlation IDs for request tracing
- Configurable log levels per module
"""

import os
import sys
import json
import logging
import logging.handlers
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, Optional
from uuid import uuid4

import structlog
from structlog.processors import JSONRenderer, TimeStamper
from structlog.types import EventDict, Processor

# Module-level correlation ID context
_correlation_id: Optional[str] = None


def set_correlation_id(cid: Optional[str] = None) -> str:
    """Set or generate a correlation ID for request tracing."""
    global _correlation_id
    _correlation_id = cid or str(uuid4())
    return _correlation_id


def get_correlation_id() -> Optional[str]:
    """Get the current correlation ID."""
    return _correlation_id


def _add_correlation_id(
    logger: logging.Logger, method_name: str, event_dict: EventDict
) -> EventDict:
    """Processor that adds correlation ID to log events."""
    cid = get_correlation_id()
    if cid:
        event_dict["correlation_id"] = cid
    return event_dict


def _drop_debug_if_needed(
    logger: logging.Logger, method_name: str, event_dict: EventDict
) -> EventDict:
    """Drop debug messages if not in debug mode."""
    return event_dict


def _rename_event_to_message(
    logger: logging.Logger, method_name: str, event_dict: EventDict
) -> EventDict:
    """Rename 'event' key to 'message' for log aggregation compatibility."""
    if "event" in event_dict:
        event_dict["message"] = event_dict.pop("event")
    return event_dict


def _format_exc_info(
    logger: logging.Logger, method_name: str, event_dict: EventDict
) -> EventDict:
    """Format exception info for structured logging."""
    if "exc_info" in event_dict and event_dict["exc_info"]:
        import traceback

        exc = event_dict["exc_info"]
        if isinstance(exc, tuple):
            event_dict["exception"] = {
                "type": exc[0].__name__,
                "message": str(exc[1]),
                "traceback": "".join(traceback.format_tb(exc[2])),
            }
        del event_dict["exc_info"]
    return event_dict


class LogManager:
    """
    Centralized log manager for Corax Orchestrator.

    Configures structured logging with both console and file outputs.
    Supports log rotation, correlation IDs, and module-level filtering.
    """

    def __init__(
        self,
        log_dir: Optional[Path] = None,
        log_level: str = "INFO",
        json_output: bool = False,
        max_bytes: int = 10 * 1024 * 1024,  # 10MB
        backup_count: int = 5,
    ) -> None:
        self.log_dir = log_dir or Path("data/logs")
        self.log_level = getattr(logging, log_level.upper(), logging.INFO)
        self.json_output = json_output
        self.max_bytes = max_bytes
        self.backup_count = backup_count
        self._initialized = False

    def initialize(self) -> None:
        """Initialize the logging system."""
        if self._initialized:
            return

        # Ensure log directory exists
        self.log_dir.mkdir(parents=True, exist_ok=True)

        # Configure structlog
        processors: list[Processor] = [
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            TimeStamper(fmt="iso", utc=True),
            _add_correlation_id,
            _rename_event_to_message,
            _format_exc_info,
            structlog.processors.StackInfoRenderer(),
            structlog.dev.ConsoleRenderer()
            if not self.json_output
            else JSONRenderer(),
        ]

        structlog.configure(
            processors=processors,
            context_class=dict,
            logger_factory=structlog.stdlib.LoggerFactory(),
            cache_logger_on_first_use=True,
        )

        # Configure root logger
        root_logger = logging.getLogger()
        root_logger.setLevel(self.log_level)

        # File handler with rotation
        log_file = self.log_dir / "corax.log"
        file_handler = logging.handlers.RotatingFileHandler(
            filename=str(log_file),
            maxBytes=self.max_bytes,
            backupCount=self.backup_count,
            encoding="utf-8",
        )
        file_handler.setLevel(self.log_level)
        file_handler.setFormatter(
            logging.Formatter(
                "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
            )
        )
        root_logger.addHandler(file_handler)

        # JSON file handler for log aggregation
        json_log_file = self.log_dir / "corax.jsonl"
        json_handler = logging.handlers.RotatingFileHandler(
            filename=str(json_log_file),
            maxBytes=self.max_bytes,
            backupCount=self.backup_count,
            encoding="utf-8",
        )
        json_handler.setLevel(self.log_level)

        class JSONFormatter(logging.Formatter):
            def format(self, record: logging.LogRecord) -> str:
                log_entry = {
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "level": record.levelname,
                    "logger": record.name,
                    "message": record.getMessage(),
                    "module": record.module,
                    "line": record.lineno,
                }
                if hasattr(record, "correlation_id"):
                    log_entry["correlation_id"] = record.correlation_id
                if record.exc_info and record.exc_info[0]:
                    log_entry["exception"] = {
                        "type": record.exc_info[0].__name__,
                        "message": str(record.exc_info[1]),
                    }
                return json.dumps(log_entry)

        json_handler.setFormatter(JSONFormatter())
        root_logger.addHandler(json_handler)

        self._initialized = True

    def get_log_path(self) -> Path:
        """Get the path to the main log file."""
        return self.log_dir / "corax.log"

    def get_json_log_path(self) -> Path:
        """Get the path to the JSON log file."""
        return self.log_dir / "corax.jsonl"


def setup_logging(
    log_dir: Optional[Path] = None,
    log_level: str = "INFO",
    json_output: bool = False,
) -> None:
    """
    Initialize the logging system with defaults.

    Convenience function that creates a LogManager and initializes it.
    This is the function imported by main.py and other entry points.

    Args:
        log_dir: Directory for log files (default: data/logs)
        log_level: Log level string (default: INFO)
        json_output: Whether to output JSON logs to console
    """
    manager = LogManager(
        log_dir=log_dir,
        log_level=log_level,
        json_output=json_output,
    )
    manager.initialize()


def get_logger(name: str = __name__) -> structlog.stdlib.BoundLogger:
    """
    Get a structured logger instance.

    Args:
        name: The logger name, typically __name__

    Returns:
        A configured structlog BoundLogger
    """
    return structlog.get_logger(name)
