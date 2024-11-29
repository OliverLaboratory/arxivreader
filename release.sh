#!/bin/bash
cd "$(dirname "$0")"
source .venv/bin/activate
python3 src/main.py
python3 src/liturgy/feed.py
