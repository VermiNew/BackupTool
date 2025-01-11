import logging
from pathlib import Path
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
    QPushButton, QProgressBar, QLabel, QFileDialog,
    QMessageBox, QGroupBox, QLineEdit, QCheckBox
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
import time
from datetime import datetime, timedelta

from ..core.backup_manager import BackupManager
from .widgets import AnimatedProgressBar
from .dialogs import PathVerificationDialog

logger = logging.getLogger(__name__)

def truncate_path(path: str, max_length: int = 80) -> str:
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
    progress = pyqtSignal(float)
    finished = pyqtSignal(bool, str)
    status = pyqtSignal(str)
    current_file = pyqtSignal(str, str)  # path, size
    stats_update = pyqtSignal(dict)  # For speed, eta, total size updates
    
    def __init__(self, manager, differences):
        super().__init__()
        self.manager = manager
        self.differences = differences
        self.total_files = len(differences['to_copy']) + len(differences['to_update'])
        self.current_file_number = 0
        self.start_time = None
        self.total_size = 0
        self.processed_size = 0
        self.current_speed = 0
        self.last_update_time = 0
        self.last_processed_size = 0
        
        # Calculate total size
        for file_type in ['to_copy', 'to_update']:
            for file_path in differences[file_type]:
                try:
                    full_path = Path(self.manager.source_path) / file_path
                    self.total_size += full_path.stat().st_size
                except Exception as e:
                    logger.warning(f"Failed to get size for {file_path}: {e}")
        
    def format_size(self, size_in_bytes):
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size_in_bytes < 1024:
                return f"{size_in_bytes:.1f} {unit}"
            size_in_bytes /= 1024
        return f"{size_in_bytes:.1f} TB"
        
    def format_speed(self, bytes_per_sec):
        return f"{self.format_size(bytes_per_sec)}/s"
        
    def format_time(self, seconds):
        if seconds < 60:
            return f"{seconds:.0f}s"
        elif seconds < 3600:
            minutes = seconds / 60
            return f"{minutes:.0f}m"
        else:
            hours = seconds / 3600
            return f"{hours:.1f}h"
        
    def update_stats(self, current_size):
        current_time = time.time()
        if current_time - self.last_update_time >= 1:  # Update every second
            # Update speed
            size_delta = current_size - self.last_processed_size
            time_delta = current_time - self.last_update_time
            if time_delta > 0:
                self.current_speed = size_delta / time_delta
            
            # Update ETA
            if self.current_speed > 0:
                remaining_size = self.total_size - current_size
                eta_seconds = remaining_size / self.current_speed
            else:
                eta_seconds = 0
                
            # Emit stats update
            self.stats_update.emit({
                'speed': self.format_speed(self.current_speed),
                'eta': self.format_time(eta_seconds),
                'processed_size': self.format_size(current_size),
                'total_size': self.format_size(self.total_size),
                'percent': (current_size / self.total_size * 100) if self.total_size > 0 else 0
            })
            
            self.last_update_time = current_time
            self.last_processed_size = current_size
        
    def run(self):
        try:
            self.start_time = time.time()
            self.last_update_time = self.start_time
            source_path = Path(self.manager.source_path)
            source_drive = str(source_path.anchor)
            source_preview = str(source_path.relative_to(source_path.anchor).parts[0])
            
            # Emit initial stats
            self.stats_update.emit({
                'speed': '0 B/s',
                'eta': '...',
                'processed_size': '0 B',
                'total_size': self.format_size(self.total_size),
                'percent': 0
            })
            
            def progress_callback(progress: float, current_file: str = None):
                if current_file:
                    self.current_file_number += 1
                    full_path = str(Path(self.manager.source_path) / current_file)
                    file_size = Path(full_path).stat().st_size
                    self.processed_size += file_size
                    size_str = self.format_size(file_size)
                    
                    self.current_file.emit(full_path, size_str)
                    truncated_file = truncate_path(current_file, 50)
                    
                    self.update_stats(self.processed_size)
                    self.progress.emit(progress)
                    
                    self.status.emit(
                        f"Creating backup [{source_drive}{source_preview}/...] - "
                        f"{truncated_file} ({self.current_file_number}/{self.total_files} files)"
                    )
            
            success = self.manager.perform_backup(
                self.differences,
                progress_callback
            )
            if success:
                total_time = time.time() - self.start_time
                avg_speed = self.total_size / total_time if total_time > 0 else 0
                self.finished.emit(True, 
                    f"Backup completed successfully!\n"
                    f"Total size: {self.format_size(self.total_size)}\n"
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
    
    def __init__(self, manager, source_path, dest_path):
        super().__init__()
        self.manager = manager
        self.source_path = source_path
        self.dest_path = dest_path
        
    def run(self):
        try:
            source_path = Path(self.source_path)
            dest_path = Path(self.dest_path)
            source_drive = str(source_path.anchor)
            dest_drive = str(dest_path.anchor)
            source_preview = str(source_path.relative_to(source_path.anchor).parts[0])
            dest_preview = str(dest_path.relative_to(dest_path.anchor).parts[0])
            
            self.status.emit(f"Analyzing paths... [Source: {source_drive}{source_preview}/...] [Destination: {dest_drive}{dest_preview}/...]")
            success, message = self.manager.analyze_paths(self.source_path, self.dest_path)
            if not success:
                self.finished.emit(False, message, {})
                return

            def progress_update(msg: str):
                if msg.startswith("Scanning:"):
                    file_path = msg[9:].strip()
                    # Extract the part in parentheses if it exists
                    file_count = ""
                    if "(" in file_path:
                        file_path, file_count = file_path.rsplit("(", 1)
                        file_count = f" ({file_count}"
                    
                    full_path = str(Path(self.source_path) / file_path)
                    status_msg = f"Scanning [{source_drive}{source_preview}/...] - {file_path}{file_count}"
                    self.status.emit(status_msg)
                    self.current_file.emit(full_path)

            differences = self.manager.analyze_differences(
                progress_callback=progress_update
            )
            
            total_files = len(differences['to_copy']) + len(differences['to_update'])
            if total_files == 0:
                self.finished.emit(True, "No files need to be updated", differences)
            else:
                self.finished.emit(True, f"Found {total_files} files to process", differences)
                
        except Exception as e:
            logger.error(f"Scan error: {e}")
            self.finished.emit(False, str(e), {})

class MainWindow(QMainWindow):
    def __init__(self, config):
        super().__init__()
        self.config = config
        self.backup_manager = BackupManager()
        self.setup_ui()
        self.scanning = False
        self.backing_up = False
        
    def setup_ui(self):
        self.setWindowTitle("Backup Tool")
        self.setFixedSize(
            self.config['interface']['window_size']['width'],
            self.config['interface']['window_size']['height']
        )
        
        # Main widget and layout
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        layout = QVBoxLayout(main_widget)
        
        # Paths group
        paths_group = QGroupBox("Paths")
        paths_layout = QVBoxLayout()
        
        # Source path
        source_layout = QHBoxLayout()
        self.source_path = QLineEdit()
        source_browse = QPushButton("Browse")
        source_browse.clicked.connect(lambda: self.browse_path("source"))
        source_layout.addWidget(QLabel("Source:"))
        source_layout.addWidget(self.source_path)
        source_layout.addWidget(source_browse)
        
        # Destination path
        dest_layout = QHBoxLayout()
        self.dest_path = QLineEdit()
        dest_browse = QPushButton("Browse")
        dest_browse.clicked.connect(lambda: self.browse_path("destination"))
        dest_layout.addWidget(QLabel("Destination:"))
        dest_layout.addWidget(self.dest_path)
        dest_layout.addWidget(dest_browse)
        
        paths_layout.addLayout(source_layout)
        paths_layout.addLayout(dest_layout)
        paths_group.setLayout(paths_layout)
        layout.addWidget(paths_group)
        
        # Options group
        options_group = QGroupBox("Options")
        options_layout = QVBoxLayout()
        
        self.auto_mode = QCheckBox("Auto mode (skip confirmations)")
        self.verify_mode = QCheckBox("Verify files after copy")
        self.verify_mode.setChecked(self.config['backup']['verify_after_copy'])
        
        options_layout.addWidget(self.auto_mode)
        options_layout.addWidget(self.verify_mode)
        options_group.setLayout(options_layout)
        layout.addWidget(options_group)
        
        # Progress group
        progress_group = QGroupBox("Progress")
        progress_layout = QVBoxLayout()
        
        # Progress bar with percentage
        progress_bar_layout = QHBoxLayout()
        self.progress_bar = AnimatedProgressBar()
        self.progress_percent = QLabel("0%")
        progress_bar_layout.addWidget(self.progress_bar)
        progress_bar_layout.addWidget(self.progress_percent)
        
        # Status label
        self.status_label = QLabel("Ready")
        self.status_label.setWordWrap(False)
        
        # Stats layout
        stats_layout = QHBoxLayout()
        self.speed_label = QLabel("Speed: 0 B/s")
        self.eta_label = QLabel("ETA: ...")
        self.size_label = QLabel("Size: 0 B / 0 B")
        stats_layout.addWidget(self.speed_label)
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
        
        # Buttons
        button_layout = QHBoxLayout()
        self.start_button = QPushButton("Start Backup")
        self.start_button.clicked.connect(self.start_backup)
        
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.clicked.connect(self.cancel_backup)
        self.cancel_button.setEnabled(False)
        
        button_layout.addWidget(self.start_button)
        button_layout.addWidget(self.cancel_button)
        layout.addLayout(button_layout)
        
        self.apply_theme()
        
    def apply_theme(self):
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
            
    def browse_path(self, path_type):
        dialog = QFileDialog(self)
        dialog.setFileMode(QFileDialog.FileMode.Directory)
        dialog.setOption(QFileDialog.Option.ShowDirsOnly, True)
        
        if dialog.exec() == QFileDialog.DialogCode.Accepted:
            selected = dialog.selectedFiles()[0]
            if path_type == "source":
                self.source_path.setText(selected)
            else:
                self.dest_path.setText(selected)
                
    def start_backup(self):
        if self.scanning or self.backing_up:
            return
            
        source = self.source_path.text().strip()
        dest = self.dest_path.text().strip()
        
        if not source or not dest:
            QMessageBox.warning(self, "Error", "Please select both paths")
            return
            
        # Configure backup manager
        self.backup_manager.source_path = source
        self.backup_manager.dest_path = dest
        
        # Disable UI during scan
        self.scanning = True
        self.update_ui_state()
        self.status_label.setText("Scanning...")
        self.progress_bar.setValue(0)
        
        # Start scan thread
        self.scan_thread = ScanThread(self.backup_manager, source, dest)
        self.scan_thread.status.connect(self.update_status)
        self.scan_thread.current_file.connect(self.update_current_file)
        self.scan_thread.finished.connect(self.scan_finished)
        self.scan_thread.start()
        
    def scan_finished(self, success, message, differences):
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
        if self.scanning and hasattr(self, 'scan_thread'):
            self.scan_thread.terminate()
            self.scanning = False
            
        if self.backing_up and hasattr(self, 'backup_thread'):
            self.backup_thread.terminate()
            self.backing_up = False
            
        self.update_ui_state()
        self.status_label.setText("Cancelled")
        
    def update_progress(self, value):
        self.progress_bar.setValue(int(value))
        self.progress_percent.setText(f"{int(value)}%")
        
    def update_status(self, message):
        self.status_label.setText(message)
        
    def backup_finished(self, success, message):
        self.backing_up = False
        self.update_ui_state()
        
        if success:
            QMessageBox.information(self, "Success", message)
        else:
            QMessageBox.critical(self, "Error", message)
            
    def update_ui_state(self):
        """Update UI elements based on current state."""
        enabled = not (self.scanning or self.backing_up)
        self.start_button.setEnabled(enabled)
        self.source_path.setEnabled(enabled)
        self.dest_path.setEnabled(enabled)
        self.auto_mode.setEnabled(enabled)
        self.verify_mode.setEnabled(enabled)
        
        self.cancel_button.setEnabled(not enabled) 
        
    def update_current_file(self, file_path, size=None):
        """Update current file being processed."""
        truncated_path = truncate_path(str(file_path), 80)  # Shorter max length
        self.current_file_label.setText(truncated_path)
        if size:
            self.file_size_label.setText(f"Size: {size}")
        
    def update_stats(self, stats):
        self.speed_label.setText(f"Speed: {stats['speed']}")
        self.eta_label.setText(f"ETA: {stats['eta']}")
        self.size_label.setText(f"Size: {stats['processed_size']} / {stats['total_size']}")
        self.progress_percent.setText(f"{int(stats['percent'])}%")
