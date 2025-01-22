import os
import psutil
from pathlib import Path
from typing import Tuple, Dict, Optional
from datetime import datetime

def get_free_space(path: Path) -> int:
    """Get free space in bytes for the given path."""
    return psutil.disk_usage(str(path)).free

def format_size(size: int) -> str:
    """Format size in bytes to human readable format."""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size < 1024:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"

def get_file_info(path: str) -> Optional[Dict]:
    """Get file information.
    
    Args:
        path: Path to the file
        
    Returns:
        Dictionary containing file information or None if file doesn't exist
    """
    try:
        file_path = Path(path)
        if not file_path.exists():
            return None
            
        stats = file_path.stat()
        return {
            'size': stats.st_size,
            'created': datetime.fromtimestamp(stats.st_ctime).strftime('%Y-%m-%d %H:%M:%S'),
            'modified': datetime.fromtimestamp(stats.st_mtime).strftime('%Y-%m-%d %H:%M:%S'),
            'is_dir': file_path.is_dir()
        }
    except Exception:
        return None 