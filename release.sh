#!/bin/bash
cd "$(dirname "$0")"
source .venv/bin/activate
python3 src/build_episode.py
python3 src/liturgy/feed.py
