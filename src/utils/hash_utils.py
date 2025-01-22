import hashlib
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


def calculate_file_hash(file_path: Path, chunk_size: int = 4096) -> Optional[str]:
    """Calculate SHA-256 hash of a file.

    Args:
        file_path: Path to the file
        chunk_size: Size of chunks to read (default: 4KB)

    Returns:
        File hash as string or None if file cannot be read

    Example:
        >>> file_hash = calculate_file_hash(Path("example.txt"))
        >>> if file_hash:
        ...     print(f"File hash: {file_hash}")
        ... else:
        ...     print("Failed to calculate hash")
    """
    try:
        sha256_hash = hashlib.sha256()
        with file_path.open("rb") as f:
            # Read file in chunks to handle large files efficiently
            for byte_block in iter(lambda: f.read(chunk_size), b""):
                sha256_hash.update(byte_block)
        return sha256_hash.hexdigest()
    except Exception as e:
        logger.warning(f"Failed to calculate hash for {file_path}: {e}")
        return None


def verify_file_hash(file_path: Path, expected_hash: str, chunk_size: int = 4096) -> bool:
    """Verify if file matches expected hash.

    Args:
        file_path: Path to the file
        expected_hash: Expected SHA-256 hash
        chunk_size: Size of chunks to read (default: 4KB)

    Returns:
        True if file hash matches expected hash, False otherwise

    Example:
        >>> is_valid = verify_file_hash(Path("example.txt"), "abc123...")
        >>> print("File is valid" if is_valid else "File has changed")
    """
    current_hash = calculate_file_hash(file_path, chunk_size)
    if not current_hash:
        return False
    return current_hash.lower() == expected_hash.lower()


def get_file_signature(file_path: Path) -> Optional[dict]:
    """Get file signature including hash and metadata.

    Args:
        file_path: Path to the file

    Returns:
        Dictionary containing file signature or None if file cannot be read

    Example:
        >>> signature = get_file_signature(Path("example.txt"))
        >>> if signature:
        ...     print(f"Hash: {signature['hash']}")
        ...     print(f"Size: {signature['size']}")
        ...     print(f"Modified: {signature['modified']}")
    """
    try:
        stats = file_path.stat()
        file_hash = calculate_file_hash(file_path)
        if not file_hash:
            return None

        return {
            'hash': file_hash,
            'size': stats.st_size,
            'modified': stats.st_mtime,
            'created': stats.st_ctime
        }
    except Exception as e:
        logger.warning(f"Failed to get file signature for {file_path}: {e}")
        return None 