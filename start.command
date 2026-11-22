#!/bin/bash
# Double-click to start Shortsmith. It opens in your browser.
# A double-clicked script gets a bare PATH; make sure uv is findable.
export PATH="$HOME/.local/bin:/opt/homebrew/bin:$PATH"
cd "$(dirname "$0")/backend" || exit 1
uv run python -m app
