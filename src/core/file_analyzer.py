import os
import logging
from pathlib import Path
from typing import Dict, Callable, List, Optional
import fnmatch

logger = logging.getLogger(__name__)

class FileAnalyzer:
    """Analyzes files and directories for backup."""
    
    @staticmethod
    def get_files_info(
        path: Path, 
        progress_callback: Optional[Callable] = None,
        exclude_patterns: Optional[List[str]] = None
    ) -> Dict:
        """Get information about files in directory."""
        files_info = {}
        file_count = 0
        exclude_patterns = exclude_patterns or []

        # Helper function to check exclusions
        def is_excluded(file_path: Path) -> bool:
            try:
                # Get relative path from base directory
                rel_path = str(file_path.relative_to(path))
                rel_path_parts = Path(rel_path).parts
                
                for pattern in exclude_patterns:
                    pattern = pattern.strip()
                    if not pattern:
                        continue
                        
                    # Handle directory patterns (ending with /)
                    if pattern.endswith('/'):
                        dir_pattern = pattern.rstrip('/')
                        if any(part == dir_pattern for part in rel_path_parts):
                            return True
                    # Handle file patterns
                    else:
                        # Check if any part of the path matches the pattern
                        if any(fnmatch.fnmatch(part, pattern) for part in rel_path_parts):
                            return True
                return False
            except ValueError:
                return False

        try:
            # Count files considering exclusions
            total_files = sum(
                1 for f in path.rglob('*') 
                if f.is_file() and not is_excluded(f)
            )

            # Iterate through files
            for file_path in path.rglob('*'):
                if not file_path.is_file():
                    continue

                # Check if file should be excluded
                if is_excluded(file_path):
                    continue

                file_count += 1
                if progress_callback:
                    rel_path = file_path.relative_to(path)
                    progress_callback(f"Scanning: {rel_path} ({file_count}/{total_files} files)")

                try:
                    rel_path = str(file_path.relative_to(path))
                    stats = file_path.stat()
                    files_info[rel_path] = {
                        'size': stats.st_size,
                        'mtime': stats.st_mtime,
                    }
                except (OSError, ValueError) as e:
                    logger.warning(f"Failed to get info for {file_path}: {e}")
                    continue

        except Exception as e:
            logger.error(f"Error scanning directory {path}: {e}")
            raise

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