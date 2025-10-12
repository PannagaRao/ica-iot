#!/bin/bash

# Check if Python is installed
if command -v python3 &>/dev/null; then
    echo "Python 3 is installed"
else
    echo "Python 3 is not installed"
    exit 1
fi

# Check if pip is installed
if command -v pip3 &>/dev/null; then
    echo "pip3 is installed"
else
    echo "pip3 is not installed"
    exit 1
fi

# Install requirements
if [ -f requirements.txt ]; then
    echo "requirements.txt found"
    pip3 install -r requirements.txt
else
    echo "requirements.txt not found"
    exit 1
fi

# Run Python scripts
if [ -f client.py ]; then
    echo "client.py found"
    python3 client.py &
else
    echo "client.py not found"
    exit 1
fi

if [ -f webserver.py ]; then
    echo "webserver.py found"
    python3 webserver.py &
else
    echo "webserver.py not found"
    exit 1
fi
