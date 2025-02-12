import logging
from pathlib import Path
from typing import Dict, Tuple, Optional, Callable, List
from datetime import datetime
import json
import sys

from .file_analyzer import FileAnalyzer
from .file_handler import FileHandler, FileOperationError
from ..utils.helpers import get_free_space, format_size
from ..utils.hash_utils import get_file_signature

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
            
    def _compare_files(self, source_file: Path, dest_file: Path) -> Tuple[bool, str]:
        """Compare two files to determine if they are identical.
        
        Performs checks in order of increasing complexity:
        1. Basic attributes (size, time)
        2. File permissions
        3. Content comparison
        4. System attributes (Windows)
        
        Args:
            source_file: Original file path
            dest_file: File to compare against
            
        Returns:
            (is_different, reason): Tuple indicating if files differ and why
        """
        try:
            src_stat = source_file.stat()
            dst_stat = dest_file.stat()
            
            if src_stat.st_size != dst_stat.st_size:
                return True, "Different file size"
                
            # Use 2-second tolerance for filesystem differences
            if abs(src_stat.st_mtime - dst_stat.st_mtime) > 2:
                return True, "Different modification time"
                
            if hasattr(src_stat, 'st_mode'):
                if src_stat.st_mode != dst_stat.st_mode:
                    return True, "Different file permissions"
            
            # Compare content in chunks to minimize memory usage
            CHUNK_SIZE = 8192  # 8KB chunks for efficient memory usage
            with open(source_file, 'rb') as src, open(dest_file, 'rb') as dst:
                while True:
                    src_chunk = src.read(CHUNK_SIZE)
                    dst_chunk = dst.read(CHUNK_SIZE)
                    
                    if src_chunk != dst_chunk:
                        return True, "Different file content"
                    
                    if not src_chunk:
                        break
            
            # Check Windows-specific attributes
            try:
                # On Windows check attributes like hidden, system, readonly
                if sys.platform == 'win32':
                    import win32api
                    import win32con
                    src_attrs = win32api.GetFileAttributes(str(source_file))
                    dst_attrs = win32api.GetFileAttributes(str(dest_file))
                    
                    # Check only important attributes (hidden, system, readonly)
                    important_attrs = (
                        win32con.FILE_ATTRIBUTE_HIDDEN |
                        win32con.FILE_ATTRIBUTE_SYSTEM |
                        win32con.FILE_ATTRIBUTE_READONLY
                    )
                    if (src_attrs & important_attrs) != (dst_attrs & important_attrs):
                        return True, "Different system attributes"
            except ImportError:
                # If we don't have access to win32api, skip these tests
                pass
                
            return False, "Files are identical"
            
        except Exception as e:
            logger.error(f"Error comparing files: {e}")
            return True, f"Comparison error: {str(e)}"

    def analyze_differences(self, progress_callback: Callable = None) -> Dict:
        """Analyze differences between source and destination directories.
        
        Args:
            progress_callback: Function to report progress
            
        Returns:
            Dictionary with lists of files to copy, update, and delete
        """
        differences = {
            'to_copy': [],
            'to_update': [],
            'to_delete': []
        }
        
        if progress_callback:
            progress_callback("Analyzing files...")
        
        # Process source directory
        total_files = 0
        for source_file in self.source_path.rglob('*'):
            if not self._running:
                break
                
            # Skip directories and excluded files
            if not source_file.is_file() or any(source_file.match(p) for p in self.exclude_patterns):
                continue
                
            total_files += 1
            if total_files % 100 == 0 and progress_callback:
                progress_callback(f"Analyzed {total_files} files...")
                
            # Calculate relative path
            rel_path = source_file.relative_to(self.source_path)
            dest_file = self.dest_path / rel_path
            
            # Check if file exists in destination
            if not dest_file.exists():
                differences['to_copy'].append(str(rel_path))
            else:
                # Detailed file comparison
                is_different, reason = self._compare_files(source_file, dest_file)
                if is_different:
                    logger.debug(f"File {rel_path} needs update: {reason}")
                    differences['to_update'].append(str(rel_path))
        
        # Find deleted files
        if self.dest_path.exists():
            for dest_file in self.dest_path.rglob('*'):
                if not self._running:
                    break
                    
                if not dest_file.is_file():
                    continue
                    
                rel_path = dest_file.relative_to(self.dest_path)
                source_file = self.source_path / rel_path
                
                if not source_file.exists():
                    differences['to_delete'].append(str(rel_path))
        
        return differences
            
    def perform_backup(self, differences: Dict, progress_callback: Callable = None) -> bool:
        """Execute backup operation based on analyzed differences.
        
        Args:
            differences: Dictionary with files to process
            progress_callback: Function to report progress
            
        Returns:
            True if backup completed successfully
        """
        try:
            self._running = True
            self.dest_path.mkdir(parents=True, exist_ok=True)
            
            total_files = len(differences['to_copy']) + len(differences['to_update']) + len(differences['to_delete'])
            processed_files = 0
            
            # Delete unnecessary files first
            for rel_path in differences['to_delete']:
                if not self._running:
                    return False
                    
                try:
                    file_to_delete = self.dest_path / rel_path
                    if file_to_delete.exists():
                        file_to_delete.unlink()
                        self.report_data['deleted_files'].append(str(rel_path))
                except Exception as e:
                    logger.error(f"Failed to delete {rel_path}: {e}")
                    self.report_data['errors'].append({
                        "time": datetime.now(),
                        "error": f"Delete error {rel_path}: {str(e)}"
                    })
                
                processed_files += 1
                if progress_callback:
                    progress_callback(f"Progress: {processed_files}/{total_files} files...")

            # Copy and update files
            for operation in ['to_copy', 'to_update']:
                for rel_path in differences[operation]:
                    if not self._running:
                        return False
                        
                    try:
                        src_file = self.source_path / rel_path
                        dest_file = self.dest_path / rel_path
                        
                        # Ensure destination directory exists
                        dest_file.parent.mkdir(parents=True, exist_ok=True)
                        
                        # Copy file
                        self.handler.CHUNK_SIZE = 1024 * 1024  # 1MB chunks
                        success, message = self.handler.copy_file(src_file, dest_file)
                        
                        if success:
                            file_info = {
                                "path": str(rel_path),
                                "time": datetime.now(),
                                "size": src_file.stat().st_size
                            }
                            
                            if operation == 'to_copy':
                                self.report_data['copied_files'].append(file_info)
                            else:
                                self.report_data['updated_files'].append(file_info)
                        else:
                            raise Exception(message)
                            
                    except Exception as e:
                        logger.error(f"Error during {operation} for {rel_path}: {e}")
                        self.report_data['errors'].append({
                            "time": datetime.now(),
                            "error": f"Error {operation} {rel_path}: {str(e)}"
                        })
                    
                    processed_files += 1
                    if progress_callback:
                        progress_callback(f"Progress: {processed_files}/{total_files} files...")
            
            self.report_data['end_time'] = datetime.now()
            self.save_report()
            return True
            
        except Exception as e:
            logger.error(f"Backup failed: {e}")
            self.report_data['errors'].append({
                "time": datetime.now(),
                "error": f"Backup failed: {str(e)}"
            })
            self.report_data['end_time'] = datetime.now()
            self.save_report()
            return False