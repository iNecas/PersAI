import os
import sys
from loguru import logger


def configure_logging(
    level: str = "INFO",
):
    """Configure loguru for the application."""
    logger.remove()

    logger.add(
        sys.stderr,
        level=level,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level> | {extra}",
        # To prevent leaking secrets from the traceback
        diagnose=True if os.getenv("PERSAI_LOG_DIAGNOSE") == "true" else False,
    )

    return logger
