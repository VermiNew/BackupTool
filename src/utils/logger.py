"""Logging configuration for the backup tool."""

import json
import logging
import sys
from datetime import datetime
from pathlib import Path
from logging.handlers import RotatingFileHandler
from typing import Any, Dict

class JsonFormatter(logging.Formatter):
    """Custom formatter that outputs logs in JSON format."""
    
    def format(self, record: logging.LogRecord) -> str:
        """Format the log record as JSON."""
        log_data = {
            'timestamp': datetime.fromtimestamp(record.created).isoformat(),
            'level': record.levelname,
            'message': record.getMessage(),
            'logger': record.name
        }
        
        # Add extra fields if they exist
        if hasattr(record, 'extra'):
            log_data.update(record.extra)
        
        # Add exception info if present
        if record.exc_info:
            log_data['exception'] = {
                'type': record.exc_info[0].__name__,
                'message': str(record.exc_info[1]),
                'traceback': self.formatException(record.exc_info)
            }
            
        return json.dumps(log_data)

class HealthCheckHandler(logging.Handler):
    """Handler that monitors logging health and system status."""
    
    def __init__(self, health_file: Path):
        super().__init__()
        self.health_file = health_file
        self.error_count = 0
        self.last_error_time = None
        
    def emit(self, record: logging.LogRecord) -> None:
        """Update health metrics when a log is emitted."""
        if record.levelno >= logging.ERROR:
            self.error_count += 1
            self.last_error_time = datetime.now()
            self._update_health_file()
    
    def _update_health_file(self) -> None:
        """Update the health check file with current status."""
        health_data = {
            'last_update': datetime.now().isoformat(),
            'error_count': self.error_count,
            'last_error': self.last_error_time.isoformat() if self.last_error_time else None,
            'status': 'degraded' if self.error_count > 0 else 'healthy'
        }
        
        with self.health_file.open('w', encoding='utf-8') as f:
            json.dump(health_data, f, indent=2)

def setup_logger(log_dir: Path = None) -> logging.Logger:
    """Setup application logger with JSON formatting and health monitoring."""
    logger = logging.getLogger('backup_tool')
    logger.setLevel(logging.INFO)
    
    # Remove existing handlers
    logger.handlers.clear()
    
    # Console handler with simple formatting
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(logging.Formatter('%(message)s'))
    logger.addHandler(console_handler)
    
    if log_dir:
        log_dir.mkdir(parents=True, exist_ok=True)
        
        # JSON file handler
        json_handler = RotatingFileHandler(
            log_dir / 'backup.json',
            maxBytes=10 * 1024 * 1024,  # 10MB
            backupCount=5,
            encoding='utf-8'
        )
        json_handler.setLevel(logging.DEBUG)
        json_handler.setFormatter(JsonFormatter())
        logger.addHandler(json_handler)
        
        # Health check handler
        health_handler = HealthCheckHandler(log_dir / 'health.json')
        health_handler.setLevel(logging.ERROR)
        logger.addHandler(health_handler)
    
    return logger

def log_with_context(logger: logging.Logger, level: int, message: str, context: Dict[str, Any] = None) -> None:
    """Log a message with additional context in JSON format."""
    extra = {'extra': context} if context else {}
    logger.log(level, message, extra=extra) 