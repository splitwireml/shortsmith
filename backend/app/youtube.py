"""YouTube: the only file that imports the Google API clients.

Connect (the installed-app sign-in that used to live in
`scripts/youtube_connect.py`), connection status, upload, and the
numbers behind snapshots — call shapes exactly as in
docs/research.md §5. Everything here is plain sync code; callers run
it in a thread. The token file's contents are a secret: they are
loaded for Google's own libraries and never returned or logged.

While the owner's Google app is in “Testing” the sign-in expires
every 7 days; a failed refresh surfaces as `needs_reconnect`, never
as a crash (Y3).
"""

import logging
import random
import threading
import time
import uuid
from datetime import date
from pathlib import Path

from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload

from app.config import REPO_ROOT, Config

log = logging.getLogger(__name__)

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.readonly",
    "https://www.googleapis.com/auth/yt-analytics.readonly",
]

NOT_CONNECTED_MESSAGE = "YouTube is not connected yet. Connect YouTube first, then press Retry."
EXPIRED_MESSAGE = "Your YouTube sign-in has expired. Reconnect YouTube, then press Retry."
THUMBNAIL_NOTE = (
    "Your video was published, but its thumbnail picture could not be set. "
    "You can add one in YouTube Studio."
)
UNCERTAIN_UPLOAD_MESSAGE = (
    "The upload did not finish, so it is not clear whether YouTube received it. "
    "Check your YouTube channel; if the video is not there, press Retry."
)
# How long a status answer may be reused before credentials are checked
# again — long enough to spare quota on 5-second polls, short enough
# that a 7-day “Testing” expiry shows up within the minute.
_STATUS_CACHE_SECONDS = 60

_RETRIABLE_STATUSES = {500, 502, 503, 504}
_MAX_UPLOAD_RETRIES = 10
# Thumbnail polling: at most about ten minutes of processing.
_PROCESSING_TRIES = 60
_PROCESSING_WAIT_SECONDS = 10


class NotConnected(RuntimeError):
    """No usable YouTube sign-in; the message is for the user.

    `confirmed` means the sign-in is really dead (invalid/revoked
    grant or an unreadable token file), as opposed to a refresh that
    merely failed on the way to Google and may work on the next poll.
    Only a confirmed failure may be cached as `needs_reconnect`.
    """

    def __init__(self, message: str, *, confirmed: bool = True):
        super().__init__(message)
        self.confirmed = confirmed


def _save_token(config: Config, creds: Credentials) -> None:
    config.youtube_token_path.parent.mkdir(parents=True, exist_ok=True)
    config.youtube_token_path.write_text(creds.to_json())
    config.youtube_token_path.chmod(0o600)


def _load_credentials(config: Config) -> Credentials:
    """The saved sign-in, refreshed if needed. Raises NotConnected."""
    if not config.youtube_token_path.is_file():
        raise NotConnected(NOT_CONNECTED_MESSAGE)
    try:
        creds = Credentials.from_authorized_user_file(str(config.youtube_token_path), SCOPES)
    except Exception:
        raise NotConnected(EXPIRED_MESSAGE) from None
    if creds.valid:
        return creds
    if creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
        except RefreshError:  # Google itself refused: the grant is dead
            raise NotConnected(EXPIRED_MESSAGE) from None
        except Exception:  # never reached Google; the next poll may work
            raise NotConnected(EXPIRED_MESSAGE, confirmed=False) from None
        _save_token(config, creds)
        return creds
    raise NotConnected(EXPIRED_MESSAGE)


_connect_thread: threading.Thread | None = None
_connect_lock = threading.Lock()


def _run_connect(config: Config, client_secrets: Path) -> None:
    try:
        flow = InstalledAppFlow.from_client_secrets_file(str(client_secrets), SCOPES)
        creds = flow.run_local_server(
            port=0, access_type="offline", prompt="consent", timeout_seconds=10 * 60
        )
        _save_token(config, creds)
    except Exception:  # noqa: BLE001 — the UI polls status and can try again
        log.exception("YouTube connect did not finish")


