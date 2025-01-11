from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QLabel, QPushButton,
    QTextEdit, QDialogButtonBox
)
from PyQt6.QtCore import Qt

from ..utils.helpers import format_size

class PathVerificationDialog(QDialog):
    def __init__(self, differences, parent=None):
        super().__init__(parent)
        self.differences = differences
        self.setup_ui()
        
    def setup_ui(self):
        self.setWindowTitle("Backup Verification")
        self.setFixedWidth(500)
        
        layout = QVBoxLayout(self)
        
        # Summary
        to_copy = len(self.differences['to_copy'])
        to_update = len(self.differences['to_update'])
        to_delete = len(self.differences['to_delete'])
        
        summary = QLabel(
            f"Files to copy: {to_copy}\n"
            f"Files to update: {to_update}\n"
            f"Files to delete: {to_delete}"
        )
        layout.addWidget(summary)
        
        # Details
        if to_delete > 0:
            layout.addWidget(QLabel("\nFiles to be deleted:"))
            delete_text = QTextEdit()
            delete_text.setPlainText("\n".join(self.differences['to_delete']))
            delete_text.setReadOnly(True)
            delete_text.setMaximumHeight(100)
            layout.addWidget(delete_text)
            
        # Buttons
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | 
            QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons) 