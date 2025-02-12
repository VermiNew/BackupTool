from PyQt6.QtWidgets import QSystemTrayIcon, QMenu, QApplication
from PyQt6.QtGui import QIcon
from PyQt6.QtCore import QObject, pyqtSignal
from pathlib import Path
import logging

logger = logging.getLogger(__name__)

class TrayManager(QObject):
    """Manages system tray icon and its functionality."""
    
    # Signals
    show_window = pyqtSignal()  # Signal to show main window
    start_backup = pyqtSignal()  # Signal to start backup
    stop_backup = pyqtSignal()  # Signal to stop backup
    quit_app = pyqtSignal()     # Signal to quit application
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.tray_icon = None
        self.tray_menu = None
        self.app_name = "Backup Tool"
        # Create tray icon in the constructor to ensure proper thread affinity
        self.tray_icon = QSystemTrayIcon(parent)
        self.tray_menu = QMenu()
        self.setup_tray()
        
    def setup_tray(self):
        """Setup tray icon and menu."""
        if not self.tray_icon or not self.tray_menu:
            return
            
        # Add menu actions
        show_action = self.tray_menu.addAction("Show Window")
        show_action.triggered.connect(self.show_window.emit)
        
        self.tray_menu.addSeparator()
        
        start_action = self.tray_menu.addAction("Start Backup")
        start_action.triggered.connect(self.start_backup.emit)
        
        stop_action = self.tray_menu.addAction("Stop Backup")
        stop_action.triggered.connect(self.stop_backup.emit)
        stop_action.setEnabled(False)
        self.stop_action = stop_action
        
        self.tray_menu.addSeparator()
        
        quit_action = self.tray_menu.addAction("Exit")
        quit_action.triggered.connect(self._quit_application)
        
        # Set context menu
        self.tray_icon.setContextMenu(self.tray_menu)
        
        # Setup double click behavior
        self.tray_icon.activated.connect(self._handle_tray_activation)
        
        # Load default icon
        self.set_state('waiting')
        
        # Show tray icon
        self.tray_icon.show()
        
    def _handle_tray_activation(self, reason):
        """Handle tray icon activation."""
        # Only show window on double click
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self.show_window.emit()
            
    def _quit_application(self):
        """Handle quit action from tray menu."""
        # Hide tray icon immediately to prevent further interactions
        self.cleanup()
        # Emit quit signal
        self.quit_app.emit()
        
    def set_state(self, state: str, message: str = None):
        """Set tray icon state and tooltip.
        
        Args:
            state: Icon state ('backup', 'error', 'warning', 'waiting')
            message: Optional tooltip message
        """
        if not self.tray_icon:
            return
            
        # Get icon path
        icon_path = Path(__file__).parent.parent / 'resources' / 'images' / 'trays'
        icon_file = icon_path / f'tray_{state}.png'
        
        if not icon_file.exists():
            logger.error(f"Tray icon not found: {icon_file}")
            return
            
        # Set icon
        self.tray_icon.setIcon(QIcon(str(icon_file)))
        
        # Update tooltip
        state_messages = {
            'backup': 'Backup in progress...',
            'error': 'Backup error occurred',
            'warning': 'Warning',
            'waiting': 'Ready'
        }
        
        status = message if message else state_messages.get(state, 'Ready')
        self.tray_icon.setToolTip(f"{self.app_name} - {status}")
            
        # Update menu items
        self.stop_action.setEnabled(state == 'backup')
        
        # Update menu text based on state
        if state == 'backup':
            self.stop_action.setText("Stop Current Backup")
        else:
            self.stop_action.setText("Stop Backup")
        
    def show_message(self, title: str, message: str, icon_type=QSystemTrayIcon.MessageIcon.Information):
        """Show tray notification.
        
        Args:
            title: Notification title
            message: Notification message
            icon_type: Type of notification icon
        """
        if self.tray_icon:
            self.tray_icon.showMessage(title, message, icon_type)
        
    def cleanup(self):
        """Clean up tray icon before application exit."""
        if self.tray_icon:
            self.tray_icon.hide()
            self.tray_icon.setVisible(False)
            if self.tray_menu:
                self.tray_menu.clear()
                self.tray_menu = None
            self.tray_icon.deleteLater()
            self.tray_icon = None 