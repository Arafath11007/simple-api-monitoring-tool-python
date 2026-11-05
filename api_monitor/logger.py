"""Logging configuration with rotating file handler and console output."""

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path


def setup_logger(log_file: str = "./logs/monitor.log", level: int = logging.INFO) -> logging.Logger:
    logger = logging.getLogger("api_monitor")
    logger.setLevel(level)

    # Avoid duplicate handlers if setup_logger is called multiple times
    if logger.handlers:
        return logger

    # Ensure log directory exists
    log_path = Path(log_file)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    # Rotating file handler: 5MB per file, keeping 3 backups
    file_handler = RotatingFileHandler(log_path, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8")
    file_fmt = logging.Formatter("[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s")
    file_handler.setFormatter(file_fmt)
    logger.addHandler(file_handler)

    # Console handler
    console_handler = logging.StreamHandler()
    console_fmt = logging.Formatter("[%(levelname)s] %(message)s")
    console_handler.setFormatter(console_fmt)
    logger.addHandler(console_handler)

    return logger
