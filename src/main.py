import sys
import logging
from pathlib import Path
from PyQt6.QtWidgets import QApplication, QSystemTrayIcon
from PyQt6.QtGui import QIcon
from PyQt6.QtCore import Qt

from .gui.main_window import MainWindow
from .utils.logger import setup_logger
from .utils.config import load_config

def main():
    try:
        # Load configuration
        config, config_path = load_config()
        
        # Setup logger
        log_dir = Path(config.get('logging', {}).get('directory', 'logs'))
        logger = setup_logger(log_dir)
        logger.info("Starting backup application")
        
        # Create Qt application
        app = QApplication(sys.argv)
        
        # Ensure application doesn't quit when last window is closed
        # but only if system tray is available
        if QSystemTrayIcon.isSystemTrayAvailable():
            app.setQuitOnLastWindowClosed(False)
        
        # Check if system tray is supported
        if not QSystemTrayIcon.isSystemTrayAvailable():
            logger.warning("System tray is not available")
            config['interface']['minimize_to_tray'] = False
            config['tray']['actions']['minimize_to_tray'] = False
            config['tray']['actions']['close_to_tray'] = False
            # If tray is not available, make sure app quits on window close
            app.setQuitOnLastWindowClosed(True)
        
        # Set application style and icon
        if config.get('interface', {}).get('dark_mode', True):
            app.setStyle('Fusion')
        
        icon_path = Path(__file__).parent / 'resources' / 'images' / 'icon.png'
        if icon_path.exists():
            app_icon = QIcon(str(icon_path))
            app.setWindowIcon(app_icon)
        
        # Create main window
        window = MainWindow(config, config_path)
        
        # Show window based on configuration
        if config.get('tray', {}).get('actions', {}).get('start_minimized', False):
            if config['interface']['minimize_to_tray']:
                logger.info("Starting minimized to tray")
            else:
                logger.info("Starting minimized")
                window.showMinimized()
        else:
            window.show()
        
        # Start application event loop
        exit_code = app.exec()
        
        # Ensure proper cleanup
        app.quit()
        return exit_code
        
    except Exception as e:
        logging.critical(f"Application failed to start: {e}", exc_info=True)
        return 1

if __name__ == '__main__':
    sys.exit(main()) 