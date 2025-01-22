import logging
import gc
import psutil
import os
from typing import Optional, Dict, Any
from threading import Lock
import time

logger = logging.getLogger(__name__)

class MemoryManager:
    """Manages memory usage across the application.
    
    This class provides centralized memory management including:
    - Memory usage monitoring
    - Automatic garbage collection
    - Cache management
    - Memory limits enforcement
    """
    
    # Memory thresholds (in bytes)
    DEFAULT_MEMORY_LIMIT = 1024 * 1024 * 1024  # 1GB
    WARNING_THRESHOLD = 0.8  # 80% of limit
    CRITICAL_THRESHOLD = 0.9  # 90% of limit
    
    # Cache settings
    DEFAULT_CACHE_SIZE = 10000
    CACHE_CLEANUP_RATIO = 0.2  # Remove 20% when cleaning
    
    # GC settings
    GC_CHECK_INTERVAL = 60  # Check every 60 seconds
    
    def __init__(self, memory_limit: Optional[int] = None):
        """Initialize memory manager.
        
        Args:
            memory_limit: Optional memory limit in bytes
        """
        self.memory_limit = memory_limit or self.DEFAULT_MEMORY_LIMIT
        self._lock = Lock()
        self._caches: Dict[str, Dict] = {}
        self._last_gc_time = time.time()
        self._process = psutil.Process(os.getpid())
        
        # Enable automatic garbage collection
        gc.enable()
        logger.info(f"Memory manager initialized with {self.memory_limit / 1024 / 1024:.1f}MB limit")
        
    def register_cache(self, name: str, cache_dict: Dict, max_size: Optional[int] = None):
        """Register a cache for management.
        
        Args:
            name: Unique name for the cache
            cache_dict: Dictionary used as cache
            max_size: Maximum number of items (default: DEFAULT_CACHE_SIZE)
        """
        with self._lock:
            self._caches[name] = {
                'dict': cache_dict,
                'max_size': max_size or self.DEFAULT_CACHE_SIZE
            }
        logger.debug(f"Registered cache '{name}' with max size {max_size or self.DEFAULT_CACHE_SIZE}")
        
    def unregister_cache(self, name: str):
        """Unregister a cache.
        
        Args:
            name: Name of cache to unregister
        """
        with self._lock:
            if name in self._caches:
                del self._caches[name]
                logger.debug(f"Unregistered cache '{name}'")
                
    def get_memory_usage(self) -> Dict[str, Any]:
        """Get current memory usage statistics.
        
        Returns:
            Dictionary containing memory usage information
        """
        usage = self._process.memory_info()
        return {
            'rss': usage.rss,  # Resident Set Size
            'vms': usage.vms,  # Virtual Memory Size
            'percent': usage.rss / self.memory_limit * 100,
            'limit': self.memory_limit,
            'cache_sizes': {
                name: len(cache['dict']) 
                for name, cache in self._caches.items()
            }
        }
        
    def check_memory(self) -> bool:
        """Check memory usage and perform cleanup if needed.
        
        Returns:
            True if memory usage is OK, False if critical
        """
        with self._lock:
            current_usage = self._process.memory_info().rss
            usage_ratio = current_usage / self.memory_limit
            
            # Log memory usage at debug level
            logger.debug(
                f"Memory usage: {current_usage / 1024 / 1024:.1f}MB "
                f"({usage_ratio * 100:.1f}% of limit)"
            )
            
            # Check if it's time for garbage collection
            current_time = time.time()
            if current_time - self._last_gc_time > self.GC_CHECK_INTERVAL:
                self._force_garbage_collection()
                self._last_gc_time = current_time
            
            # If usage is above warning threshold, clean caches
            if usage_ratio > self.WARNING_THRESHOLD:
                logger.warning(
                    f"Memory usage above warning threshold "
                    f"({usage_ratio * 100:.1f}% of limit)"
                )
                self._clean_all_caches()
                
            # If still above critical threshold after cleanup
            if usage_ratio > self.CRITICAL_THRESHOLD:
                logger.error(
                    f"Memory usage critical "
                    f"({usage_ratio * 100:.1f}% of limit)"
                )
                return False
                
            return True
            
    def _force_garbage_collection(self):
        """Force garbage collection."""
        collected = gc.collect()
        logger.debug(f"Garbage collection: {collected} objects collected")
        
    def _clean_cache(self, cache_dict: Dict, max_size: int):
        """Clean a single cache if it exceeds maximum size.
        
        Args:
            cache_dict: Dictionary used as cache
            max_size: Maximum allowed size
        """
        if len(cache_dict) > max_size:
            # Remove oldest entries (assuming they're least likely to be used)
            remove_count = int(max_size * self.CACHE_CLEANUP_RATIO)
            for _ in range(remove_count):
                if cache_dict:
                    cache_dict.popitem()
                    
    def _clean_all_caches(self):
        """Clean all registered caches."""
        with self._lock:
            for name, cache_info in self._caches.items():
                cache_dict = cache_info['dict']
                max_size = cache_info['max_size']
                initial_size = len(cache_dict)
                self._clean_cache(cache_dict, max_size)
                final_size = len(cache_dict)
                if initial_size != final_size:
                    logger.debug(
                        f"Cleaned cache '{name}': {initial_size - final_size} "
                        f"items removed"
                    )
                    
    def clear_all_caches(self):
        """Clear all registered caches completely."""
        with self._lock:
            for name, cache_info in self._caches.items():
                cache_dict = cache_info['dict']
                size = len(cache_dict)
                cache_dict.clear()
                logger.info(f"Cleared cache '{name}': {size} items removed") 