import os
import logging
from pathlib import Path
from typing import Callable, Tuple

logger = logging.getLogger(__name__)

class FileOperationError(Exception):
    """Custom exception for file operations"""
    pass

class FileHandler:
    """Handles file operations for backup process."""
    
    CHUNK_SIZE = 1024 * 1024  # 1MB chunks for file copying

    @staticmethod
    def copy_file(src_path: Path, dest_path: Path, progress_callback: Callable = None) -> Tuple[bool, str]:
        """
        Copy file with metadata preservation.
        Returns: Tuple[success: bool, message: str]
        """
        try:
            # Verify source file exists and is readable
            if not src_path.exists():
                raise FileOperationError(f"Source file does not exist: {src_path}")
            if not os.access(src_path, os.R_OK):
                raise FileOperationError(f"Source file is not readable: {src_path}")

            # Create parent directories if needed
            dest_path.parent.mkdir(parents=True, exist_ok=True)

            # Verify write permissions
            if dest_path.exists() and not os.access(dest_path, os.W_OK):
                raise FileOperationError(f"Destination file is not writable: {dest_path}")

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
                        progress_callback(copied_size)

            # Copy metadata
            os.utime(dest_path, (src_path.stat().st_atime, src_path.stat().st_mtime))
            
            return True, "File copied successfully"

        except FileOperationError as e:
            logger.error(f"File operation error: {e}")
            return False, str(e)
        except Exception as e:
            logger.error(f"Error copying {src_path}: {e}")
            return False, f"Unexpected error: {str(e)}"

    @staticmethod
    def delete_path(path: Path) -> Tuple[bool, str]:
        """
        Safely delete a file or directory.
        Returns: Tuple[success: bool, message: str]
        """
        try:
            if not path.exists():
                return True, "Path already deleted"
                
            if not os.access(path, os.W_OK):
                raise FileOperationError(f"Path is not writable: {path}")
                
            if path.is_file():
                path.unlink()
                logger.info(f"Deleted file: {path}")
            elif path.is_dir():
                # Usuń zawartość katalogu rekurencyjnie
                for item in path.rglob('*'):
                    if item.is_file():
                        if not os.access(item, os.W_OK):
                            raise FileOperationError(f"File is not writable: {item}")
                        item.unlink()
                    elif item.is_dir():
                        if not os.access(item, os.W_OK):
                            raise FileOperationError(f"Directory is not writable: {item}")
                        item.rmdir()
                # Usuń pusty katalog
                path.rmdir()
                logger.info(f"Deleted directory: {path}")
                
            return True, "Path deleted successfully"
            
        except FileOperationError as e:
            logger.error(f"File operation error: {e}")
            return False, str(e)
        except Exception as e:
            logger.error(f"Error deleting {path}: {e}")
            return False, f"Unexpected error: {str(e)}" 