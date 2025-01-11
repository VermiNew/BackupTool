import os
import logging
from pathlib import Path
from typing import Dict, Tuple, Callable

logger = logging.getLogger(__name__)

class FileAnalyzer:
    """Analyzes files and directories for backup purposes."""
    
    @staticmethod
    def get_files_info(path: Path, progress_callback: Callable = None) -> Dict:
        """Get information about all files in the directory."""
        files_info = {}
        file_count = 0
        
        # First count total files
        total_files = sum(1 for _ in path.rglob('*') if Path(_).is_file())
        
        for file_path in path.rglob('*'):
            if file_path.is_file():
                file_count += 1
                # Emit current path being scanned
                if progress_callback:
                    rel_path = file_path.relative_to(path)
                    progress_callback(f"Scanning: {rel_path} ({file_count}/{total_files} files)")
                
                rel_path = file_path.relative_to(path)
                stats = file_path.stat()
                files_info[str(rel_path)] = {
                    'size': stats.st_size,
                    'mtime': stats.st_mtime,
                }
                
        return files_info

    @staticmethod
    def needs_update(src_info: Dict, dest_info: Dict) -> bool:
        """Check if file needs to be updated based on size and modification time."""
        if src_info['size'] != dest_info['size']:
            return True
        return abs(src_info['mtime'] - dest_info['mtime']) > 2

    @staticmethod
    def analyze_differences(source_files: Dict, dest_files: Dict) -> Dict:
        """Compare source and destination files to find differences."""
        differences = {
            'to_copy': [],    # New files to copy
            'to_update': [],  # Files to update
            'to_delete': [],  # Files to remove
            'unchanged': []   # Files that are the same
        }
        
        # Find new and modified files
        for rel_path, src_info in source_files.items():
            if rel_path not in dest_files:
                differences['to_copy'].append(rel_path)
            else:
                if FileAnalyzer.needs_update(src_info, dest_files[rel_path]):
                    differences['to_update'].append(rel_path)
                else:
                    differences['unchanged'].append(rel_path)

        # Find files to delete
        for rel_path in dest_files:
            if rel_path not in source_files:
                differences['to_delete'].append(rel_path)

        return differences 