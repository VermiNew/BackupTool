"""Module for cleaning up temporary files and caches."""
import os
import shutil
import logging
import tempfile
import time
from pathlib import Path
from typing import List, Set

logger = logging.getLogger(__name__)

class CleanupManager:
    """Manages cleanup operations for the application."""
    
    # File patterns to clean up
    TEMP_FILE_PATTERNS = [
        '*.pyc',        # Python compiled files
        '*.pyo',        # Python optimized files
        '*.pyd',        # Python dynamic modules
        '*.log',        # Log files
        '*.tmp',        # Temporary files
        '*.bak',        # Backup files
        '*.swp',        # Vim swap files
        '*.~*',         # Backup files
        '*.cache',      # Cache files
        '.DS_Store',    # macOS system files
        'Thumbs.db'     # Windows thumbnail cache
    ]
    
    def __init__(self, base_dir: Path = None):
        """Initialize cleanup manager.
        
        Args:
            base_dir: Base directory for cleanup operations. Defaults to src directory.
        """
        if base_dir is None:
            base_dir = Path(__file__).parent.parent
        self.base_dir = base_dir
        self._temp_dirs: Set[Path] = set()
        
    def register_temp_dir(self, path: Path):
        """Register a temporary directory for cleanup.
        
        Args:
            path: Path to temporary directory
        """
        self._temp_dirs.add(path)
        logger.debug(f"Registered temporary directory: {path}")
        
    def remove_pycache(self) -> int:
        """Remove all __pycache__ directories in the project.
        
        Returns:
            Number of removed directories
        """
        removed_count = 0
        try:
            for root, dirs, _ in os.walk(self.base_dir):
                for dir_name in dirs:
                    if dir_name == "__pycache__":
                        cache_path = Path(root) / dir_name
                        try:
                            shutil.rmtree(cache_path)
                            removed_count += 1
                            logger.info(f"Removed __pycache__ directory: {cache_path}")
                        except Exception as e:
                            logger.error(f"Failed to remove {cache_path}: {e}")
            
            logger.info(f"Removed {removed_count} __pycache__ directories")
            return removed_count
            
        except Exception as e:
            logger.error(f"Error while removing __pycache__ directories: {e}")
            return 0
            
    def clean_temp_files(self) -> int:
        """Remove temporary files based on patterns.
        
        Returns:
            Number of removed files
        """
        removed_count = 0
        try:
            for root, _, files in os.walk(self.base_dir):
                for pattern in self.TEMP_FILE_PATTERNS:
                    for file in Path(root).glob(pattern):
                        try:
                            file.unlink()
                            removed_count += 1
                            logger.info(f"Removed temporary file: {file}")
                        except Exception as e:
                            logger.error(f"Failed to remove {file}: {e}")
                            
            logger.info(f"Removed {removed_count} temporary files")
            return removed_count
            
        except Exception as e:
            logger.error(f"Error while removing temporary files: {e}")
            return 0
            
    def clean_empty_dirs(self) -> int:
        """Remove empty directories.
        
        Returns:
            Number of removed directories
        """
        removed_count = 0
        try:
            for root, dirs, files in os.walk(self.base_dir, topdown=False):
                if not files and not dirs:
                    try:
                        os.rmdir(root)
                        removed_count += 1
                        logger.info(f"Removed empty directory: {root}")
                    except Exception as e:
                        logger.error(f"Failed to remove empty directory {root}: {e}")
                        
            logger.info(f"Removed {removed_count} empty directories")
            return removed_count
            
        except Exception as e:
            logger.error(f"Error while removing empty directories: {e}")
            return 0
            
    def clean_temp_dirs(self) -> int:
        """Remove registered temporary directories.
        
        Returns:
            Number of removed directories
        """
        removed_count = 0
        for temp_dir in self._temp_dirs.copy():
            try:
                if temp_dir.exists():
                    shutil.rmtree(temp_dir)
                    removed_count += 1
                    logger.info(f"Removed temporary directory: {temp_dir}")
                self._temp_dirs.remove(temp_dir)
            except Exception as e:
                logger.error(f"Failed to remove temporary directory {temp_dir}: {e}")
                
        logger.info(f"Removed {removed_count} temporary directories")
        return removed_count
        
    def clean_old_logs(self, max_age_days: int = 30) -> int:
        """Remove log files older than specified days.
        
        Args:
            max_age_days: Maximum age of log files in days
            
        Returns:
            Number of removed files
        """
        removed_count = 0
        log_dir = self.base_dir / 'logs'
        if not log_dir.exists():
            return 0
            
        try:
            current_time = time.time()
            for log_file in log_dir.glob('*.log'):
                if (current_time - log_file.stat().st_mtime) > (max_age_days * 86400):
                    try:
                        log_file.unlink()
                        removed_count += 1
                        logger.info(f"Removed old log file: {log_file}")
                    except Exception as e:
                        logger.error(f"Failed to remove log file {log_file}: {e}")
                        
            logger.info(f"Removed {removed_count} old log files")
            return removed_count
            
        except Exception as e:
            logger.error(f"Error while removing old log files: {e}")
            return 0
            
    def cleanup_all(self):
        """Perform all cleanup operations."""
        logger.info("Starting cleanup operations...")
        
        # Remove __pycache__ directories
        self.remove_pycache()
        
        # Clean temporary files
        self.clean_temp_files()
        
        # Clean temporary directories
        self.clean_temp_dirs()
        
        # Clean empty directories
        self.clean_empty_dirs()
        
        # Clean old log files (older than 30 days)
        self.clean_old_logs()
        
        logger.info("Cleanup operations completed") 