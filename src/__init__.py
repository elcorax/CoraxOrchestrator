"""
Corax Orchestrator - Autonomous AI Workstation Deployment System.

A production-grade autonomous deployment agent capable of transforming
a clean computer into a complete AI development workstation.
"""

__version__ = "0.1.0"
__author__ = "Corax Team"
__license__ = "MIT"

from src.core.logging import get_logger

logger = get_logger(__name__)
logger.info("Corax Orchestrator initialized", version=__version__)
