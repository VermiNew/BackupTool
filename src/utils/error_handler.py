"""Error handling and reporting module for the backup tool."""

import json
import logging
import traceback
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional
import psutil
import platform

logger = logging.getLogger(__name__)

@dataclass
class ErrorReport:
    """Data structure for error reporting."""
    timestamp: str
    error_type: str
    error_message: str
    traceback: str
    system_info: Dict
    context: Optional[Dict] = None

class BackupError(Exception):
    """Base exception for backup operations."""
    def __init__(self, message: str, context: Dict[str, Any] = None):
        super().__init__(message)
        self.context = context or {}
        self.timestamp = datetime.now().isoformat()

class FileOperationError(BackupError):
    """Exception for file operation failures."""
    pass

class NetworkError(BackupError):
    """Exception for network-related failures."""
    pass

class ConfigurationError(BackupError):
    """Exception for configuration-related errors."""
    pass

class ErrorTracker:
    """Tracks and manages error reporting."""
    
    def __init__(self, log_dir: Path):
        """Initialize error tracker.
        
        Args:
            log_dir: Directory for storing error logs
        """
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        
    def create_error_report(self, error: Exception, context: Dict[str, Any] = None) -> ErrorReport:
        """Create structured error report.
        
        Args:
            error: Exception that occurred
            context: Additional context about the error
            
        Returns:
            ErrorReport object containing error details
        """
        # Get disk usage for all mounted disks
        disk_usage = {}
        for disk in psutil.disk_partitions():
            try:
                usage = psutil.disk_usage(disk.mountpoint)
                disk_usage[str(disk.mountpoint)] = {
                    'total': usage.total,
                    'used': usage.used,
                    'free': usage.free,
                    'percent': usage.percent
                }
            except Exception as e:
                logger.warning(f"Could not get disk usage for {disk.mountpoint}: {e}")
                
        # Create system info dictionary
        system_info = {
            'platform': platform.platform(),
            'python_version': platform.python_version(),
            'memory_usage': dict(psutil.virtual_memory()._asdict()),
            'disk_usage': disk_usage,
            'cpu_percent': psutil.cpu_percent(interval=1)
        }
        
        return ErrorReport(
            timestamp=datetime.now().isoformat(),
            error_type=error.__class__.__name__,
            error_message=str(error),
            traceback=traceback.format_exc(),
            system_info=system_info,
            context=context
        )
        
    def handle_error(self, error: Exception, context: Dict[str, Any] = None):
        """Handle and log an error.
        
        Args:
            error: Exception that occurred
            context: Additional context about the error
        """
        try:
            # Create error report
            report = self.create_error_report(error, context)
            
            # Save to JSON file
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            error_file = self.log_dir / f"error_{timestamp}.json"
            
            with open(error_file, 'w') as f:
                json.dump(asdict(report), f, indent=2)
                
            logger.error(f"Error report saved to {error_file}")
            
            # Log the error
            logger.error(f"Error occurred: {error}")
            if context:
                logger.error(f"Error context: {context}")
            logger.error(report.traceback)
            
        except Exception as e:
            logger.error(f"Failed to handle error: {e}")
            logger.error(traceback.format_exc())
            
    def get_recent_errors(self, limit: int = 10) -> list:
        """Get most recent error reports.
        
        Args:
            limit: Maximum number of reports to return
            
        Returns:
            List of recent error reports
        """
        try:
            error_files = sorted(
                self.log_dir.glob("error_*.json"),
                key=lambda x: x.stat().st_mtime,
                reverse=True
            )[:limit]
            
            reports = []
            for file in error_files:
                try:
                    with open(file) as f:
                        reports.append(json.load(f))
                except Exception as e:
                    logger.error(f"Failed to read error report {file}: {e}")
                    
            return reports
            
        except Exception as e:
            logger.error(f"Failed to get recent errors: {e}")
            return []

def get_last_error_reports(log_dir: Path, count: int = 5) -> List[ErrorReport]:
    """Retrieve the most recent error reports."""
    error_dir = log_dir / 'error_reports'
    if not error_dir.exists():
        return []
    
    reports = []
    for file in sorted(error_dir.glob('error_*.json'), reverse=True)[:count]:
        with file.open('r', encoding='utf-8') as f:
            data = json.load(f)
            reports.append(ErrorReport(**data))
    
    return reports 