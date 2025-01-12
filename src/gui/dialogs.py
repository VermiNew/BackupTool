from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QDialogButtonBox, QTableWidget, QComboBox,
    QTableWidgetItem, QHeaderView, QLineEdit, QCheckBox
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor
from typing import Dict, List
import logging

from ..utils.helpers import format_size, get_file_info

logger = logging.getLogger(__name__)

class PathVerificationDialog(QDialog):
    """Dialog for verifying backup paths and operations."""
    
    OPERATIONS = {
        'copy': {'text': 'Copy', 'color': QColor('#4CAF50')},  # Green
        'update': {'text': 'Update', 'color': QColor('#2196F3')},  # Blue
        'move': {'text': 'Move', 'color': QColor('#FF9800')},  # Orange
        'delete': {'text': 'Delete', 'color': QColor('#F44336')}  # Red
    }
    
    def __init__(self, differences: Dict, parent=None):
        """Initialize the dialog.
        
        Args:
            differences: Dictionary containing files to copy/update
            parent: Parent widget
        """
        super().__init__(parent)
        self.differences = differences
        self.filtered_items = []  # Store filtered items
        self.setup_ui()
        
    def setup_ui(self):
        """Setup the dialog UI."""
        self.setWindowTitle("Backup Verification")
        self.setFixedWidth(600)  # Increased width for better readability
        self.setMinimumHeight(500)  # Added minimum height
        
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        
        # Summary
        to_copy = len(self.differences['to_copy'])
        to_update = len(self.differences['to_update'])
        to_move = len(self.differences.get('to_move', []))
        to_delete = len(self.differences.get('to_delete', []))
        total_size = self.calculate_total_size()
        
        summary = QLabel(
            f"<b>Summary:</b><br>"
            f"Files to copy: <span style='color: #4CAF50'>{to_copy}</span><br>"
            f"Files to update: <span style='color: #2196F3'>{to_update}</span><br>"
            f"Files to move: <span style='color: #FF9800'>{to_move}</span><br>"
            f"Files to delete: <span style='color: #F44336'>{to_delete}</span><br>"
            f"Total files: {to_copy + to_update + to_move + to_delete}<br>"
            f"Total size: {format_size(total_size)}"
        )
        summary.setTextFormat(Qt.TextFormat.RichText)
        layout.addWidget(summary)
        
        # Filter controls
        filter_layout = QHBoxLayout()
        
        # Operation filter
        self.operation_filter = QComboBox()
        self.operation_filter.addItem("All Operations")
        for op in self.OPERATIONS.values():
            self.operation_filter.addItem(op['text'])
        self.operation_filter.currentTextChanged.connect(self.apply_filters)
        filter_layout.addWidget(QLabel("Operation:"))
        filter_layout.addWidget(self.operation_filter)
        
        # Path filter
        self.path_filter = QLineEdit()
        self.path_filter.setPlaceholderText("Filter by path...")
        self.path_filter.textChanged.connect(self.apply_filters)
        filter_layout.addWidget(QLabel("Path:"))
        filter_layout.addWidget(self.path_filter)
        
        # Size filter
        self.size_filter = QComboBox()
        self.size_filter.addItems(["All Sizes", "< 1MB", "1MB - 10MB", "10MB - 100MB", "100MB - 1GB", "> 1GB"])
        self.size_filter.currentTextChanged.connect(self.apply_filters)
        filter_layout.addWidget(QLabel("Size:"))
        filter_layout.addWidget(self.size_filter)
        
        layout.addLayout(filter_layout)
        
        # Files table
        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["Operation", "Path", "Size", "Status"])
        
        # Set table properties
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.setShowGrid(True)
        self.table.setStyleSheet("""
            QTableWidget {
                gridline-color: #d0d0d0;
                selection-background-color: #e0e0e0;
            }
            QTableWidget::item {
                padding: 5px;
            }
        """)
        
        layout.addWidget(self.table)
            
        # Buttons
        button_layout = QHBoxLayout()
        
        # Select all checkbox
        self.select_all = QCheckBox("Select All")
        self.select_all.stateChanged.connect(self.toggle_all_items)
        button_layout.addWidget(self.select_all)
        
        button_layout.addStretch()
        
        # Standard buttons
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | 
            QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        button_layout.addWidget(buttons)
        
        layout.addLayout(button_layout)
        
        # Populate table
        self.populate_table()
        
    def calculate_total_size(self) -> int:
        """Calculate total size of all files to be processed."""
        total = 0
        for path in self.differences['to_copy'] + self.differences['to_update']:
            try:
                file_info = get_file_info(path)
                if file_info:
                    total += file_info['size']
            except Exception as e:
                logger.warning(f"Failed to get size for {path}: {e}")
        return total
        
    def get_file_status(self, path: str, operation: str) -> str:
        """Get status information for a file."""
        try:
            file_info = get_file_info(path)
            if file_info:
                if operation == 'update':
                    return f"Modified: {file_info['modified']}"
                return f"Created: {file_info['created']}"
        except Exception as e:
            logger.warning(f"Failed to get status for {path}: {e}")
        return ""
        
    def populate_table(self):
        """Populate the table with files to process."""
        try:
            self.table.setRowCount(0)
            self.filtered_items.clear()
            
            operations = {
                'to_copy': ('copy', "Copy"),
                'to_update': ('update', "Update"),
                'to_move': ('move', "Move"),
                'to_delete': ('delete', "Delete")
            }
            
            for diff_key, (op_key, op_text) in operations.items():
                if diff_key not in self.differences:
                    continue
                    
                for path in self.differences[diff_key]:
                    try:
                        file_info = get_file_info(path)
                        size_str = format_size(file_info['size']) if file_info else "Unknown"
                        status = self.get_file_status(path, op_key)
                        
                        self.filtered_items.append({
                            'operation': op_key,
                            'path': path,
                            'size': file_info['size'] if file_info else 0,
                            'size_str': size_str,
                            'status': status
                        })
                    except Exception as e:
                        logger.warning(f"Failed to process {path}: {e}")
            
            self.apply_filters()
            
        except Exception as e:
            logger.error(f"Error populating table: {e}")
            self.reject()
            
    def apply_filters(self):
        """Apply filters to the table items."""
        try:
            self.table.setRowCount(0)
            
            operation_filter = self.operation_filter.currentText()
            path_filter = self.path_filter.text().lower()
            size_filter = self.size_filter.currentText()
            
            for item in self.filtered_items:
                # Apply operation filter
                if operation_filter != "All Operations" and operation_filter != self.OPERATIONS[item['operation']]['text']:
                    continue
                    
                # Apply path filter
                if path_filter and path_filter not in item['path'].lower():
                    continue
                    
                # Apply size filter
                size_mb = item['size'] / (1024 * 1024)
                if size_filter != "All Sizes":
                    if size_filter == "< 1MB" and size_mb >= 1:
                        continue
                    elif size_filter == "1MB - 10MB" and (size_mb < 1 or size_mb >= 10):
                        continue
                    elif size_filter == "10MB - 100MB" and (size_mb < 10 or size_mb >= 100):
                        continue
                    elif size_filter == "100MB - 1GB" and (size_mb < 100 or size_mb >= 1024):
                        continue
                    elif size_filter == "> 1GB" and size_mb < 1024:
                        continue
                
                # Add row
                row = self.table.rowCount()
                self.table.insertRow(row)
                
                # Operation
                op_item = QTableWidgetItem(self.OPERATIONS[item['operation']]['text'])
                op_item.setForeground(self.OPERATIONS[item['operation']]['color'])
                op_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                
                # Path
                path_item = QTableWidgetItem(item['path'])
                path_item.setToolTip(
                    f"Path: {item['path']}\n"
                    f"Size: {item['size_str']}\n"
                    f"Status: {item['status']}"
                )
                
                # Size
                size_item = QTableWidgetItem(item['size_str'])
                size_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                
                # Status
                status_item = QTableWidgetItem(item['status'])
                status_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                
                self.table.setItem(row, 0, op_item)
                self.table.setItem(row, 1, path_item)
                self.table.setItem(row, 2, size_item)
                self.table.setItem(row, 3, status_item)
            
        except Exception as e:
            logger.error(f"Error applying filters: {e}")
            
    def toggle_all_items(self, state):
        """Toggle selection of all visible items."""
        for row in range(self.table.rowCount()):
            self.table.item(row, 0).setSelected(state == Qt.CheckState.Checked)
            
    def get_selected_items(self) -> Dict[str, List[str]]:
        """Get dictionary of selected items grouped by operation."""
        selected = {
            'to_copy': [],
            'to_update': [],
            'to_move': [],
            'to_delete': []
        }
        
        for row in range(self.table.rowCount()):
            if self.table.item(row, 0).isSelected():
                operation = self.table.item(row, 0).text()
                path = self.table.item(row, 1).text()
                
                for op_key, op_data in self.OPERATIONS.items():
                    if op_data['text'] == operation:
                        selected[f'to_{op_key}'].append(path)
                        break
        
        return selected 