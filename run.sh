#!/usr/bin/env bash
# Launch The Blockheads – PC Edition
set -e
cd "$(dirname "$0")"

# Install dependencies if needed
if ! python3 -c "import pygame, numpy" 2>/dev/null; then
    echo "Installing dependencies..."
    pip install -r requirements.txt -q
fi

python3 main.py "$@"