def connect(config: Config) -> None:
    """Start the browser sign-in in the background and return at once.

    The UI polls `status()` until the saved token appears.
    """
    client_secrets = REPO_ROOT / "credentials.json"
    if not client_secrets.is_file():
        raise RuntimeError(
            "The Google sign-in file (credentials.json) is missing from the "
            "Shortsmith folder, so YouTube cannot be connected yet."
        )
    global _connect_thread
    with _connect_lock:
        if _connect_thread is not None and _connect_thread.is_alive():
            raise RuntimeError(
                "A Google sign-in window is already open. Finish signing in "
                "there — or, if you closed it, wait a few minutes and press "
                "Connect again."
            )
        _connect_thread = threading.Thread(
            target=_run_connect, args=(config, client_secrets), daemon=True,
            name="youtube-connect",
        )
        _connect_thread.start()


def disconnect(config: Config) -> None:
    """Forget the saved sign-in, so the page offers a fresh Connect."""
    config.youtube_token_path.unlink(missing_ok=True)


# ponytail: one-entry cache keyed by the token file, held only for
# `_STATUS_CACHE_SECONDS` — the UI polls every few seconds, but a
# sign-in can also expire without the file changing (7-day “Testing”
# tokens), so a cached green must regularly re-check credentials.
# (token path, token mtime, expiry instant, result)
_status_cache: tuple[str, float, float, dict] | None = None


def status(config: Config) -> dict:
    """{connected, channel_title, needs_reconnect} — never raises (Y3)."""
    never = {"connected": False, "channel_title": None, "needs_reconnect": False}
    if not config.youtube_token_path.is_file():
        return never
    global _status_cache
    key = (str(config.youtube_token_path), config.youtube_token_path.stat().st_mtime)
    if (
        _status_cache is not None
        and _status_cache[:2] == key
        and time.monotonic() < _status_cache[2]
    ):
        return dict(_status_cache[3])

    def remember(result: dict) -> dict:
        global _status_cache
        _status_cache = (
            key[0],
            config.youtube_token_path.stat().st_mtime,
            time.monotonic() + _STATUS_CACHE_SECONDS,
            result,
        )
        return dict(result)

    try:
        creds = _load_credentials(config)
    except NotConnected as exc:
        result = {"connected": False, "channel_title": None, "needs_reconnect": True}
        # A refresh that never reached Google is not proof the sign-in
        # is dead; let the next poll try again instead of caching it.
        return remember(result) if exc.confirmed else dict(result)
    title = None
    try:
        yt = build("youtube", "v3", credentials=creds, cache_discovery=False)
        items = yt.channels().list(part="snippet", mine=True).execute().get("items", [])
        if items:
            title = items[0].get("snippet", {}).get("title")
    except Exception:  # noqa: BLE001 — valid sign-in, channel name unknown
        log.exception("Could not read the connected channel's name")
    result = {"connected": True, "channel_title": title, "needs_reconnect": False}
    if title is not None:  # an unknown name may just be a blip; retry next poll
        return remember(result)
    return dict(result)


def _wait_processed(yt, youtube_id: str) -> bool:
    for _ in range(_PROCESSING_TRIES):
        items = yt.videos().list(part="processingDetails", id=youtube_id).execute().get("items", [])
        state = items[0].get("processingDetails", {}).get("processingStatus") if items else None
        if state == "succeeded":
            return True
        if state == "failed":
            return False
        time.sleep(_PROCESSING_WAIT_SECONDS)
    return False


