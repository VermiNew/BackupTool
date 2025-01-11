#!/bin/bash

# Check if virtual environment exists
if [ ! -d ".venv" ]; then
    echo "Virtual environment not found. Please run setup.sh first."
    exit 1
fi

# Activate virtual environment
source .venv/bin/activate

# Add src to PYTHONPATH and run
export PYTHONPATH=$PYTHONPATH:$(pwd)
python -m src.main 