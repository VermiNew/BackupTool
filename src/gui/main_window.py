import logging
from pathlib import Path
from typing import Tuple, Dict, Optional, List, Any
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
    QPushButton, QLabel, QFileDialog, QMessageBox,
    QGroupBox, QLineEdit, QCheckBox, QComboBox,
    QSystemTrayIcon, QApplication
)
from PyQt6.QtCore import QThread, pyqtSignal, Qt
import time
import json
import math
from datetime import datetime

from ..core.backup_manager import BackupManager
from ..utils.helpers import format_size
from ..utils.error_handler import ErrorTracker, ConfigurationError
from ..utils.memory_manager import MemoryManager
from ..utils.recovery import AutomaticRecovery
from ..utils.cleanup import CleanupManager
from ..utils.update_checker import UpdateChecker
from .widgets import AnimatedProgressBar
from .dialogs import PathVerificationDialog
from .tray_manager import TrayManager

logger = logging.getLogger(__name__)

# Status messages
SCANNING_MSG = "Scanning"
CREATING_BACKUP_MSG = "Creating backup"
ANALYZING_PATHS_MSG = "Analyzing paths..."
READY_MSG = "Ready"
BACKUP_CANCELLED_MSG = "Backup cancelled by user"
NO_FILES_MSG = "No files need to be updated"

# Error messages
PATH_SELECT_ERROR = "Please select both paths"
BACKUP_CANCEL_CONFIRM = "Are you sure you want to stop the backup operation?"
EXIT_CONFIRM = "A backup operation is in progress. Are you sure you want to exit?"

def format_path_display(path: Path) -> Tuple[str, str]:
    """Format path for display with preview.
    
    Args:
        path: Path object to format
        
    Returns:
        Tuple containing:
            - drive: Drive letter or root
            - display: Formatted path for display
    """
    drive = str(path.anchor)
    try:
        relative_path = path.relative_to(path.anchor)
        if len(relative_path.parts) > 0:
            preview = str(relative_path.parts[0])
            path_display = f"{drive}{preview}/..."
        else:
            path_display = drive
    except (IndexError, ValueError):
        path_display = drive
    return drive, path_display

def truncate_path(path: str, max_length: int) -> str:
    """Truncate path to specified length while preserving important parts."""
    if len(path) <= max_length:
        return path
        
    path_obj = Path(path)
    parts = list(path_obj.parts)
    
    if len(parts) <= 2:
        return path
        
    # Always keep drive/root and last component
    drive = parts[0]
    last_part = parts[-1]
    middle_parts = parts[1:-1]
    
    # If we have too many parts, keep only first and last from middle
    if len(middle_parts) > 2:
        middle_parts = [middle_parts[0], "...", middle_parts[-1]]
    
    # Construct path and check length
    result = str(Path(drive) / Path(*middle_parts) / last_part)
    if len(result) <= max_length:
        return result
        
    # If still too long, show only drive, ... and filename
    return str(Path(drive) / "..." / last_part)

