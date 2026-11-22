#!/bin/bash
# Double-click to start Shortsmith. It opens in your browser.
cd "$(dirname "$0")/backend" || exit 1
uv run python -m app
