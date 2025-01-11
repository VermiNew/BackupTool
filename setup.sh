#!/bin/bash

echo "Setting up Backup Tool..."

# Create virtual environment if it doesn't exist
if [ ! -d ".venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv .venv
fi

# Activate virtual environment
source .venv/bin/activate

# Install requirements
echo "Installing requirements..."
python3 -m pip install --upgrade pip
pip install -r requirements.txt

echo "Setup complete! You can now run the application using ./run.sh"
