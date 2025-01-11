import logging
from pathlib import Path
from typing import Dict, Tuple, Optional, Callable

from .file_analyzer import FileAnalyzer
from .file_handler import FileHandler
from ..utils.helpers import get_drive_info, get_free_space, format_size

logger = logging.getLogger(__name__)

class BackupManager:
    """Manages the backup process."""
    
    def __init__(self):
        self.source_path: Optional[Path] = None
        self.dest_path: Optional[Path] = None
        self.analyzer = FileAnalyzer()
        self.handler = FileHandler()
        self._running = True  # Flaga do kontroli przerwania operacji
        
    def stop(self):
        """Stop current operation."""
        self._running = False

    def prepare_backup(self, source_path: str, dest_path: str) -> Tuple[bool, str, Dict]:
        """Prepare backup by analyzing paths and differences."""
        # Validate paths
        valid, message = self.analyze_paths(source_path, dest_path)
        if not valid:
            return False, message, {}
            
        # Check available space
        source_size = sum(f.stat().st_size for f in Path(source_path).rglob('*') if f.is_file())
        dest_free = get_free_space(self.dest_path.parent)
        
        if dest_free < source_size:
            return False, f"Insufficient space. Need: {format_size(source_size)}, Available: {format_size(dest_free)}", {}
            
        # Analyze differences
        try:
            differences = self.analyze_differences()
            total_files = len(differences['to_copy']) + len(differences['to_update'])
            if total_files == 0:
                return True, "No files need to be updated", differences
            return True, f"Found {total_files} files to process", differences
        except Exception as e:
            return False, f"Error analyzing differences: {str(e)}", {}

    def analyze_paths(self, source_path: str, dest_path: str) -> Tuple[bool, str]:
        """Analyze and validate source and destination paths."""
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
        """Analyze differences between source and destination."""
        if progress_callback:
            progress_callback("Scanning source directory...")
        source_files = self.analyzer.get_files_info(
            self.source_path,
            progress_callback
        )
        
        if progress_callback:
            progress_callback("Scanning destination directory...")
        dest_files = self.analyzer.get_files_info(
            self.dest_path,
            progress_callback
        ) if self.dest_path.exists() else {}
        
        if progress_callback:
            progress_callback("Analyzing differences...")
        return self.analyzer.analyze_differences(source_files, dest_files)
            
    def perform_backup(self, differences: Dict, progress_callback: Callable = None) -> bool:
        """Perform the backup operation."""
        try:
            self._running = True  # Reset flag
            # Create destination directory if needed
            self.dest_path.mkdir(parents=True, exist_ok=True)
            
            # Delete unnecessary files first
            for rel_path in differences['to_delete']:
                self.handler.delete_file(self.dest_path / rel_path)
                
            # Copy new files and update existing ones
            total_operations = len(differences['to_copy']) + len(differences['to_update'])
            completed = 0
            
            # Get optimal chunk size based on drive type
            _, chunk_size = get_drive_info(self.dest_path)
            self.handler.CHUNK_SIZE = chunk_size
            
            for rel_path in differences['to_copy'] + differences['to_update']:
                if not self._running:
                    logger.info("Backup operation cancelled")
                    return False
                src_file = self.source_path / rel_path
                dest_file = self.dest_path / rel_path
                
                self.handler.copy_file(
                    src_file, 
                    dest_file,
                    lambda p: progress_callback(
                        (completed + p/100) / total_operations * 100
                    ) if progress_callback else None
                )
                
                completed += 1
                    
            return True
            
        except Exception as e:
            logger.error(f"Backup operation failed: {e}")
            raise 