import sys
import logging
from pathlib import Path
from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QIcon

from .gui.main_window import MainWindow
from .utils.logger import setup_logger
from .utils.config import load_config

def main():
    try:
        # Load configuration
        config = load_config()
        
        # Setup logger
        log_dir = Path(config.get('logging', {}).get('directory', 'logs'))
        logger = setup_logger(log_dir)
        logger.info("Starting backup application")
        
        # Create Qt application
        app = QApplication(sys.argv)
        
        # Set application style and icon
        if config.get('interface', {}).get('dark_mode', True):
            app.setStyle('Fusion')
        
        icon_path = Path(__file__).parent / 'resources' / 'icon.png'
        if icon_path.exists():
            app.setWindowIcon(QIcon(str(icon_path)))
        
        # Create and show main window
        window = MainWindow(config)
        window.show()
        
        # Start application event loop
        return app.exec()
        
    except Exception as e:
        logging.critical(f"Application failed to start: {e}", exc_info=True)
        return 1

if __name__ == '__main__':
    sys.exit(main()) 