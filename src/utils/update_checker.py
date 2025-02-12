"""Module for checking application updates."""
import subprocess
import logging
from pathlib import Path
from typing import Tuple, Optional

logger = logging.getLogger(__name__)

class UpdateChecker:
    """Checks for application updates using git."""
    
    def __init__(self, app_dir: Path = None):
        """Initialize update checker.
        
        Args:
            app_dir: Application root directory. Defaults to current directory.
        """
        self.app_dir = app_dir or Path.cwd()
        self._git_available = self._check_git_available()
        
    def _check_git_available(self) -> bool:
        """Check if git is available in the system.
        
        Returns:
            bool: True if git is available, False otherwise
        """
        try:
            subprocess.run(
                ['git', '--version'], 
                capture_output=True, 
                check=True
            )
            return True
        except (subprocess.SubprocessError, FileNotFoundError):
            logger.warning("Git is not available in the system")
            return False
            
    def _get_current_version(self) -> Optional[str]:
        """Get current version from git.
        
        Returns:
            Current commit hash or None if failed
        """
        if not self._git_available:
            return None
            
        try:
            result = subprocess.run(
                ['git', 'rev-parse', 'HEAD'],
                cwd=self.app_dir,
                capture_output=True,
                text=True,
                check=True
            )
            return result.stdout.strip()
        except subprocess.SubprocessError as e:
            logger.error(f"Failed to get current version: {e}")
            return None
            
    def _get_remote_version(self) -> Optional[str]:
        """Get latest version from remote repository.
        
        Returns:
            Latest commit hash or None if failed
        """
        if not self._git_available:
            return None
            
        try:
            # Fetch updates from remote
            subprocess.run(
                ['git', 'fetch'],
                cwd=self.app_dir,
                capture_output=True,
                check=True
            )
            
            # Get remote HEAD hash
            result = subprocess.run(
                ['git', 'rev-parse', 'origin/main'],
                cwd=self.app_dir,
                capture_output=True,
                text=True,
                check=True
            )
            return result.stdout.strip()
        except subprocess.SubprocessError as e:
            logger.error(f"Failed to get remote version: {e}")
            return None
            
    def check_for_updates(self) -> Tuple[bool, str]:
        """Check if updates are available.
        
        Returns:
            Tuple containing:
                - bool: True if updates available, False otherwise
                - str: Status message
        """
        if not self._git_available:
            return False, "Git is not available - cannot check for updates"
            
        current = self._get_current_version()
        if not current:
            return False, "Failed to get current version"
            
        remote = self._get_remote_version()
        if not remote:
            return False, "Failed to check remote version"
            
        if current != remote:
            return True, f"Update available: {current[:7]} → {remote[:7]}"
            
        return False, "Application is up to date" 