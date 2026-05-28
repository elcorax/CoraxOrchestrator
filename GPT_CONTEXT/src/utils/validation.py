"""
Corax Orchestrator - Validation Utility Functions.

Provides input validation utilities for paths, URLs, versions, and filenames.
"""

import re
import os
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse


def validate_path(path: str) -> Optional[Path]:
    """
    Validate and resolve a file system path.

    Args:
        path: Path string to validate

    Returns:
        Resolved Path object if valid, None otherwise
    """
    try:
        resolved = Path(path).resolve()
        return resolved
    except (OSError, ValueError):
        return None


def validate_url(url: str) -> bool:
    """
    Validate a URL string.

    Args:
        url: URL string to validate

    Returns:
        True if the URL is valid
    """
    try:
        result = urlparse(url)
        return all([result.scheme, result.netloc])
    except Exception:
        return False


def validate_version(version: str) -> bool:
    """
    Validate a semantic version string.

    Supports formats:
    - X.Y.Z
    - X.Y.Z-prerelease
    - vX.Y.Z

    Args:
        version: Version string to validate

    Returns:
        True if the version string is valid
    """
    pattern = r"^v?\d+\.\d+\.\d+(-[a-zA-Z0-9.]+)?$"
    return bool(re.match(pattern, version))


def sanitize_filename(filename: str) -> str:
    """
    Sanitize a filename by removing or replacing invalid characters.

    Args:
        filename: Raw filename string

    Returns:
        Sanitized filename safe for all operating systems
    """
    # Remove null bytes
    filename = filename.replace("\0", "")

    # Replace path separators
    filename = filename.replace("/", "_").replace("\\", "_")

    # Remove characters invalid on Windows
    invalid_chars = '<>:"|?*'
    for char in invalid_chars:
        filename = filename.replace(char, "_")

    # Remove leading/trailing dots and spaces (Windows issue)
    filename = filename.strip(". ")

    # Limit length (255 chars is typical max)
    if len(filename) > 255:
        name, ext = os.path.splitext(filename)
        filename = name[: 255 - len(ext)] + ext

    return filename if filename else "unnamed"
