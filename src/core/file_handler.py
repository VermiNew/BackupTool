import os
import logging
import shutil
from pathlib import Path
from typing import Tuple

logger = logging.getLogger(__name__)

class FileOperationError(Exception):
    """Custom exception for file operations"""
    pass

class FileHandler:
    """Handles file operations with exact 1:1 copying."""
    
    def copy_file(self, source: Path, dest: Path) -> Tuple[bool, str]:
        """Copy file with all metadata preserved.
        
        Uses shutil.copy2 for exact 1:1 copy including:
        - File content
        - Permissions
        - Timestamps
        - File flags
        """
        try:
            # Create parent directories if they don't exist
            dest.parent.mkdir(parents=True, exist_ok=True)
            
            # Perform exact copy
            shutil.copy2(source, dest)
            return True, "Success"
            
        except Exception as e:
            logger.error(f"Failed to copy {source} to {dest}: {e}")
            return False, str(e)
    
    def delete_file(self, path: Path) -> Tuple[bool, str]:
        """Safely delete a file."""
        try:
            if path.exists():
                path.unlink()
            return True, "Success"
        except Exception as e:
            logger.error(f"Failed to delete {path}: {e}")
            return False, str(e)

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