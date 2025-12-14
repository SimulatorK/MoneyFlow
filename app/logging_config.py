"""
Logging configuration for MoneyFlow application.

This module provides centralized logging configuration that can be imported
by all other modules. It sets up file and console logging with appropriate
formatting and log rotation.
"""

import logging
import logging.handlers
import os
from datetime import datetime

# Create logs directory if it doesn't exist
LOGS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'logs')
os.makedirs(LOGS_DIR, exist_ok=True)

# Log file paths
APP_LOG_FILE = os.path.join(LOGS_DIR, 'moneyflow.log')
ERROR_LOG_FILE = os.path.join(LOGS_DIR, 'errors.log')


def setup_logging(level: str = "INFO"):
    """
    Configure application-wide logging.
    
    Sets up:
    - Console handler for development feedback
    - Rotating file handler for general logs
    - Separate error log file
    
    Args:
        level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
    """
    log_level = getattr(logging, level.upper(), logging.INFO)
    
    # Create formatters
    detailed_formatter = logging.Formatter(
        fmt='%(asctime)s | %(levelname)-8s | %(name)s:%(funcName)s:%(lineno)d | %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    simple_formatter = logging.Formatter(
        fmt='%(asctime)s | %(levelname)-8s | %(message)s',
        datefmt='%H:%M:%S'
    )
    
    # Get root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)
    
    # Clear any existing handlers
    root_logger.handlers.clear()
    
    # Console handler (for development)
    console_handler = logging.StreamHandler()
    console_handler.setLevel(log_level)
    console_handler.setFormatter(simple_formatter)
    root_logger.addHandler(console_handler)
    
    # Rotating file handler (10MB max, keep 5 backups)
    file_handler = logging.handlers.RotatingFileHandler(
        APP_LOG_FILE,
        maxBytes=10*1024*1024,  # 10MB
        backupCount=5,
        encoding='utf-8'
    )
    file_handler.setLevel(log_level)
    file_handler.setFormatter(detailed_formatter)
    root_logger.addHandler(file_handler)
    
    # Error file handler (errors and above only)
    error_handler = logging.handlers.RotatingFileHandler(
        ERROR_LOG_FILE,
        maxBytes=5*1024*1024,  # 5MB
        backupCount=3,
        encoding='utf-8'
    )
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(detailed_formatter)
    root_logger.addHandler(error_handler)
    
    # Configure uvicorn loggers
    logging.getLogger("uvicorn.access").setLevel(logging.INFO)
    logging.getLogger("uvicorn.error").setLevel(logging.INFO)
    
    # Reduce noise from some libraries
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
    
    # Log startup
    root_logger.info(f"Logging configured at level: {level}")
    root_logger.info(f"Log files: {APP_LOG_FILE}, {ERROR_LOG_FILE}")


def get_logger(name: str) -> logging.Logger:
    """
    Get a logger for a specific module.
    
    Args:
        name: Usually __name__ of the calling module
        
    Returns:
        Configured logger instance
    """
    return logging.getLogger(name)


# Initialize logging when this module is imported
setup_logging("INFO")