class BackupThread(QThread):
    """Thread responsible for performing the backup operation.
    
    Signals:
        progress (float): Emits the current progress percentage (0-100)
        finished (bool, str): Emits backup completion status and message
        status (str): Emits current status message
        current_file (str, str): Emits current file path and size
        stats_update (dict): Emits dictionary with speed, ETA and size statistics
    """
    
    progress = pyqtSignal(float)
    finished = pyqtSignal(bool, str)
    status = pyqtSignal(str)
    current_file = pyqtSignal(str, str)  # path, size
    stats_update = pyqtSignal(dict)  # For speed, eta, total size updates
    
    def __init__(self, manager: BackupManager, differences: Dict):
        """Initialize the backup thread.
        
        Args:
            manager: BackupManager instance
            differences: Dictionary containing files to copy/update
        """
        super().__init__()
        self.manager = manager
        self.differences = differences
        self.total_files = len(differences['to_copy']) + len(differences['to_update'])
        self.current_file_number = 0
        self.start_time: Optional[float] = None
        self.total_size = 0
        self.processed_size = 0
        
        # Speed calculation variables
        self.speed_samples: List[float] = []
        self.SPEED_WINDOW_SIZE = 150  # Large window for better stability
        self.MIN_UPDATE_INTERVAL = 0.5  # Update every 0.5 seconds
        self.last_update_time = time.time()
        self.last_processed_size = 0
        self.current_speed = 0.0
        self.last_eta = 0.0  # For ETA smoothing
        self.min_speed = float('inf')  # Track minimum speed
        self.max_speed = 0.0  # Track maximum speed
        
        # Calculate total size
        for file_type in ['to_copy', 'to_update']:
            for file_path in differences[file_type]:
                try:
                    full_path = Path(self.manager.source_path) / file_path
                    self.total_size += full_path.stat().st_size
                except Exception as e:
                    logger.warning(f"Failed to get size for {file_path}: {e}")
        
    def format_speed(self, bytes_per_sec: float) -> str:
        """Format speed in bytes/sec to human readable format.
        
        Args:
            bytes_per_sec: Speed in bytes per second
            
        Returns:
            Formatted string with appropriate unit/s
        """
        return f"{format_size(bytes_per_sec)}/s"
        
    def format_time(self, seconds: float) -> str:
        """Format time in seconds to human readable format.
        
        Args:
            seconds: Time in seconds
            
        Returns:
            Formatted string with appropriate unit
        """
        if seconds < 60:
            return f"{seconds:.0f}s"
        elif seconds < 3600:
            minutes = seconds / 60
            return f"{minutes:.0f}m"
        else:
            hours = seconds / 3600
            return f"{hours:.1f}h"
        
    def update_progress(self, copied_size: int, current_file: Optional[str] = None):
        """Update progress and statistics.
        
        Args:
            copied_size: Total number of bytes copied so far
            current_file: Current file being processed (optional)
        """
        current_time = time.time()
        self.processed_size = copied_size
        
        # Calculate progress percentage
        progress = (self.processed_size / self.total_size * 100) if self.total_size > 0 else 0
        self.progress.emit(progress)
        
        # Update stats every MIN_UPDATE_INTERVAL seconds
        if current_time - self.last_update_time >= self.MIN_UPDATE_INTERVAL:
            # Calculate instantaneous speed
            size_delta = self.processed_size - self.last_processed_size
            time_delta = current_time - self.last_update_time
            
            if time_delta > 0:
                instant_speed = size_delta / time_delta
                self.speed_samples.append(instant_speed)
                
                # Keep only the last N samples
                if len(self.speed_samples) > self.SPEED_WINDOW_SIZE:
                    self.speed_samples.pop(0)
                
                # Calculate weighted average with emphasis on middle samples
                # for better stability and accuracy
                total_weight = 0
                weighted_speed = 0
                samples_count = len(self.speed_samples)
                
                if samples_count > 0:
                    # Gaussian weights - higher importance for middle samples
                    middle = samples_count / 2
                    sigma = samples_count / 6  # Gaussian curve width
                    
                    for i, speed in enumerate(self.speed_samples):
                        # Gaussian weight - highest in the middle
                        weight = math.exp(-((i - middle) ** 2) / (2 * sigma ** 2))
                        weighted_speed += speed * weight
                        total_weight += weight
                    
                    self.current_speed = weighted_speed / total_weight if total_weight > 0 else 0
                    
                    # Update min/max speeds (ignore first few samples for stability)
                    if samples_count > 5 and self.current_speed > 0:
                        self.min_speed = min(self.min_speed, self.current_speed)
                        self.max_speed = max(self.max_speed, self.current_speed)
            
            # Calculate ETA using moving average speed
            eta_seconds = 0  # Initialize default value
            
            if self.current_speed > 0:
                remaining_size = self.total_size - self.processed_size
                
                # Use combination of different methods for better accuracy
                if self.start_time:
                    total_time = current_time - self.start_time
                    if total_time > 0:
                        # Average speed from entire transfer
                        average_speed = self.processed_size / total_time
                        
                        # Weights for different components
                        if total_time < 10:  # First 10 seconds - mainly current speed
                            current_weight = 0.8
                            average_weight = 0.2
                        elif total_time < 30:  # 10-30 seconds - more balanced weights
                            current_weight = 0.6
                            average_weight = 0.4
                        else:  # Above 30 seconds - higher weight for total average
                            current_weight = 0.3
                            average_weight = 0.7
                        
                        estimated_speed = (self.current_speed * current_weight) + (average_speed * average_weight)
                        
                        new_eta = remaining_size / estimated_speed
                        
                        # ETA smoothing
                        if self.last_eta > 0:
                            # Gradual ETA change
                            eta_change_weight = 0.2  # Maximum change of 20%
                            eta_seconds = (self.last_eta * (1 - eta_change_weight) + 
                                        new_eta * eta_change_weight)
                        else:
                            eta_seconds = new_eta
                        
                        self.last_eta = eta_seconds
                    else:
                        eta_seconds = remaining_size / self.current_speed
            else:
                    eta_seconds = remaining_size / self.current_speed
            
            # Update stats
            self.stats_update.emit({
                'speed': f"Speed: {self.format_speed(self.current_speed)}",
                'min_speed': f"Min: {self.format_speed(self.min_speed if self.min_speed != float('inf') else 0)}",
                'max_speed': f"Max: {self.format_speed(self.max_speed)}",
                'eta': f"ETA: {self.format_time(eta_seconds)}",
                'processed_size': f"Size: {format_size(self.processed_size)} / {format_size(self.total_size)}",
                'percent': progress
            })
            
            self.last_update_time = current_time
            self.last_processed_size = self.processed_size
            
        # Update current file info if provided
        if current_file:
            self.current_file_number += 1
            file_size = 0
            size_str = "Unknown"
            
            try:
                full_path = Path(self.manager.source_path) / current_file
                file_size = full_path.stat().st_size
                size_str = format_size(file_size)
            except Exception as e:
                logger.warning(f"Failed to get size for {current_file}: {e}")
            
            truncated_file = truncate_path(current_file, 50)
            self.current_file.emit(str(full_path), size_str)
            
            source_path = Path(self.manager.source_path)
            _, path_display = format_path_display(source_path)
            
            self.status.emit(
                f"{CREATING_BACKUP_MSG} ({self.current_file_number}/{self.total_files}) - "
                f"[{path_display}] {truncated_file}"
            )
        
    def run(self):
        try:
            self.start_time = time.time()
            self.last_update_time = self.start_time
            
            success = self.manager.perform_backup(
                self.differences,
                self.update_progress
            )
            
            if success:
                total_time = time.time() - self.start_time
                avg_speed = self.total_size / total_time if total_time > 0 else 0
                self.finished.emit(True, 
                    f"Backup completed successfully!\n"
                    f"Total size: {format_size(self.total_size)}\n"
                    f"Average speed: {self.format_speed(avg_speed)}\n"
                    f"Time taken: {self.format_time(total_time)}"
                )
            else:
                self.finished.emit(False, "Backup failed!")
        except Exception as e:
            logger.error(f"Backup error: {e}")
            self.finished.emit(False, str(e))

