@echo off

:: Check if virtual environment exists
if not exist .venv (
    echo Virtual environment not found. Please run setup.bat first.
    pause
    exit /b 1
)

:: Activate virtual environment
call .venv\Scripts\activate.bat

:: Add src to PYTHONPATH and run
set PYTHONPATH=%PYTHONPATH%;%~dp0
python -m src.main
pause 