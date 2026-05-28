"""
Corax Orchestrator — Windows Hardening Utilities.

Provides:
- Retry-safe file access with exponential backoff
- Safe temp file cleanup with retry
- File lock diagnostics
- Anti-virus interference mitigation
- PyInstaller extraction safety
"""

import os
import time
import random
import shutil
import tempfile
import logging
from typing import Optional, Callable, TypeVar, Any
from functools import wraps

from src.core.logging import get_logger

logger = get_logger("windows_hardening")

# Win32 error codes
ERROR_SHARING_VIOLATION = 32       # File is locked by another process
ERROR_LOCK_VIOLATION = 33          # Lock violation
ERROR_FILE_NOT_FOUND = 2
ERROR_ACCESS_DENIED = 5
ERROR_PATH_NOT_FOUND = 3

# Retry configuration
MAX_RETRIES = 5
BASE_DELAY = 0.5  # seconds
MAX_DELAY = 10.0  # seconds
JITTER = 0.1      # seconds

T = TypeVar('T')


def retry_file_operation(
    max_retries: int = MAX_RETRIES,
    base_delay: float = BASE_DELAY,
    max_delay: float = MAX_DELAY,
) -> Callable:
    """Decorator for retry-safe file operations with exponential backoff."""

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> T:
            last_exception = None

            for attempt in range(1, max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except (PermissionError, OSError) as e:
                    last_exception = e
                    winerror = getattr(e, 'winerror', 0)

                    # Only retry on file-lock related errors
                    if winerror not in (
                        ERROR_SHARING_VIOLATION,
                        ERROR_LOCK_VIOLATION,
                        ERROR_ACCESS_DENIED,
                    ):
                        raise

                    if attempt < max_retries:
                        delay = min(
                            base_delay * (2 ** (attempt - 1)) +
                            random.uniform(0, JITTER),
                            max_delay,
                        )
                        logger.debug(
                            f"File operation retry {attempt}/{max_retries} "
                            f"after {delay:.1f}s (winerror={winerror})"
                        )
                        time.sleep(delay)

            # Final attempt failed
            logger.warning(
                f"File operation failed after {max_retries} retries: "
                f"{last_exception}"
            )
            raise last_exception  # type: ignore

        return wrapper

    return decorator


class SafeFileAccess:
    """Safe file operations with retry and diagnostic capabilities."""

    @staticmethod
    @retry_file_operation()
    def read_file(path: str, mode: str = 'rb') -> bytes:
        """Read file with retry on lock contention."""
        with open(path, mode) as f:
            return f.read()

    @staticmethod
    @retry_file_operation()
    def write_file(path: str, data: bytes, mode: str = 'wb') -> None:
        """Write file with retry on lock contention."""
        # Ensure directory exists
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        with open(path, mode) as f:
            f.write(data)

    @staticmethod
    @retry_file_operation()
    def delete_file(path: str) -> None:
        """Delete file with retry on lock contention."""
        if os.path.exists(path):
            os.remove(path)

    @staticmethod
    @retry_file_operation()
    def move_file(src: str, dst: str) -> None:
        """Move/rename file with retry on lock contention."""
        os.makedirs(os.path.dirname(os.path.abspath(dst)), exist_ok=True)
        shutil.move(src, dst)

    @staticmethod
    def safe_temp_directory(prefix: str = "corax_") -> str:
        """Create a temp directory with safe cleanup tracking."""
        temp_dir = tempfile.mkdtemp(prefix=prefix)
        logger.debug(f"Created temp directory: {temp_dir}")
        return temp_dir

    @staticmethod
    def cleanup_temp_directory(temp_dir: str, max_retries: int = 3) -> bool:
        """Safely remove a temp directory with retry."""
        if not os.path.exists(temp_dir):
            return True

        for attempt in range(1, max_retries + 1):
            try:
                shutil.rmtree(temp_dir, onerror=None)
                logger.debug(f"Cleaned up temp directory: {temp_dir}")
                return True
            except (PermissionError, OSError) as e:
                if attempt < max_retries:
                    delay = 0.5 * (2 ** (attempt - 1))
                    logger.debug(
                        f"Temp cleanup retry {attempt}/{max_retries}: {e}"
                    )
                    time.sleep(delay)
                else:
                    logger.warning(
                        f"Failed to cleanup temp directory after "
                        f"{max_retries} attempts: {temp_dir} - {e}"
                    )
                    return False
        return False


class FileLockDiagnostics:
    """Diagnose file lock issues for troubleshooting."""

    @staticmethod
    def check_file_access(path: str) -> dict:
        """Check if a file can be accessed and diagnose issues."""
        result = {
            "path": path,
            "exists": os.path.exists(path),
            "readable": False,
            "writable": False,
            "locked": False,
            "diagnostics": [],
        }

        if not result["exists"]:
            result["diagnostics"].append("File does not exist")
            return result

        # Check readability
        try:
            with open(path, 'rb') as f:
                f.read(1)
            result["readable"] = True
        except PermissionError as e:
            result["diagnostics"].append(
                f"Permission denied (winerror={getattr(e, 'winerror', 0)})"
            )
        except OSError as e:
            winerror = getattr(e, 'winerror', 0)
            result["diagnostics"].append(
                f"OS error (winerror={winerror}): {e}"
            )
            if winerror in (ERROR_SHARING_VIOLATION, ERROR_LOCK_VIOLATION):
                result["locked"] = True

        # Check writability
        try:
            with open(path, 'ab') as f:
                pass  # Just test append mode
            result["writable"] = True
        except (PermissionError, OSError):
            pass

        # File attributes
        try:
            stat = os.stat(path)
            result["size"] = stat.st_size
            result["mode"] = stat.st_mode
        except Exception as e:
            result["diagnostics"].append(f"Could not stat file: {e}")

        return result

    @staticmethod
    def diagnose_temp_extraction(temp_dir: str) -> list:
        """Diagnose PyInstaller temp extraction directory."""
        issues = []

        if not os.path.exists(temp_dir):
            issues.append(f"Temp directory does not exist: {temp_dir}")
            return issues

        # Check each file in temp
        for root, dirs, files in os.walk(temp_dir):
            for filename in files[:20]:  # Limit checks
                filepath = os.path.join(root, filename)
                diag = FileLockDiagnostics.check_file_access(filepath)
                if diag.get("locked"):
                    issues.append(
                        f"File locked: {filename} - "
                        f"{'; '.join(diag['diagnostics'])}"
                    )

        # Check directory permissions
        try:
            test_file = os.path.join(temp_dir, ".corax_write_test")
            with open(test_file, 'w') as f:
                f.write("test")
            os.remove(test_file)
        except (PermissionError, OSError) as e:
            issues.append(
                f"Temp directory not writable: {e}"
            )

        return issues


# Convenience functions

def safe_read(path: str) -> Optional[bytes]:
    """Read a file safely with retry."""
    try:
        return SafeFileAccess.read_file(path)
    except Exception as e:
        logger.error(f"Failed to read {path}: {e}")
        return None


def safe_write(path: str, data: bytes) -> bool:
    """Write a file safely with retry."""
    try:
        SafeFileAccess.write_file(path, data)
        return True
    except Exception as e:
        logger.error(f"Failed to write {path}: {e}")
        return False


def safe_delete(path: str) -> bool:
    """Delete a file safely with retry."""
    try:
        SafeFileAccess.delete_file(path)
        return True
    except Exception as e:
        logger.error(f"Failed to delete {path}: {e}")
        return False


def diagnose_file_locks(paths: list) -> list:
    """Diagnose file lock issues for multiple paths."""
    diagnostics = FileLockDiagnostics()
    results = []
    for path in paths:
        results.append(diagnostics.check_file_access(path))
    return results