class ScanThread(QThread):
    """Thread for scanning directories and preparing backup."""
    finished = pyqtSignal(bool, str, dict)
    status = pyqtSignal(str)
    current_file = pyqtSignal(str)
    
    def __init__(self, manager: BackupManager, source_path: str, dest_path: str):
        super().__init__()
        self.manager = manager
        self.source_path = source_path
        self.dest_path = dest_path
        
    def run(self):
        try:
            source_path = Path(self.source_path)
            dest_path = Path(self.dest_path)
            
            # Get formatted paths for display
            _, source_path_display = format_path_display(source_path)
            _, dest_path_display = format_path_display(dest_path)
            
            self.status.emit(f"{ANALYZING_PATHS_MSG} [Source: {source_path_display}] [Destination: {dest_path_display}]")
            success, message = self.manager.analyze_paths(self.source_path, self.dest_path)
            if not success:
                self.finished.emit(False, message, {})
                return

            def progress_update(msg: str):
                if msg.startswith(f"{SCANNING_MSG}:"):
                    file_path = msg[9:].strip()
                    # Extract the part in parentheses if it exists
                    file_count = ""
                    if "(" in file_path:
                        file_path, file_count = file_path.rsplit("(", 1)
                        file_count = file_count.rstrip(")")  # Remove closing parenthesis
                    
                    full_path = str(Path(self.source_path) / file_path)
                    _, path_display = format_path_display(source_path)
                    
                    status_msg = (
                        f"{SCANNING_MSG} ({file_count}) - "
                        f"[{path_display}] {file_path.strip()}"
                    )
                    self.status.emit(status_msg)
                    self.current_file.emit(full_path)

            differences = self.manager.analyze_differences(
                progress_callback=progress_update
            )
            
            total_files = len(differences['to_copy']) + len(differences['to_update'])
            if total_files == 0:
                self.finished.emit(True, NO_FILES_MSG, differences)
            else:
                self.finished.emit(True, f"Found {total_files} files to process", differences)
                
        except Exception as e:
            logger.error(f"Scan error: {e}")
            self.finished.emit(False, str(e), {})

