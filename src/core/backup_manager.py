import logging
from pathlib import Path
from typing import Dict, Tuple, Optional, Callable, List
from datetime import datetime
import json

from .file_analyzer import FileAnalyzer
from .file_handler import FileHandler, FileOperationError
from ..utils.helpers import get_drive_info, get_free_space, format_size

logger = logging.getLogger(__name__)

class BackupManager:
    """Manages backup operations."""
    
    def __init__(self):
        """Initialize backup manager."""
        self.source_path: Optional[Path] = None
        self.dest_path: Optional[Path] = None
        self.analyzer = FileAnalyzer()
        self.handler = FileHandler()
        self._running = True
        self.exclude_patterns: List[str] = []
        self.report_data = {
            'start_time': None,
            'end_time': None,
            'copied_files': [],
            'updated_files': [],
            'deleted_files': [],
            'errors': []
        }
        
    def set_exclude_patterns(self, patterns: List[str]):
        """Set patterns for files/directories to exclude."""
        self.exclude_patterns = patterns
        
    def stop(self):
        """Stop current operation."""
        self._running = False
        
    def save_report(self):
        """Save backup report to file."""
        if not self.report_data['start_time']:
            return
            
        report_path = self.dest_path / 'backup_report.json'
        try:
            with open(report_path, 'w') as f:
                json.dump(self.report_data, f, indent=2, default=str)
        except Exception as e:
            logger.error(f"Failed to save report: {e}")

    def prepare_backup(self, source_path: str, dest_path: str) -> Tuple[bool, str, Dict]:
        """Prepare backup operation."""
        self.report_data['start_time'] = datetime.now()
        
        # Validate paths
        valid, message = self.analyze_paths(source_path, dest_path)
        if not valid:
            self.report_data['errors'].append({"time": datetime.now(), "error": message})
            return False, message, {}
            
        # Check available space
        try:
            source_size = sum(
                f.stat().st_size for f in Path(source_path).rglob('*') 
                if f.is_file() and not any(f.match(p) for p in self.exclude_patterns)
            )
            dest_free = get_free_space(self.dest_path.parent)
            
            if dest_free < source_size:
                msg = f"Insufficient space. Need: {format_size(source_size)}, Available: {format_size(dest_free)}"
                self.report_data['errors'].append({"time": datetime.now(), "error": msg})
                return False, msg, {}
                
        except Exception as e:
            self.report_data['errors'].append({"time": datetime.now(), "error": str(e)})
            return False, str(e), {}
            
        # Analyze differences
        try:
            differences = self.analyze_differences()
            total_files = len(differences['to_copy']) + len(differences['to_update'])
            if total_files == 0:
                return True, "No files need to be updated", differences
            return True, f"Found {total_files} files to process", differences
        except Exception as e:
            self.report_data['errors'].append({"time": datetime.now(), "error": str(e)})
            return False, f"Error analyzing differences: {str(e)}", {}

    def analyze_paths(self, source_path: str, dest_path: str) -> Tuple[bool, str]:
        """Validate source and destination paths."""
        try:
            self.source_path = Path(source_path)
            self.dest_path = Path(dest_path)
            
            if not self.source_path.exists():
                return False, "Source path does not exist"
                
            if not self.source_path.is_dir():
                return False, "Source path must be a directory"
                
            if self.dest_path.exists() and not self.dest_path.is_dir():
                return False, "Destination path must be a directory"
                
            # Check if paths are the same
            if self.source_path.resolve() == self.dest_path.resolve():
                return False, "Source and destination paths cannot be the same"
                
            # Check if destination is subdirectory of source
            if str(self.dest_path).startswith(str(self.source_path)):
                return False, "Destination cannot be a subdirectory of source"
                
            return True, "Paths validated successfully"
            
        except Exception as e:
            logger.error(f"Path analysis failed: {e}")
            return False, f"Path analysis failed: {str(e)}"
            
    def analyze_differences(self, progress_callback: Callable = None) -> Dict:
        """Analyze differences between directories."""
        if progress_callback:
            progress_callback("Scanning source directory...")
            
        source_files = self.analyzer.get_files_info(
            self.source_path,
            progress_callback,
            self.exclude_patterns
        )
        
        if progress_callback:
            progress_callback("Scanning destination directory...")
            
        dest_files = self.analyzer.get_files_info(
            self.dest_path,
            progress_callback,
            self.exclude_patterns
        ) if self.dest_path.exists() else {}
        
        if progress_callback:
            progress_callback("Analyzing differences...")
            
        return self.analyzer.analyze_differences(source_files, dest_files)
            
    def perform_backup(self, differences: Dict, progress_callback: Callable = None) -> bool:
        """Perform backup operation."""
        try:
            self._running = True
            self.dest_path.mkdir(parents=True, exist_ok=True)
            
            # Delete unnecessary files
            for rel_path in differences['to_delete']:
                try:
                    success, message = self.handler.delete_path(self.dest_path / rel_path)
                    if success:
                        self.report_data['deleted_files'].append({
                            "path": str(rel_path),
                            "time": datetime.now()
                        })
                    else:
                        logger.error(f"Failed to delete {rel_path}: {message}")
                        self.report_data['errors'].append({
                            "time": datetime.now(),
                            "error": f"Failed to delete {rel_path}: {message}"
                        })
                except Exception as e:
                    logger.error(f"Failed to delete {rel_path}: {e}")
                    self.report_data['errors'].append({
                        "time": datetime.now(),
                        "error": f"Failed to delete {rel_path}: {e}"
                    })

            # Copy and update files
            total_copied = 0
            _, chunk_size = get_drive_info(self.dest_path)
            self.handler.CHUNK_SIZE = chunk_size
            
            for rel_path in differences['to_copy'] + differences['to_update']:
                if not self._running:
                    logger.info("Backup operation cancelled")
                    return False
                    
                try:
                    src_file = self.source_path / rel_path
                    dest_file = self.dest_path / rel_path
                    
                    def file_progress(copied_size):
                        if progress_callback:
                            progress_callback(total_copied + copied_size, rel_path)
                    
                    success, message = self.handler.copy_file(src_file, dest_file, file_progress)
                    if success:
                        total_copied += src_file.stat().st_size
                        
                        # Log copied/updated file
                        file_info = {
                            "path": str(rel_path),
                            "size": src_file.stat().st_size,
                            "time": datetime.now()
                        }
                        
                        if rel_path in differences['to_copy']:
                            self.report_data['copied_files'].append(file_info)
                        else:
                            self.report_data['updated_files'].append(file_info)
                    else:
                        logger.error(f"Failed to copy {rel_path}: {message}")
                        self.report_data['errors'].append({
                            "time": datetime.now(),
                            "error": f"Failed to copy {rel_path}: {message}"
                        })
                except Exception as e:
                    logger.error(f"Unexpected error copying {rel_path}: {e}")
                    self.report_data['errors'].append({
                        "time": datetime.now(),
                        "error": f"Unexpected error copying {rel_path}: {e}"
                    })
            
            self.report_data['end_time'] = datetime.now()
            self.save_report()
            return True
            
        except Exception as e:
            logger.error(f"Backup operation failed: {e}")
            self.report_data['errors'].append({
                "time": datetime.now(),
                "error": f"Backup operation failed: {e}"
            })
            self.report_data['end_time'] = datetime.now()
            self.save_report()
            raise 