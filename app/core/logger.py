"""
Enterprise-grade structured logging configuration using structlog
"""
import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from typing import Any, Dict

import structlog
from structlog.types import Processor


def setup_structlog() -> None:
    """
    Configure structlog for enterprise-grade structured JSON logging.
    
    Features:
    - JSON output for log aggregation (ELK, Datadog, CloudWatch)
    - Request ID correlation
    - Proper log levels (INFO, WARN, ERROR)
    - Timestamp in ISO format
    - Context-aware logging
    """
    # Configure standard logging first
    log_level = os.getenv("LOG_LEVEL", "INFO").upper()
    
    # Console handler for development (always available)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(getattr(logging, log_level, logging.INFO))
    
    # Try to create file handler, but gracefully fall back to console-only if permissions fail
    file_handler = None
    try:
        # Create logs directory if it doesn't exist
        logs_dir = "logs"
        os.makedirs(logs_dir, exist_ok=True)
        
        # Verify we can write to the directory
        test_file = os.path.join(logs_dir, ".test_write")
        try:
            with open(test_file, "w") as f:
                f.write("test")
            os.remove(test_file)
        except (OSError, PermissionError):
            # Can't write to logs directory, skip file handler
            pass
        else:
            # File handler with rotation for structured logs
            file_handler = RotatingFileHandler(
                os.path.join(logs_dir, "app.log"),
                maxBytes=10 * 1024 * 1024,  # 10MB
                backupCount=5,
                encoding="utf-8"
            )
            file_handler.setLevel(getattr(logging, log_level, logging.INFO))
    except (OSError, PermissionError):
        # Permission denied or other filesystem error - continue with console-only logging
        pass
    
    # Configure structlog processors
    processors: list[Processor] = [
        structlog.contextvars.merge_contextvars,  # Merge context variables
        structlog.stdlib.add_log_level,  # Add log level
        structlog.stdlib.add_logger_name,  # Add logger name
        structlog.processors.TimeStamper(fmt="iso"),  # ISO timestamp
        structlog.processors.StackInfoRenderer(),  # Stack traces
        structlog.processors.format_exc_info,  # Exception formatting
    ]
    
    # Use JSON renderer for production, console for development
    use_json = os.getenv("LOG_FORMAT", "json").lower() == "json"
    if use_json:
        processors.append(structlog.processors.JSONRenderer())
    else:
        processors.append(structlog.dev.ConsoleRenderer())
    
    # Configure structlog
    structlog.configure(
        processors=processors,
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )
    
    # Configure root logger with handlers (avoid duplication)
    root_logger = logging.getLogger()
    root_logger.handlers.clear()  # Clear any existing handlers
    
    # Add file handler only if it was successfully created
    if file_handler:
        root_logger.addHandler(file_handler)
    
    # Always add console handler
    root_logger.addHandler(console_handler)
    root_logger.setLevel(getattr(logging, log_level, logging.INFO))
    
    # Prevent propagation to avoid duplicate logs
    root_logger.propagate = False


def get_logger(name: str = None) -> structlog.stdlib.BoundLogger:
    """
    Get a structured logger instance.
    
    Args:
        name: Logger name (typically __name__)
        
    Returns:
        BoundLogger instance for structured logging
    """
    return structlog.get_logger(name)


# Initialize structlog on module import
setup_structlog()

# Global logger instance
logger = get_logger(__name__)
