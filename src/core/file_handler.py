import os
import logging
from pathlib import Path
from typing import Callable

logger = logging.getLogger(__name__)

class FileHandler:
    """Handles file operations for backup process."""
    
    CHUNK_SIZE = 1024 * 1024  # 1MB chunks for file copying

    @staticmethod
    def copy_file(src_path: Path, dest_path: Path, progress_callback: Callable = None):
        """Copy file with metadata preservation."""
        try:
            # Create parent directories if needed
            dest_path.parent.mkdir(parents=True, exist_ok=True)

            # Copy file content
            total_size = src_path.stat().st_size
            copied_size = 0

            with src_path.open('rb') as src, dest_path.open('wb') as dest:
                while True:
                    chunk = src.read(FileHandler.CHUNK_SIZE)
                    if not chunk:
                        break
                    dest.write(chunk)
                    
                    if progress_callback:
                        copied_size += len(chunk)
                        progress = (copied_size / total_size) * 100
                        progress_callback(progress)

            # Copy metadata
            os.utime(dest_path, (src_path.stat().st_atime, src_path.stat().st_mtime))
            
        except Exception as e:
            logger.error(f"Error copying {src_path}: {e}")
            raise

    @staticmethod
    def delete_file(path: Path):
        """Safely delete a file."""
        try:
            path.unlink()
            logger.info(f"Deleted: {path}")
        except Exception as e:
            logger.error(f"Error deleting {path}: {e}")
            raise 