#!/bin/bash
# Starts the web dashboard (same as `vibemus web`), logging to data/web.log
cd "$(dirname "$0")/.."
python3 main.py web "$@" >> data/web.log 2>&1
