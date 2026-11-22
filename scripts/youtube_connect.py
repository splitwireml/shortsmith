"""One-time YouTube sign-in. Opens the browser, saves the token to data/youtube_token.json.

Run: uv run --with google-auth-oauthlib python scripts/youtube_connect.py
"""
from pathlib import Path

from google_auth_oauthlib.flow import InstalledAppFlow

ROOT = Path(__file__).resolve().parent.parent
TOKEN_PATH = ROOT / "data" / "youtube_token.json"
SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.readonly",
    "https://www.googleapis.com/auth/yt-analytics.readonly",
]

if __name__ == "__main__":
    flow = InstalledAppFlow.from_client_secrets_file(ROOT / "credentials.json", SCOPES)
    creds = flow.run_local_server(port=0, access_type="offline", prompt="consent", timeout_seconds=6 * 3600)
    TOKEN_PATH.parent.mkdir(exist_ok=True)
    TOKEN_PATH.write_text(creds.to_json())
    TOKEN_PATH.chmod(0o600)
    print("YouTube connected. Token saved.")
