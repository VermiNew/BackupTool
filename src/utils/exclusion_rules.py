import re
from pathlib import Path
from typing import List, Dict, Union, Optional
import fnmatch
import logging

logger = logging.getLogger(__name__)


class ExclusionRules:
    """Manages file and directory exclusion rules.

    This class handles various types of exclusion rules for files and directories,
    including pattern matching, size limits, and specific paths.

    Attributes:
        patterns (List[str]): List of glob patterns to exclude
        min_size (int): Minimum file size in bytes (files smaller will be excluded)
        max_size (int): Maximum file size in bytes (files larger will be excluded)
        excluded_names (List[str]): List of specific file/directory names to exclude
        excluded_paths (List[str]): List of specific paths to exclude
    """

    def __init__(self):
        self.patterns: List[str] = []
        self.min_size: Optional[int] = None
        self.max_size: Optional[int] = None
        self.excluded_names: List[str] = []
        self.excluded_paths: List[str] = []
        self._compiled_patterns: List[re.Pattern] = []

    def add_pattern(self, pattern: str):
        """Add a glob pattern for exclusion.

        Args:
            pattern: Glob pattern (e.g. "*.tmp", "backup/**", "temp*")
                   Use /** to match all files and subdirectories in a directory
        """
        pattern = pattern.strip()
        if not pattern or pattern in self.patterns:
            return

        self.patterns.append(pattern)

        # Handle directory patterns with /**
        if "/**" in pattern:
            base_pattern = pattern.replace("/**", "")
            regex = fnmatch.translate(f"{base_pattern}/**/*")
        else:
            regex = fnmatch.translate(pattern)

        self._compiled_patterns.append(re.compile(regex))
        logger.debug(f"Added exclusion pattern: {pattern}")

    def add_size_limit(
        self, min_size: Optional[int] = None, max_size: Optional[int] = None
    ):
        """Set size limits for file exclusion.

        Args:
            min_size: Minimum file size in bytes (None for no limit)
            max_size: Maximum file size in bytes (None for no limit)
        """
        self.min_size = min_size
        self.max_size = max_size

    def add_excluded_name(self, name: str):
        """Add specific file/directory name to exclude.

        Args:
            name: Name of file or directory to exclude
        """
        name = name.strip()
        if name and name not in self.excluded_names:
            self.excluded_names.append(name)
            logger.debug(f"Added excluded name: {name}")

    def add_excluded_path(self, path: Union[str, Path]):
        """Add specific path to exclude.

        Args:
            path: Path to exclude (can be relative or absolute)
        """
        path_str = str(path).strip()
        if path_str and path_str not in self.excluded_paths:
            self.excluded_paths.append(path_str)
            logger.debug(f"Added excluded path: {path_str}")

    def should_exclude(self, path: Path, base_path: Optional[Path] = None) -> bool:
        """Check if path should be excluded based on rules.

        Args:
            path: Path to check
            base_path: Optional base path for relative path calculation

        Returns:
            True if path should be excluded, False otherwise
        """
        # Get relative path for pattern matching
        try:
            rel_path = str(path.relative_to(base_path) if base_path else path)
        except ValueError:
            # If relative_to fails, use full path
            rel_path = str(path)

        # Check name exclusions first (fastest)
        if path.name in self.excluded_names:
            logger.debug(f"Excluded by name: {path.name}")
            return True

        # Check path exclusions
        if any(excl in str(path) for excl in self.excluded_paths):
            logger.debug(f"Excluded by path: {path}")
            return True

        # Check patterns
        for pattern, compiled_pattern in zip(self.patterns, self._compiled_patterns):
            if compiled_pattern.match(rel_path):
                logger.debug(f"Excluded by pattern '{pattern}': {rel_path}")
                return True

        # Check size limits if file exists
        if path.is_file():
            try:
                size = path.stat().st_size
                if self.min_size is not None and size < self.min_size:
                    logger.debug(
                        f"Excluded by min size ({self.min_size}): {path}")
                    return True
                if self.max_size is not None and size > self.max_size:
                    logger.debug(
                        f"Excluded by max size ({self.max_size}): {path}")
                    return True
            except OSError:
                pass  # Ignore errors getting file size

        return False

    def to_dict(self) -> Dict:
        """Convert rules to dictionary format.

        Returns:
            Dictionary containing all exclusion rules
        """
        return {
            "patterns": self.patterns,
            "min_size": self.min_size,
            "max_size": self.max_size,
            "excluded_names": self.excluded_names,
            "excluded_paths": self.excluded_paths,
        }

    @classmethod
    def from_dict(cls, data: Dict) -> "ExclusionRules":
        """Create ExclusionRules instance from dictionary.

        Args:
            data: Dictionary containing exclusion rules

        Returns:
            New ExclusionRules instance
        """
        rules = cls()
        for pattern in data.get("patterns", []):
            rules.add_pattern(pattern)
        rules.add_size_limit(data.get("min_size"), data.get("max_size"))
        for name in data.get("excluded_names", []):
            rules.add_excluded_name(name)
        for path in data.get("excluded_paths", []):
            rules.add_excluded_path(path)
        return rules
