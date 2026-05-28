"""
Corax Orchestrator - Network Utility Functions.

Provides network-related utility functions for connectivity checks,
file downloads, and URL validation.
"""

import os
import asyncio
from pathlib import Path
from typing import Optional, Callable, Awaitable

import aiohttp
import httpx


async def check_connectivity(url: str = "https://google.com", timeout: int = 5) -> bool:
    """
    Check if there is internet connectivity by pinging a URL.

    Args:
        url: URL to check connectivity against
        timeout: Timeout in seconds

    Returns:
        True if reachable, False otherwise
    """
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=timeout)) as response:
                return response.status < 500
    except Exception:
        return False


async def download_file_async(
    url: str,
    destination: Path,
    progress_callback: Optional[Callable[[int, int], Awaitable[None]]] = None,
    chunk_size: int = 8192,
) -> Path:
    """
    Download a file asynchronously with progress reporting.

    Args:
        url: URL to download from
        destination: Path to save the file
        progress_callback: Optional async callback (downloaded, total)
        chunk_size: Size of download chunks

    Returns:
        Path to the downloaded file
    """
    destination.parent.mkdir(parents=True, exist_ok=True)

    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            response.raise_for_status()

            total_size = int(response.headers.get("content-length", 0))
            downloaded = 0

            with open(destination, "wb") as f:
                async for chunk in response.content.iter_chunked(chunk_size):
                    f.write(chunk)
                    downloaded += len(chunk)
                    if progress_callback and total_size:
                        await progress_callback(downloaded, total_size)

    return destination


def download_file(
    url: str,
    destination: Path,
    timeout: int = 300,
) -> Path:
    """
    Download a file synchronously.

    Args:
        url: URL to download from
        destination: Path to save the file
        timeout: Timeout in seconds

    Returns:
        Path to the downloaded file
    """
    destination.parent.mkdir(parents=True, exist_ok=True)

    with httpx.Client(timeout=timeout) as client:
        response = client.get(url)
        response.raise_for_status()

        with open(destination, "wb") as f:
            f.write(response.content)

    return destination


async def check_url(url: str, timeout: int = 5) -> bool:
    """
    Check if a URL is accessible.

    Args:
        url: URL to check
        timeout: Timeout in seconds

    Returns:
        True if accessible, False otherwise
    """
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.head(url)
            return response.status_code < 500
    except Exception:
        return False
