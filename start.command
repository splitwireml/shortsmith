#!/bin/bash
# Double-click to start Shortsmith. It opens in your browser.
# A double-clicked script gets a bare PATH; make sure Homebrew and uv are findable.
export PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:$PATH"
cd "$(dirname "$0")" || exit 1

# First start: install whichever tools are missing, through Homebrew.
missing=()
for tool in uv ffmpeg node pnpm; do
	command -v "$tool" >/dev/null || missing+=("$tool")
done
if [ ${#missing[@]} -gt 0 ]; then
	if ! command -v brew >/dev/null; then
		echo "Installing Homebrew first (it installs the other tools). It may ask for your Mac password."
		/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
		if ! command -v brew >/dev/null; then
			read -r -p "Homebrew did not install; see the messages above. Press Return to close."
			exit 1
		fi
	fi
	echo "Installing ${missing[*]} (first start only)…"
	if ! brew install "${missing[@]}"; then
		read -r -p "The install did not finish; see the messages above. Press Return to close."
		exit 1
	fi
fi

# First start: ask for the Gemini key and keep it in .env, readable only by you.
if [ ! -s .env ]; then
	echo "Paste your Gemini API key, then press Return."
	echo "(Make one at https://aistudio.google.com/apikey. It is saved only in this"
	echo " folder's .env file, and it stays hidden while you paste.)"
	read -r -s key
	(umask 077 && printf 'GEMINI_API_KEY=%s\n' "$key" >.env)
	echo "Saved."
fi

cd backend && exec uv run python -m app
