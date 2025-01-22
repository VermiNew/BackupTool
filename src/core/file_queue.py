import logging
from pathlib import Path
from typing import List, Dict, Optional
from dataclasses import dataclass
from enum import Enum
import heapq
import time

logger = logging.getLogger(__name__)


class OperationType(Enum):
    """Types of file operations with their base priorities."""
    DELETE = 100        # Highest priority - free up space first
    MOVE = 80           # Then handle moves
    UPDATE = 60         # Then update existing files
    COPY = 40           # Finally copy new files


@dataclass
class FileOperation:
    """Represents a file operation with priority information."""
    path: Path
    operation: OperationType
    size: int
    priority: float
    dependencies: List[Path]
    original_path: Optional[Path] = None  # Original path for move operations

    def __lt__(self, other):
        """Compare operations for priority queue."""
        return self.priority > other.priority


class FileQueue:
    """Manages intelligent queuing of file operations.

    Implements a priority-based queue system that optimizes the order of operations:
    1. Deletes first to free up space
    2. Small files next for quick wins
    3. Large files last

    Size categories:
    - Small files: < 10 MB
    - Medium files: 10-100 MB
    - Large files: > 100 MB
    """

    # Size thresholds (in bytes)
    SMALL_FILE_THRESHOLD = 10 * 1024 * 1024     # 10 MB
    LARGE_FILE_THRESHOLD = 100 * 1024 * 1024    # 100 MB

    # Priority modifiers
    SMALL_FILE_BONUS = 20       # Bonus for small files
    LARGE_FILE_PENALTY = 10     # Penalty for large files
    DEPTH_PENALTY = 5           # Penalty per directory level

    # Speed calculation constants
    SPEED_WINDOW_SIZE = 20          # Number of samples for speed calculation
    SPEED_UPDATE_INTERVAL = 1.0     # Update speed every second
    ETA_SMOOTHING_FACTOR = 0.2      # ETA smoothing factor (0-1)
    
    # Memory management constants
    MAX_COMPLETED_ITEMS = 1000          # Maximum number of completed items to keep
    COMPLETED_CLEANUP_THRESHOLD = 1200  # When to trigger cleanup
    MAX_SPEED_SAMPLES = 100             # Maximum number of speed samples to keep

    def __init__(self):
        """Initialize the file queue."""
        self.queue = []
        self.in_progress = {}
        self.completed = {}
        self._reset_metrics()
        logger.info("Queue initialized")

    def _reset_metrics(self):
        """Reset performance metrics."""
        self.start_time = None
        self.last_update_time = 0
        self.last_processed_size = 0
        self.speed_samples = []  # List of (timestamp, speed) tuples
        self.last_eta = 0
        self.total_size = 0
        self.processed_size = 0
        self._cleanup_completed()

    def _cleanup_completed(self):
        """Clean up completed items if they exceed the threshold."""
        if len(self.completed) > self.COMPLETED_CLEANUP_THRESHOLD:
            # Keep only the most recent MAX_COMPLETED_ITEMS
            items = sorted(self.completed.items(), key=lambda x: x[1].get('completion_time', 0))
            self.completed = dict(items[-self.MAX_COMPLETED_ITEMS:])
            logger.debug(f"Cleaned up completed items. Current count: {len(self.completed)}")

    def _cleanup_speed_samples(self):
        """Clean up speed samples if they exceed the maximum."""
        if len(self.speed_samples) > self.MAX_SPEED_SAMPLES:
            # Keep only the most recent samples
            self.speed_samples = self.speed_samples[-self.MAX_SPEED_SAMPLES:]

    def update_progress(self, processed_size: int, current_time: float = None):
        """Update progress metrics.

        Args:
            processed_size: Total bytes processed so far
            current_time: Current timestamp (uses time.time() if None)
        """
        current_time = time.time()

        if self.start_time is None:
            self.start_time = current_time

        self.processed_size = processed_size

        # Update speed only at specified intervals
        if current_time - self.last_update_time >= self.SPEED_UPDATE_INTERVAL:
            # Calculate instantaneous speed
            size_delta = processed_size - self.last_processed_size
            time_delta = current_time - self.last_update_time

            if time_delta > 0:
                speed = size_delta / time_delta
                self.speed_samples.append((current_time, speed))
                self._cleanup_speed_samples()

                # Calculate weighted average speed
                total_weight = 0
                weighted_speed = 0
                current_samples = self.speed_samples[-self.SPEED_WINDOW_SIZE:]

                for _, (timestamp, speed) in enumerate(current_samples, 1):
                    # More recent samples get higher weight
                    age = current_time - timestamp
                    weight = 1 / (age + 1)  # Avoid division by zero
                    weighted_speed += speed * weight
                    total_weight += weight

                current_speed = weighted_speed / total_weight if total_weight > 0 else 0

                # Calculate ETA
                if current_speed > 0:
                    remaining_size = self.total_size - processed_size
                    new_eta = remaining_size / current_speed

                    # Smooth ETA changes
                    if self.last_eta > 0:
                        self.last_eta = (self.last_eta * (1 - self.ETA_SMOOTHING_FACTOR) +
                                         new_eta * self.ETA_SMOOTHING_FACTOR)
                    else:
                        self.last_eta = new_eta

            self.last_update_time = current_time
            self.last_processed_size = processed_size

    def get_progress_stats(self) -> Dict:
        """Get detailed progress statistics."""
        if not self.start_time:
            return {
                'progress_percent': 0,
                'current_speed': 0,
                'eta_seconds': 0,
                'elapsed_seconds': 0,
                'memory_usage': {
                    'queue_size': len(self.queue),
                    'in_progress': len(self.in_progress),
                    'completed': len(self.completed),
                    'speed_samples': len(self.speed_samples)
                }
            }

        current_time = time.time()
        elapsed = current_time - self.start_time

        if self.total_size > 0:
            progress = (self.processed_size / self.total_size) * 100
        else:
            progress = 0

        # Calculate current speed from recent samples
        current_speed = 0
        if self.speed_samples:
            # Use weighted average of last few samples
            samples = self.speed_samples[-5:]  # Last 5 samples
            if samples:
                weights = [0.5, 0.25, 0.15, 0.07, 0.03][:len(samples)]
                speeds = [sample[1] for sample in samples]
                current_speed = sum(s * w for s, w in zip(speeds, weights))

        return {
            'progress_percent': progress,
            'current_speed': current_speed,
            'eta_seconds': self.last_eta,
            'elapsed_seconds': elapsed,
            'memory_usage': {
                'queue_size': len(self.queue),
                'in_progress': len(self.in_progress),
                'completed': len(self.completed),
                'speed_samples': len(self.speed_samples)
            }
        }

    def _calculate_priority(self, path: Path, size: int, op_type: OperationType) -> float:
        """Calculate priority for a file operation.

        Priority is based on:
        1. Operation type (base priority from OperationType)
        2. File size (bonus for small files, penalty for large)
        3. Path depth (slight penalty for deeper paths)

        Args:
            path: File path
            size: File size in bytes
            op_type: Type of operation

        Returns:
            Priority value (higher means more important)
        """
        # Start with base priority from operation type
        priority = op_type.value

        # Adjust based on file size
        if size < self.SMALL_FILE_THRESHOLD:
            priority += self.SMALL_FILE_BONUS
            logger.debug(f"Small file bonus applied to {path}")
        elif size > self.LARGE_FILE_THRESHOLD:
            priority -= self.LARGE_FILE_PENALTY
            logger.debug(f"Large file penalty applied to {path}")

        # Adjust for path depth (deeper paths get slightly lower priority)
        depth = len(path.parts)
        depth_penalty = depth * self.DEPTH_PENALTY
        priority -= depth_penalty

        logger.debug(
            f"Priority calculated for {path}: {priority:.2f} "
            f"(size: {size/1024/1024:.1f}MB, depth: {depth})"
        )

        return priority

    def _add_dependencies(self, path: Path) -> List[Path]:
        """Calculate dependencies for a path.

        Args:
            path: Path to calculate dependencies for

        Returns:
            List of paths that must be processed before this one
        """
        deps = []
        current = path.parent

        # Add all parent directories as dependencies
        while current.parts:
            deps.append(current)
            current = current.parent

        return deps

    def add_operation(self, path: Path, size: int, op_type: OperationType, original_path: Optional[Path] = None):
        """Add a file operation to the queue.

        Args:
            path: Path to operate on
            size: File size in bytes
            op_type: Type of operation
            original_path: Original path for move operations
        """
        try:
            # Calculate priority
            priority = self._calculate_priority(path, size, op_type)

            # Create operation
            operation = FileOperation(
                path=path,
                operation=op_type,
                size=size,
                priority=priority,
                dependencies=self._add_dependencies(path),
                original_path=original_path
            )

            # Add to queue
            heapq.heappush(self.queue, operation)
            self.total_size += size

            # Clean up completed items if necessary
            self._cleanup_completed()

            logger.debug(
                f"Added operation: {op_type.name} {path} "
                f"(size: {size/1024/1024:.1f}MB, priority: {priority:.2f})"
            )

        except Exception as e:
            logger.error(f"Failed to add operation for {path}: {e}")
            raise

    def get_next_operation(self) -> Optional[FileOperation]:
        """Get the next operation to process.

        Returns:
            Next FileOperation to process, or None if queue is empty
        """
        while self.queue:
            # Get highest priority operation
            operation = heapq.heappop(self.queue)

            # Check if all dependencies are completed
            deps_completed = all(
                dep in self.completed for dep in operation.dependencies
            )

            if deps_completed:
                self.in_progress[operation.path] = operation
                logger.debug(
                    f"Starting operation: {operation.operation.value} "
                    f"{operation.path} (priority: {operation.priority:.2f})"
                )
                return operation
            else:
                # Put back in queue with slightly lower priority
                operation.priority -= 0.1
                heapq.heappush(self.queue, operation)

        return None

    def complete_operation(self, path: Path):
        """Mark an operation as completed.

        Args:
            path: Path of completed operation
        """
        if path in self.in_progress:
            operation = self.in_progress.pop(path)
            self.completed[path] = operation
            logger.debug(
                f"Completed operation: {operation.operation.value} {path}")

    def get_queue_stats(self) -> Dict:
        """Get statistics about the queue.

        Returns:
            Dictionary containing queue statistics
        """
        return {
            'queued': len(self.queue),
            'in_progress': len(self.in_progress),
            'completed': len(self.completed),
            'total_size': sum(op.size for op in self.queue),
            'completed_size': sum(op.size for op in self.completed.values())
        }
