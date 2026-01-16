"""Centralized logging configuration for the Dota Analyzer application.

This module sets up logging to both console and file handlers with consistent
formatting across the entire application.
"""

import logging
import os


def setup_logging(logger_name: str = __name__) -> logging.Logger:
    """Configure and return a logger with console and file handlers.

    Args:
        logger_name: Name of the logger (typically __name__ from calling module)

    Returns:
        Configured logger instance
    """
    logger = logging.getLogger(logger_name)

    # Only configure if not already configured (avoid duplicate handlers)
    if logger.handlers:
        return logger

    # Determine the application root directory (parent of backend directory)
    backend_dir = os.path.dirname(os.path.abspath(__file__))
    app_root = os.path.dirname(backend_dir)
    logs_dir = os.path.join(app_root, "logs")

    # Create logs directory if it doesn't exist
    os.makedirs(logs_dir, exist_ok=True)

    # Set logger level
    logger.setLevel(logging.DEBUG)

    # Create console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.DEBUG)

    # Create file handler with absolute path
    log_file_path = os.path.join(logs_dir, "dota2_bet_analyzer.log")
    file_handler = logging.FileHandler(log_file_path)
    file_handler.setLevel(logging.DEBUG)

    # Create formatter
    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    console_handler.setFormatter(formatter)
    file_handler.setFormatter(formatter)

    # Add handlers to logger
    logger.addHandler(console_handler)
    logger.addHandler(file_handler)

    return logger