class MainWindow(QMainWindow):
    """Main window of the backup application."""
    
    def __init__(self, config: Dict, config_path: str):
        """Initialize the main window."""
        super().__init__()
        self.config = config
        self.config_path = config_path
        
        # Initialize state
        self.scanning = False
        self.backing_up = False
        self.backup_manager = BackupManager()
        self.quit_requested = False
        
        # First setup UI to create all fields
        self.setup_ui()
        
        # Initialize managers
        self.setup_error_handling()
        self.setup_memory_management()
        self.setup_recovery()
        self.setup_cleanup()
        self.setup_update_checker()
        
        # Initialize tray last, after all UI elements are created
        self.setup_tray()
        
        # Then load saved settings into existing fields
        self.load_saved_settings()
        
        # Check for updates
        self.check_for_updates()
        
    def setup_error_handling(self):
        """Initialize error handling system."""
        log_dir = Path(self.config.get('logging', {}).get('directory', 'logs'))
        self.error_tracker = ErrorTracker(log_dir)
        
    def setup_memory_management(self):
        """Initialize memory management system."""
        memory_limit = self.config.get('system', {}).get('memory_limit', None)
        self.memory_manager = MemoryManager(memory_limit)
        
        # Register caches if needed
        self.memory_manager.register_cache('backup_cache', {}, 1000)
        
    def setup_recovery(self):
        """Initialize recovery system."""
        backup_dir = Path(self.config.get('backup', {}).get('directory', 'backups'))
        self.recovery = AutomaticRecovery(backup_dir)
        
        # Start health monitoring
        self.recovery.start_monitoring(self.handle_health_warning)
        
        # Setup signal handlers
        self.recovery.setup_signal_handlers()
        
        # Try to load previous state
        self.load_previous_state()
        
    def handle_health_warning(self, warning: str):
        """Handle system health warnings."""
        self.tray_manager.set_state('warning', warning)
        QMessageBox.warning(
            self,
            "System Warning",
            warning,
            QMessageBox.StandardButton.Ok
        )
        
    def load_previous_state(self):
        """Try to load and restore previous backup state."""
        state = self.recovery.crash_recovery.load_state()
        if state:
            reply = QMessageBox.question(
                self,
                'Recover Previous Session',
                'A previous backup session was interrupted. Would you like to restore it?',
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.Yes
            )
            if reply == QMessageBox.StandardButton.Yes:
                # Restore previous state
                if 'source_path' in state:
                    self.source_path.setText(state['source_path'])
                if 'dest_path' in state:
                    self.dest_path.setText(state['dest_path'])
                # Add more state restoration as needed
                
    def setup_tray(self):
        """Initialize system tray icon."""
        if not QSystemTrayIcon.isSystemTrayAvailable():
            logger.warning("System tray is not available")
            return
            
        self.tray_manager = TrayManager(self)
        
        # Connect tray signals
        self.tray_manager.show_window.connect(self.show_and_activate)
        self.tray_manager.start_backup.connect(self.start_backup_from_tray)
        self.tray_manager.stop_backup.connect(self.cancel_backup)
        self.tray_manager.quit_app.connect(self.quit_application)
        
    def show_and_activate(self):
        """Show and activate the window."""
        self.show()
        self.activateWindow()
        self.raise_()
        
    def start_backup_from_tray(self):
        """Start backup from tray without showing window."""
        if not self.scanning and not self.backing_up:
            self.start_backup()
            
    def setup_ui(self):
        """Initialize and setup the user interface."""
        self.setWindowTitle("Backup Tool")
        self.setFixedSize(
            self.config['interface']['window_size']['width'],
            self.config['interface']['window_size']['height']
        )
        
        # Main widget and layout
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        layout = QVBoxLayout(main_widget)
        
        # Setup UI components
        self._setup_paths_group(layout)
        self._setup_options_group(layout)
        self._setup_progress_group(layout)
        self._setup_buttons(layout)
        
        self.apply_theme()
        
    def _setup_paths_group(self, layout: QVBoxLayout):
        """Setup the paths group box."""
        paths_group = QGroupBox("Paths")
        paths_layout = QVBoxLayout()
        
        # Source path
        source_layout = QHBoxLayout()
        self.source_path = QLineEdit()
        self.source_path.textChanged.connect(self._on_path_changed)
        self.source_browse = QPushButton("Browse")
        self.source_browse.clicked.connect(lambda: self.browse_path("source"))
        source_layout.addWidget(QLabel("Source:"))
        source_layout.addWidget(self.source_path)
        source_layout.addWidget(self.source_browse)
        
        # Destination path
        dest_layout = QHBoxLayout()
        self.dest_path = QLineEdit()
        self.dest_path.textChanged.connect(self._on_path_changed)
        self.dest_browse = QPushButton("Browse")
        self.dest_browse.clicked.connect(lambda: self.browse_path("destination"))
        dest_layout.addWidget(QLabel("Destination:"))
        dest_layout.addWidget(self.dest_path)
        dest_layout.addWidget(self.dest_browse)
        
        paths_layout.addLayout(source_layout)
        paths_layout.addLayout(dest_layout)
        paths_group.setLayout(paths_layout)
        layout.addWidget(paths_group)
        
    def _on_path_changed(self):
        """Handle path text changes."""
        self.save_settings()
        
    def _setup_options_group(self, layout: QVBoxLayout):
        """Setup the options group box."""
        options_group = QGroupBox("Options")
        options_layout = QVBoxLayout()
        
        # Auto mode and verify mode
        self.auto_mode = QCheckBox("Auto mode (skip confirmations)")
        self.auto_mode.stateChanged.connect(lambda: self.save_settings())
        
        self.verify_mode = QCheckBox("Verify files after copy")
        self.verify_mode.setChecked(self.config['backup']['verify_after_copy'])
        self.verify_mode.stateChanged.connect(lambda: self.save_settings())
        
        # Buffer size selection
        buffer_layout = QHBoxLayout()
        buffer_layout.addWidget(QLabel("Buffer size:"))
        self.buffer_size = QComboBox()
        buffer_sizes = [
            ("512 KB (for old HDDs, USB 2.0 flash drives)", 512 * 1024),
            ("1 MB (default, good for most HDDs)", 1024 * 1024),
            ("2 MB (for modern HDDs, USB 3.0 drives)", 2 * 1024 * 1024),
            ("4 MB (for SATA SSDs)", 4 * 1024 * 1024),
            ("8 MB (for NVMe SSDs)", 8 * 1024 * 1024),
            ("16 MB (for high-end NVMe SSDs, fast RAID arrays)", 16 * 1024 * 1024)
        ]
        
        # Add all options to combobox
        for label, size in buffer_sizes:
            self.buffer_size.addItem(label, size)
        
        # Set current buffer size from config
        current_size = self.config['backup'].get('chunk_size', 1024 * 1024)  # 1MB default if not set
        index = self.buffer_size.findData(current_size)
        if index >= 0:
            self.buffer_size.setCurrentIndex(index)
        else:
            # If configured size not in predefined list, add it as custom option
            custom_label = f"{format_size(current_size)} (custom)"
            self.buffer_size.addItem(custom_label, current_size)
            self.buffer_size.setCurrentIndex(self.buffer_size.count() - 1)
        
        self.buffer_size.setToolTip("Select buffer size based on your drive type")
        self.buffer_size.currentIndexChanged.connect(self._buffer_size_changed)
        buffer_layout.addWidget(self.buffer_size)
        
        # Add exclusion patterns
        exclude_layout = QHBoxLayout()
        self.exclude_patterns = QLineEdit()
        self.exclude_patterns.setPlaceholderText("Exclude patterns (comma separated, e.g. *.tmp, *.log)")
        self.exclude_patterns.textChanged.connect(lambda: self.save_settings())
        if 'exclude_patterns' in self.config['backup']:
            self.exclude_patterns.setText(','.join(self.config['backup']['exclude_patterns']))
        exclude_layout.addWidget(QLabel("Exclude:"))
        exclude_layout.addWidget(self.exclude_patterns)
        
        options_layout.addWidget(self.auto_mode)
        options_layout.addWidget(self.verify_mode)
        options_layout.addLayout(buffer_layout)
        options_layout.addLayout(exclude_layout)
        options_group.setLayout(options_layout)
        layout.addWidget(options_group)
        
    def _buffer_size_changed(self):
        """Handle buffer size change."""
        new_size = self.buffer_size.currentData()
        self.config['backup']['chunk_size'] = new_size
        self.save_settings()
        
    def _setup_progress_group(self, layout: QVBoxLayout):
        """Setup the progress group box."""
        progress_group = QGroupBox("Progress")
        progress_layout = QVBoxLayout()
        
        # Progress bar with percentage
        progress_bar_layout = QHBoxLayout()
        self.progress_bar = AnimatedProgressBar()
        progress_bar_layout.addWidget(self.progress_bar)
        
        # Status label
        self.status_label = QLabel(READY_MSG)
        self.status_label.setWordWrap(False)
        
        # Stats layout
        stats_layout = QHBoxLayout()
        self.speed_label = QLabel("")
        self.min_speed_label = QLabel("")
        self.max_speed_label = QLabel("")
        self.eta_label = QLabel("")
        self.size_label = QLabel("")
        stats_layout.addWidget(self.speed_label)
        stats_layout.addWidget(self.min_speed_label)
        stats_layout.addWidget(self.max_speed_label)
        stats_layout.addWidget(self.eta_label)
        stats_layout.addWidget(self.size_label)
        
        # Current file frame
        current_file_frame = QGroupBox("Current File")
        current_file_layout = QVBoxLayout()
        self.current_file_label = QLabel()
        self.current_file_label.setWordWrap(False)
        self.file_size_label = QLabel()
        current_file_layout.addWidget(self.current_file_label)
        current_file_layout.addWidget(self.file_size_label)
        current_file_frame.setLayout(current_file_layout)
        
        progress_layout.addLayout(progress_bar_layout)
        progress_layout.addWidget(self.status_label)
        progress_layout.addLayout(stats_layout)
        progress_layout.addWidget(current_file_frame)
        progress_group.setLayout(progress_layout)
        layout.addWidget(progress_group)
        
    def _setup_buttons(self, layout: QVBoxLayout):
        """Setup the action buttons."""
        button_layout = QHBoxLayout()
        self.start_button = QPushButton("Start Backup")
        self.start_button.clicked.connect(self.start_backup)
        
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.clicked.connect(self.cancel_backup)
        self.cancel_button.setEnabled(False)
        
        button_layout.addWidget(self.start_button)
        button_layout.addWidget(self.cancel_button)
        layout.addLayout(button_layout)
        
    def apply_theme(self):
        """Apply the current theme to the UI."""
        if self.config['interface']['dark_mode']:
            theme = self.config['interface']['theme']['dark']
            self.setStyleSheet(f"""
                QMainWindow, QWidget {{
                    background-color: {theme['background']};
                    color: {theme['text']};
                }}
                QPushButton {{
                    background-color: {theme['primary']};
                    color: white;
                    border: none;
                    padding: 5px 15px;
                    border-radius: 3px;
                }}
                QPushButton:hover {{
                    background-color: {theme['secondary']};
                }}
                QLineEdit {{
                    padding: 5px;
                    border: 1px solid {theme['primary']};
                    border-radius: 3px;
                }}
                QGroupBox {{
                    border: 1px solid {theme['primary']};
                    border-radius: 5px;
                    margin-top: 1em;
                    padding-top: 10px;
                }}
                QGroupBox::title {{
                    subcontrol-origin: margin;
                    left: 10px;
                    padding: 0 3px;
                    color: {theme['secondary']};
                    font-weight: bold;
                }}
                QLabel {{
                    padding: 2px;
                }}
            """)
            
    def browse_path(self, path_type: str):
        """Open file dialog to browse for a directory.
        
        Args:
            path_type: Type of path to browse for ("source" or "destination")
        """
        dialog = QFileDialog(self)
        dialog.setFileMode(QFileDialog.FileMode.Directory)
        dialog.setOption(QFileDialog.Option.ShowDirsOnly, True)
        
        if dialog.exec() == QFileDialog.DialogCode.Accepted:
            selected = dialog.selectedFiles()[0]
            if path_type == "source":
                self.source_path.setText(selected)
            else:
                self.dest_path.setText(selected)
            # Save settings when paths are changed
            self.save_settings()
                
    def start_backup(self):
        """Start the backup process with resource checks."""
        if self.scanning or self.backing_up:
            return
            
        # Check system resources before starting
        if not self.check_system_resources():
            return
            
        source = self.source_path.text().strip()
        dest = self.dest_path.text().strip()
        
        if not source or not dest:
            self.handle_error(
                ConfigurationError("Please select both paths"),
                {'source': source, 'dest': dest}
            )
            return
            
        try:
            # Configure backup manager
            self.backup_manager.source_path = source
            self.backup_manager.dest_path = dest
            
            # Set exclude patterns
            patterns = [p.strip() for p in self.exclude_patterns.text().split(',') if p.strip()]
            self.backup_manager.set_exclude_patterns(patterns)
            
            # Disable UI during scan
            self.scanning = True
            self.update_ui_state()
            self.status_label.setText(f"{SCANNING_MSG}...")
            self.progress_bar.setValue(0)
            
            # Start scan thread
            self.scan_thread = ScanThread(self.backup_manager, source, dest)
            self.scan_thread.status.connect(self.update_status)
            self.scan_thread.current_file.connect(self.update_current_file)
            self.scan_thread.finished.connect(self.scan_finished)
            self.scan_thread.start()
            
        except Exception as e:
            self.handle_error(e, {
                'source': source,
                'dest': dest,
                'patterns': patterns
            })
        
    def scan_finished(self, success: bool, message: str, differences: Dict):
        """Handle scan completion."""
        self.scanning = False
        
        if not success:
            self.update_ui_state()
            QMessageBox.critical(self, "Error", message)
            return
            
        # Show confirmation dialog
        if not self.auto_mode.isChecked():
            total_files = len(differences['to_copy']) + len(differences['to_update'])
            status_msg = f"Files to process: {total_files}\n{message}"
            self.status_label.setText(status_msg)
            
            dialog = PathVerificationDialog(differences, self)
            if dialog.exec() != QMessageBox.DialogCode.Accepted:
                self.update_ui_state()
                return
                
        # Start backup
        self.backing_up = True
        self.update_ui_state()
        
        self.backup_thread = BackupThread(self.backup_manager, differences)
        self.backup_thread.progress.connect(self.update_progress)
        self.backup_thread.status.connect(self.update_status)
        self.backup_thread.current_file.connect(self.update_current_file)
        self.backup_thread.stats_update.connect(self.update_stats)
        self.backup_thread.finished.connect(self.backup_finished)
        self.backup_thread.start()
        
    def cancel_backup(self):
        """Handle backup cancellation."""
        if self.scanning or self.backing_up:
            reply = QMessageBox.question(
                self,
                'Confirm Cancel',
                BACKUP_CANCEL_CONFIRM,
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.No:
                return
            
            if self.scanning:
                self.scan_thread.terminate()
                self.scan_thread.wait()
                self.scanning = False
            else:
                self.backup_manager.stop()
                self.backup_thread.wait()
            
            self.update_ui_state()
            self.status_label.setText(BACKUP_CANCELLED_MSG)
        
    def update_progress(self, value: float):
        """Update progress bar value.
        
        Args:
            value: Progress percentage (0-100)
        """
        self.progress_bar.setValue(int(value))
        
    def update_status(self, message: str):
        """Update status label text and tray tooltip."""
        self.status_label.setText(message)
        
        # Update tray state based on message
        if self.backing_up:
            self.tray_manager.set_state('backup', message)
        elif "error" in message.lower():
            self.tray_manager.set_state('error', message)
        elif "warning" in message.lower():
            self.tray_manager.set_state('warning', message)
        else:
            self.tray_manager.set_state('waiting', message)
            
    def backup_finished(self, success: bool, message: str, stats: Dict = None):
        """Handle backup completion."""
        self.backing_up = False
        self.update_ui_state()
        
        if not success:
            QMessageBox.critical(self, "Error", message)
            return
            
        if stats and stats.get('errors', 0) > 0:
            error_msg = f"Backup completed with {stats['errors']} errors"
            QMessageBox.warning(
                self,
                "Backup Warning",
                error_msg,
                QMessageBox.StandardButton.Ok
            )
            
        self.status_label.setText(message)
        self.progress_bar.setValue(100)
        
        # Save settings after backup completion
        self.save_settings()
            
    def update_ui_state(self):
        """Update UI elements based on current state."""
        enabled = not (self.scanning or self.backing_up)
        self.start_button.setEnabled(enabled)
        self.source_path.setEnabled(enabled)
        self.dest_path.setEnabled(enabled)
        self.source_browse.setEnabled(enabled)
        self.dest_browse.setEnabled(enabled)
        self.auto_mode.setEnabled(enabled)
        self.verify_mode.setEnabled(enabled)
        self.exclude_patterns.setEnabled(enabled)
        self.buffer_size.setEnabled(enabled)
        self.cancel_button.setEnabled(not enabled)
        
        # Update tray state
        if not enabled:
            self.tray_manager.set_state('backup', "Backup in progress...")
        else:
            self.tray_manager.set_state('waiting', READY_MSG)
            
        # Clear stats when not backing up
        if enabled:
            self.speed_label.setText("")
            self.min_speed_label.setText("")
            self.max_speed_label.setText("")
            self.eta_label.setText("")
            self.size_label.setText("")
            self.current_file_label.setText("")
            self.file_size_label.setText("")
            self.progress_bar.setValue(0)
        
    def update_current_file(self, file_path: str, size: Optional[str] = None):
        """Update current file being processed.
        
        Args:
            file_path: Path of the current file
            size: Size of the current file (optional)
        """
        truncated_path = truncate_path(str(file_path), 50)
        self.current_file_label.setText(truncated_path)
        if size:
            self.file_size_label.setText(f"Size: {size}")
        
    def update_stats(self, stats: Dict[str, str]):
        """Update statistics labels.
        
        Args:
            stats: Dictionary containing current statistics
        """
        self.speed_label.setText(stats['speed'])
        self.min_speed_label.setText(stats['min_speed'])
        self.max_speed_label.setText(stats['max_speed'])
        self.eta_label.setText(stats['eta'])
        self.size_label.setText(stats['processed_size'])
        self.progress_bar.setValue(int(stats['percent']))
        
    def load_saved_settings(self):
        """Load saved settings from config."""
        # Load exclude patterns from backup config
        if 'exclude_patterns' in self.config['backup']:
            self.exclude_patterns.setText(','.join(self.config['backup']['exclude_patterns']))
        
        # Load other settings
        if 'auto_mode' in self.config:
            self.auto_mode.setChecked(self.config['auto_mode'])
        if 'verify_after_copy' in self.config['backup']:
            self.verify_mode.setChecked(self.config['backup']['verify_after_copy'])
        
    def save_settings(self):
        """Save current settings to config."""
        # Save exclude patterns to backup config
        patterns = [p.strip() for p in self.exclude_patterns.text().split(',') if p.strip()]
        self.config['backup']['exclude_patterns'] = patterns
        
        # Save other settings
        self.config['auto_mode'] = self.auto_mode.isChecked()
        self.config['backup']['verify_after_copy'] = self.verify_mode.isChecked()
        
        # Save config to file
        try:
            with open(self.config_path, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, indent=4)
        except Exception as e:
            QMessageBox.warning(self, "Warning", f"Failed to save settings: {e}")
        
    def closeEvent(self, event):
        """Handle application close event."""
        if self.scanning or self.backing_up:
            # If operation is in progress, show warning
            warning_msg = (
                "A file operation is in progress!\n\n"
                "Please either:\n"
                "1. Stop the current operation and wait for it to finish\n"
                "2. Wait for the operation to complete naturally\n"
                "3. Use SHIFT + ESC for emergency force quit (may corrupt files!)\n\n"
                "Do you want to stop the current operation?"
            )
            
            reply = QMessageBox.warning(
                self,
                'Operation in Progress',
                warning_msg,
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )
            
            if reply == QMessageBox.StandardButton.Yes:
                # User chose to stop the operation
                if self.scanning:
                    self.scan_thread.terminate()
                    self.scan_thread.wait()
                elif self.backing_up:
                    self.backup_manager.stop()
                    # Show "waiting for operation to stop" message
                    please_wait = QMessageBox(
                        QMessageBox.Icon.Information,
                        "Please Wait",
                        "Waiting for the operation to stop safely...",
                        QMessageBox.StandardButton.NoButton,
                        self
                    )
                    please_wait.show()
                    # Wait for backup thread to finish
                    self.backup_thread.wait()
                    please_wait.close()
                    
                # Show final warning
                final_msg = (
                    "Operation has been stopped.\n"
                    "It's now safe to close the application.\n"
                    "Click OK to close or Cancel to continue working."
                )
                final_reply = QMessageBox.information(
                    self,
                    'Safe to Close',
                    final_msg,
                    QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel,
                    QMessageBox.StandardButton.Cancel
                )
                
                if final_reply == QMessageBox.StandardButton.Cancel:
                    event.ignore()
                    return
            else:
                # User chose not to stop the operation
                event.ignore()
                return
        
        # If we get here, either no operation was in progress or it was safely stopped
        
        # Save current state and settings
        self.save_settings()
        self.save_current_state()
        
        # If closing to tray is enabled and it's not a quit action
        if (self.config.get('tray', {}).get('actions', {}).get('close_to_tray', True) and 
            not self.quit_requested):
            self.hide()
            # Show toast notification that app is minimized to tray
            self.tray_manager.show_message(
                "Backup Tool",
                "Application minimized to system tray.\nDouble-click the tray icon to restore.",
                QSystemTrayIcon.MessageIcon.Information
            )
            event.ignore()
        else:
            # Stop recovery monitoring
            self.recovery.stop_monitoring()
            
            # Clean up caches
            self.memory_manager.clear_all_caches()
            
            # Cleanup before exit
            self.tray_manager.cleanup()
            self.recovery.crash_recovery.cleanup_state()
            
            # Accept the close event
            event.accept()
            
            # Ensure the application quits
            QApplication.instance().quit()

    def save_current_state(self):
        """Save current application state for recovery."""
        if self.backing_up:
            state = {
                'source_path': self.source_path.text(),
                'dest_path': self.dest_path.text(),
                'progress': self.progress_bar.value(),
                'status': self.status_label.text(),
                'timestamp': datetime.now().isoformat()
            }
            self.recovery.crash_recovery.save_state(state)
            
    def handle_error(self, error: Exception, context: Dict[str, Any] = None):
        """Handle application errors."""
        self.error_tracker.handle_error(error, context)
        self.tray_manager.set_state('error', str(error))
        QMessageBox.critical(
            self,
            "Error",
            str(error),
            QMessageBox.StandardButton.Ok
        )
        
    def check_system_resources(self) -> bool:
        """Check if system resources are sufficient."""
        # Check memory usage
        if not self.memory_manager.check_memory():
            memory_msg = "Memory usage is critical - cannot start backup"
            self.handle_error(
                Exception(memory_msg),
                {'memory_usage': self.memory_manager.get_memory_usage()}
            )
            return False
            
        # Check system health
        health_status = self.recovery.health_monitor.check_system_health()
        if not health_status['is_healthy']:
            for warning in health_status['warnings']:
                self.handle_health_warning(warning)
            return False
            
        return True
        
    def setup_cleanup(self):
        """Initialize cleanup manager."""
        self.cleanup_manager = CleanupManager()
        
    def quit_application(self):
        """Handle application quit from tray menu."""
        # Set quit flag
        self.quit_requested = True
        
        # Save and cleanup
        self.save_settings()
        self.save_current_state()
        self.recovery.stop_monitoring()
        self.memory_manager.clear_all_caches()
        self.recovery.crash_recovery.cleanup_state()
        
        # Run cleanup operations
        self.cleanup_manager.cleanup_all()
        
        # Close all windows and quit
        QApplication.instance().closeAllWindows()
        QApplication.instance().quit()

    def keyPressEvent(self, event):
        """Handle key press events."""
        # Check for Shift + Esc
        if event.key() == Qt.Key.Key_Escape and event.modifiers() == Qt.KeyboardModifier.ShiftModifier:
            # Show emergency quit warning if operations are in progress
            if self.scanning or self.backing_up:
                warning_msg = (
                    "WARNING: Emergency Force Quit!\n\n"
                    "A file operation is in progress!\n"
                    "Force quitting now may result in:\n"
                    "- Corrupted files\n"
                    "- Incomplete backups\n"
                    "- Lost data\n\n"
                    "Are you absolutely sure you want to force quit?"
                )
                reply = QMessageBox.critical(
                    self,
                    'Emergency Force Quit',
                    warning_msg,
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.No
                )
                if reply == QMessageBox.StandardButton.No:
                    return
            else:
                # Normal force quit confirmation if no operations are in progress
                reply = QMessageBox.question(
                    self,
                    'Force Quit',
                    'Are you sure you want to force quit the application?',
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.No
                )
                if reply == QMessageBox.StandardButton.No:
                    return
                    
            # Force quit without saving
            self.tray_manager.cleanup()
            # Run cleanup even in force quit
            self.cleanup_manager.cleanup_all()
            QApplication.instance().quit()
        else:
            super().keyPressEvent(event)

    def setup_update_checker(self):
        """Initialize update checker."""
        self.update_checker = UpdateChecker()
        
    def check_for_updates(self):
        """Check for application updates."""
        has_update, message = self.update_checker.check_for_updates()
        if has_update:
            self.tray_manager.show_message(
                "Update Available",
                message,
                QSystemTrayIcon.MessageIcon.Information
            )
        elif "Git is not available" in message:
            logger.warning(message)
