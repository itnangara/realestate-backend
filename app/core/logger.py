"""
Structured logging configuration
"""
import logging
import os
from logging.handlers import RotatingFileHandler


def setup_logger(name: str = "real_estate_app") -> logging.Logger:
    """Configure and return a structured logger"""
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    
    # Create logs directory if it doesn't exist
    os.makedirs("logs", exist_ok=True)
    
    # File handler with rotation
    handler = RotatingFileHandler(
        "logs/app.log",
        maxBytes=10 * 1024 * 1024,  # 10MB
        backupCount=5
    )
    
    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    
    # Formatter
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(funcName)s:%(lineno)d - %(message)s'
    )
    
    handler.setFormatter(formatter)
    console_handler.setFormatter(formatter)
    
    logger.addHandler(handler)
    logger.addHandler(console_handler)
    
    return logger


# Global logger instance
logger = setup_logger()
