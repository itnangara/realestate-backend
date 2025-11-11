"""
Enterprise-grade structured logging configuration using structlog
"""
import logging
import os
import re
import sys
from logging.handlers import RotatingFileHandler
from typing import Any, Dict

import structlog
from structlog.types import Processor, EventDict


def mask_pii(_, __, event_dict: EventDict) -> EventDict:
    """
    Enterprise-grade PII masking processor for structlog.
    
    Masks sensitive data in log entries:
    - Email addresses (keeps domain visible)
    - Phone numbers
    - User IDs (optional, configurable)
    - Passwords/tokens (if accidentally logged)
    - Credit card numbers (if present)
    
    Args:
        event_dict: The event dictionary containing log data
        
    Returns:
        Event_dict with masked PII values
    """
    # Fields that should be masked (case-insensitive)
    sensitive_fields = {
        'email', 'user_email', 'email_address',
        'phone', 'phone_number', 'mobile', 'telephone',
        'password', 'hashed_password', 'token', 'access_token', 'refresh_token',
        'api_key', 'secret', 'secret_key', 'auth_token',
        'credit_card', 'card_number', 'ssn', 'social_security',
        'bank_account', 'routing_number'
    }
    
    # Email regex pattern
    email_pattern = re.compile(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b')
    # Phone number patterns (various formats)
    phone_pattern = re.compile(r'\b(?:\+?1[-.\s]?)?\(?[0-9]{3}\)?[-.\s]?[0-9]{3}[-.\s]?[0-9]{4}\b')
    # Credit card pattern (basic)
    cc_pattern = re.compile(r'\b\d{4}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}\b')
    
    def mask_email(email: str) -> str:
        """Mask email while keeping domain visible"""
        if '@' not in email:
            return '***'
        local, domain = email.split('@', 1)
        if len(local) <= 2:
            masked_local = '*' * len(local)
        else:
            masked_local = local[0] + '*' * (len(local) - 2) + local[-1]
        return f"{masked_local}@{domain}"
    
    def mask_phone(phone: str) -> str:
        """Mask phone number"""
        digits = re.sub(r'\D', '', phone)
        if len(digits) >= 10:
            return f"***-***-{digits[-4:]}"
        return '***-***-****'
    
    def mask_value(value: Any, field_name: str) -> Any:
        """Mask a value based on its type and field name"""
        if not isinstance(value, str):
            return value
        
        # Check if field name indicates sensitive data
        field_lower = field_name.lower()
        is_sensitive_field = any(sensitive in field_lower for sensitive in sensitive_fields)
        
        # Mask based on field name
        if is_sensitive_field:
            if 'email' in field_lower and '@' in str(value):
                return mask_email(str(value))
            elif 'phone' in field_lower or 'mobile' in field_lower or 'telephone' in field_lower:
                return mask_phone(str(value))
            elif 'password' in field_lower or 'token' in field_lower or 'secret' in field_lower or 'key' in field_lower:
                return '***MASKED***'
            else:
                # Generic masking for other sensitive fields
                if len(str(value)) <= 4:
                    return '***'
                return str(value)[0] + '*' * (len(str(value)) - 2) + str(value)[-1] if len(str(value)) > 1 else '***'
        
        # Pattern-based masking (even if field name doesn't indicate sensitivity)
        if email_pattern.search(str(value)):
            return email_pattern.sub(lambda m: mask_email(m.group()), str(value))
        if phone_pattern.search(str(value)):
            return phone_pattern.sub(lambda m: mask_phone(m.group()), str(value))
        if cc_pattern.search(str(value)):
            return '****-****-****-****'
        
        return value
    
    # Process all fields in event_dict
    for key, value in event_dict.items():
        # Skip event, level, timestamp, logger, etc.
        if key in ('event', 'level', 'timestamp', 'logger', 'message', 'request_id'):
            continue
        
        # Mask sensitive values
        event_dict[key] = mask_value(value, key)
    
    return event_dict


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
        mask_pii,  # Enterprise-grade PII masking (before stack traces)
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
