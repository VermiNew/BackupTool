# BackupTool

A Python-based backup application with GUI that intelligently copies files by comparing metadata.

## Features

- GUI interface built with PyQt6
- Smart backup that only copies changed files
- Progress bar with ETA and speed information
- Error handling with user prompts
- Logging functionality
- Support for network drives
- File metadata comparison (size and modification time)

## Requirements

- Python 3.8 or higher
- Dependencies listed in `requirements.txt`

## Installation

1. Clone this repository
2. Install the required packages:
```bash
pip install -r requirements.txt
```

## Usage

1. Run the application:
```bash
python main.py
```

2. Select source and destination directories using the GUI
3. Click "Start Backup" to begin the backup process
4. Monitor progress through the progress bar and status information
5. Use the "Stop" button to interrupt the backup process if needed

## Error Handling

- The application will show a message box when errors occur
- You can choose to continue or stop the backup process
- All errors are logged to `backup_app.log`

## Logging

- Log file location: `backup_app.log`
- Maximum log file size: 100 MB
- Logs include timestamps and error details