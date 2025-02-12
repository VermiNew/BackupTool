import logging
from pathlib import Path
from typing import List

logger = logging.getLogger(__name__)

class FileAnalyzer:
    """Analyzes files for backup operations."""
    
    @staticmethod
    def are_files_identical(source: Path, dest: Path) -> bool:
        """Check if two files are exactly the same.
        
        Compares:
        - File size
        - Modification time
        - File permissions
        """
        try:
            if not source.exists() or not dest.exists():
                return False
                
            src_stat = source.stat()
            dst_stat = dest.stat()
            
            # Compare basic attributes
            return (
                src_stat.st_size == dst_stat.st_size and
                src_stat.st_mode == dst_stat.st_mode and
                abs(src_stat.st_mtime - dst_stat.st_mtime) <= 2  # 2-second tolerance
            )
        except Exception as e:
            logger.error(f"Error comparing files {source} and {dest}: {e}")
            return False
    
    def get_file_list(self, directory: Path, exclude_patterns: List[str] = None) -> List[Path]:
        """Get list of files in directory, excluding patterns."""
        files = []
        try:
            for file_path in directory.rglob('*'):
                if not file_path.is_file():
                    continue
                    
                if exclude_patterns and any(file_path.match(p) for p in exclude_patterns):
                    continue
                    
                files.append(file_path)
        except Exception as e:
            logger.error(f"Error scanning directory {directory}: {e}")
            
        return files