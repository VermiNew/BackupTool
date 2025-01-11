from PyQt6.QtWidgets import QProgressBar
from PyQt6.QtCore import QPropertyAnimation, QEasingCurve, Qt, pyqtProperty, QTimer
from PyQt6.QtGui import QColor

class AnimatedProgressBar(QProgressBar):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._color = QColor("#3498db")
        
        # Setup animations
        self.value_anim = QPropertyAnimation(self, b"value")
        self.value_anim.setDuration(250)
        self.value_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        
        self.color_anim = QPropertyAnimation(self, b"color")
        self.color_anim.setDuration(500)
        self.color_anim.setEasingCurve(QEasingCurve.Type.InOutQuad)
        
        # Setup update timer for smooth progress
        self.update_timer = QTimer()
        self.update_timer.setInterval(16)  # ~60 FPS
        self.update_timer.timeout.connect(self.smooth_update)
        
        self.target_value = 0
        self.current_value = 0
        self.smoothing_factor = 0.15
        
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setTextVisible(True)
        self.setMinimum(0)
        self.setMaximum(100)
        
        self.apply_style()
        
    def apply_style(self):
        self.setStyleSheet(f"""
            QProgressBar {{
                border: 1px solid #2c2c2c;
                border-radius: 5px;
                text-align: center;
                background-color: #1a1a1a;
                height: 20px;
            }}
            QProgressBar::chunk {{
                background-color: {self._color.name()};
                border-radius: 4px;
            }}
        """)
        
    def smooth_update(self):
        """Update progress smoothly"""
        if abs(self.target_value - self.current_value) < 0.1:
            self.current_value = self.target_value
            self.update_timer.stop()
        else:
            self.current_value += (self.target_value - self.current_value) * self.smoothing_factor
            
        super().setValue(round(self.current_value))
        
    def setValue(self, value):
        """Set progress value with smooth animation"""
        self.target_value = value
        if not self.update_timer.isActive():
            self.update_timer.start()
        
    def set_color(self, color):
        """Set progress bar color"""
        if isinstance(color, str):
            color = QColor(color)
        self._color = color
        self.apply_style()
        
    def get_color(self):
        """Get current progress bar color"""
        return self._color
        
    # Define the color property
    color = pyqtProperty(QColor, get_color, set_color)
    
    def setColor(self, color):
        """Set color with animation"""
        self.color_anim.setStartValue(self._color)
        self.color_anim.setEndValue(QColor(color))
        self.color_anim.start() 