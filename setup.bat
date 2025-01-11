@echo off
echo Setting up Backup Tool...

:: Create virtual environment if it doesn't exist
if not exist .venv (
    echo Creating virtual environment...
    python -m venv .venv
)

:: Activate virtual environment
call .venv\Scripts\activate.bat

:: Install requirements
echo Installing requirements...
python -m pip install --upgrade pip
pip install -r requirements.txt

echo Setup complete! You can now run the application using run.bat
pause
