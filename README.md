# BackupTool

A Python-based backup application with GUI that intelligently copies files by comparing metadata.

## Features

- GUI interface built with PyQt6
- Smart backup that only copies changed files
- Progress bar with ETA and speed information
- File exclusion patterns (e.g., *.tmp, *.log)
- Detailed backup reports in JSON format
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
3. (Optional) Add file exclusion patterns in the Options section
4. Click "Start Backup" to begin the backup process
5. Monitor progress through the progress bar and status information
6. Use the "Stop" button to interrupt the backup process if needed

## File Exclusion

- Enter patterns in the "Exclude" field, separated by commas
- Supports glob patterns like *.tmp, *.log, temp/*, etc.
- Excluded files will be skipped during backup
- Patterns are saved in the configuration

## Backup Reports

- Location: `backup_report.json` in the destination directory
- Contains:
  - Start and end times
  - List of copied files
  - List of updated files
  - List of deleted files
  - Any errors that occurred
  - File sizes and timestamps

## Error Handling

- The application will show a message box when errors occur
- Confirmation dialogs for closing app or stopping backup
- You can choose to continue or stop the backup process
- All errors are logged to `backup_app.log`

## Logging

- Log file location: `backup_app.log`
- Maximum log file size: 100 MB
- Logs include timestamps and error details