def upload(
    config: Config,
    *,
    video_path: Path,
    title: str,
    description: str,
    tags: list[str],
    privacy: str,
    practice: bool = False,
) -> str:
    """Upload one video and return its YouTube id as soon as it exists.

    The caller saves the id before any thumbnail work (`set_thumbnail`
    is a separate best-effort step), so a restart can never lose a
    video YouTube already received. Practice mode returns a fake
    `practice-…` id with no network (V5).
    """
    if practice:
        return f"practice-{uuid.uuid4().hex[:8]}"
    creds = _load_credentials(config)
    yt = build("youtube", "v3", credentials=creds, cache_discovery=False)
    request = yt.videos().insert(
        part="snippet,status",
        body={
            "snippet": {
                "title": title,
                "description": description,
                "tags": tags,
                "categoryId": "22",
            },
            "status": {
                "privacyStatus": privacy,
                "selfDeclaredMadeForKids": False,
                "containsSyntheticMedia": True,
            },
        },
        media_body=MediaFileUpload(str(video_path), chunksize=-1, resumable=True),
    )
    response = None
    retries = 0
    while response is None:
        try:
            _, response = request.next_chunk()
        except HttpError as exc:
            if exc.resp.status not in _RETRIABLE_STATUSES:
                raise RuntimeError(
                    "YouTube could not accept the upload just now. Press Retry to try again."
                ) from None
            if retries >= _MAX_UPLOAD_RETRIES:
                # Retriable failures outlasted us: YouTube may or may not
                # have the video, so do not ask for a blind retry.
                raise RuntimeError(UNCERTAIN_UPLOAD_MESSAGE) from None
            retries += 1
            time.sleep(random.random() * 2**retries)
        except OSError:
            if retries >= _MAX_UPLOAD_RETRIES:
                raise RuntimeError(UNCERTAIN_UPLOAD_MESSAGE) from None
            retries += 1
            time.sleep(random.random() * 2**retries)
    return response["id"]


def set_thumbnail(config: Config, youtube_id: str, thumbnail_path: Path) -> str | None:
    """Best effort: set the thumbnail once processing has succeeded.

    Returns None on success (and for practice ids, which never
    reached YouTube), or a plain note for the video page. Never
    raises — the publish it follows already succeeded.
    """
    if youtube_id.startswith("practice-") or not Path(thumbnail_path).is_file():
        return None
    try:
        creds = _load_credentials(config)
        yt = build("youtube", "v3", credentials=creds, cache_discovery=False)
        if not _wait_processed(yt, youtube_id):
            log.warning("YouTube was still processing %s; thumbnail not set", youtube_id)
            return THUMBNAIL_NOTE
        yt.thumbnails().set(
            videoId=youtube_id, media_body=MediaFileUpload(str(thumbnail_path))
        ).execute()
        return None
    except Exception:  # noqa: BLE001 — noted on the video, never fatal
        log.exception("Published %s but could not set its thumbnail", youtube_id)
        return THUMBNAIL_NOTE


def fetch_stats(config: Config, youtube_id: str, *, with_analytics: bool) -> dict:
    """Current numbers for one video, keyed by Snapshot field names.

    Views, likes and comments come from the Data API; from the 72 h
    checkpoint on, the Analytics API adds average view time, shares
    and subscribers gained (it lags 48–72 h, so earlier it has none).
    """
    creds = _load_credentials(config)
    yt = build("youtube", "v3", credentials=creds, cache_discovery=False)
    items = yt.videos().list(part="statistics", id=youtube_id).execute().get("items", [])
    if not items:
        raise RuntimeError("That video could not be found on YouTube.")
    stats = items[0].get("statistics", {})
    numbers: dict = {
        "views": int(stats.get("viewCount", 0)),
        "likes": int(stats.get("likeCount", 0)),
        "comments": int(stats.get("commentCount", 0)),
    }
    if with_analytics:
        # Analytics is a bonus on top of the counts above: if it fails
        # (it lags 48–72 h and can be empty), the Data API numbers are
        # still saved and the extra fields simply stay empty.
        try:
            analytics = build("youtubeAnalytics", "v2", credentials=creds, cache_discovery=False)
            report = analytics.reports().query(
                ids="channel==MINE",
                # No publish date is passed in; a lifetime range gives totals.
                startDate="2005-01-01",
                endDate=date.today().isoformat(),
                metrics="averageViewDuration,averageViewPercentage,shares,subscribersGained",
                filters=f"video=={youtube_id}",
            ).execute()
        except Exception:  # noqa: BLE001 — counts above are still worth saving
            log.exception("Analytics numbers unavailable for %s", youtube_id)
            return numbers
        rows = report.get("rows", [])
        if rows:
            by_metric = {
                header["name"]: value
                for header, value in zip(report.get("columnHeaders", []), rows[0], strict=False)
            }
            numbers |= {
                "avg_view_seconds": float(by_metric.get("averageViewDuration", 0.0)),
                "avg_view_percent": float(by_metric.get("averageViewPercentage", 0.0)),
                "shares": int(by_metric.get("shares", 0)),
                "subscribers_gained": int(by_metric.get("subscribersGained", 0)),
            }
    return numbers
