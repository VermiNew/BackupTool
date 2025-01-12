import os
import psutil
from pathlib import Path
from typing import Tuple, Dict, Optional
from datetime import datetime

def get_drive_info(path: Path) -> Tuple[str, int]:
    """Get drive type and optimal buffer size."""
    try:
        if os.name == 'nt':  # Windows
            import win32file
            drive = os.path.splitdrive(path)[0]
            drive_type = win32file.GetDriveType(drive)
            if drive_type == win32file.DRIVE_FIXED:
                return 'ssd', 1024 * 1024  # 1MB for SSD
            return 'hdd', 8192  # 8KB for HDD
        else:  # Linux/Unix
            # Simple check based on device name
            device = psutil.disk_partitions()[0].device
            if 'nvme' in device or 'ssd' in device:
                return 'ssd', 1024 * 1024
            return 'hdd', 8192
    except:
        return 'unknown', 65536  # 64KB default

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