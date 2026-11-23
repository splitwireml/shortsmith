"""Video clips and thumbnails: the only file that imports google-genai.

Real calls use the Interactions API exactly as in docs/research.md §1–2:
video always asks for `delivery: "uri"` and downloads through the Files
API, with a long timeout because latency is undocumented. In practice
mode both make a coloured test file with ffmpeg instead (V5) — free,
instant, no network. Callers record the cost; practice results are
recorded at $0.
"""

import asyncio
import base64
import tempfile
from dataclasses import dataclass
from pathlib import Path

from google import genai
from google.genai import types

from app.config import Config
from app.models import Settings, UnitKind
from app.stitch import run_ffmpeg

# Generation can take minutes; a short HTTP timeout would cut it off.
TIMEOUT_SECONDS = 600

_COLOURS = ("0x2a9d8f", "0xe9c46a", "0xf4a261", "0xe76f51", "0x6a8eae", "0xbc6c25")


@dataclass(frozen=True)
class MediaResult:
    data: bytes
    units: float  # seconds of video, or 1 image — what the cost ledger counts
    unit_kind: UnitKind


class PaidButNotDelivered(RuntimeError):
    """Google accepted the clip (and charges for it) but its bytes never arrived.

    Raised only after a confirmed provider response, from the
    wait/download path. The caller records the clip's cost, then
    lets it propagate — the money was spent even though there is
    no file to show for it.
    """


def _client(config: Config) -> genai.Client:
    return genai.Client(
        api_key=config.gemini_api_key.get_secret_value(),
        http_options=types.HttpOptions(timeout=TIMEOUT_SECONDS * 1000),
    )


def check_key(config: Config) -> bool | None:
    """Whether Google accepts the key: True, False, or None if unanswered.

    A free metadata lookup on the planner model (its Settings default),
    with a short timeout so the home page never waits on it. An HTTP
    rejection is False (the key itself); no answer at all — offline,
    timeout, unknown model — is None, so the UI can say it could not
    check instead of blaming the key. No key configured is False.
    """
    if not config.gemini_api_key.get_secret_value():
        return False
    client = genai.Client(
        api_key=config.gemini_api_key.get_secret_value(),
        http_options=types.HttpOptions(timeout=5_000),
    )
    try:
        client.models.get(model=Settings().planner_model)
        return True
    except Exception as exc:  # noqa: BLE001 — sorted into an answer below
        return False if getattr(exc, "code", None) in (400, 401, 403) else None
    finally:
        client.close()


def _practice_clip(prompt: str, seconds: int) -> bytes:
    colour = _COLOURS[hash(prompt) % len(_COLOURS)]
    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tmp:
        path = Path(tmp.name)
    try:
        run_ffmpeg(
            [
                "-f", "lavfi", "-i", f"color=c={colour}:s=360x640:r=24:d={seconds}",
                "-f", "lavfi", "-i", "anullsrc=cl=stereo:r=48000",
                "-t", str(seconds),
                "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
                "-c:a", "aac", "-shortest", str(path),
            ],
            "Making the practice clip",
        )
        return path.read_bytes()
    finally:
        path.unlink(missing_ok=True)


def _practice_thumbnail(prompt: str) -> bytes:
    colour = _COLOURS[hash(prompt) % len(_COLOURS)]
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
        path = Path(tmp.name)
    try:
        run_ffmpeg(
            ["-f", "lavfi", "-i", f"color=c={colour}:s=720x1280:d=0.04", "-frames:v", "1", str(path)],
            "Making the practice thumbnail",
        )
        return path.read_bytes()
    finally:
        path.unlink(missing_ok=True)


async def wait_for_file(files, name: str, *, failed: str, slow: str) -> types.File:
    """Poll a Files API file until Google has finished processing it.

    `name` may be a file name or a full Files URI; the SDK extracts the
    name either way. Shared by clip download here and review upload in
    `agents/reviewer.py` — the two waits differ only in their messages.
    """
    for _ in range(120):
        remote = await files.get(name=name)
        state = getattr(remote.state, "name", str(remote.state))
        if state == "ACTIVE":
            return remote
        if state == "FAILED":
            raise RuntimeError(failed)
        await asyncio.sleep(5)
    raise RuntimeError(slow)


async def _download_video(client: genai.Client, uri: str) -> bytes:
    await wait_for_file(
        client.aio.files,
        uri,
        failed="The video service could not finish this clip. Press Retry to try again.",
        slow="The clip took too long to prepare. Press Retry to try again.",
    )
    data = await client.aio.files.download(file=uri)
    if not data:
        raise RuntimeError("The finished clip could not be downloaded. Press Retry to try again.")
    return data


def _to_png(data: bytes) -> bytes:
    """The thumbnail as PNG, converted only when it is not PNG already.

    The picture service may answer JPEG (its only listed output type);
    storage and the clip reference both promise PNG, so normalize here,
    once, where the bytes arrive.
    """
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return data
    with tempfile.NamedTemporaryFile(delete=False) as tmp:
        src = Path(tmp.name)
        src.write_bytes(data)
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
        dst = Path(tmp.name)
    try:
        run_ffmpeg(["-i", str(src), "-frames:v", "1", str(dst)], "Converting the thumbnail")
        return dst.read_bytes()
    finally:
        src.unlink(missing_ok=True)
        dst.unlink(missing_ok=True)


async def generate_clip(
    prompt: str,
    seconds: int,
    *,
    resolution: str,
    settings: Settings,
    config: Config,
    reference_image: bytes | None = None,
) -> MediaResult:
    """One clip of `seconds` seconds. `reference_image` is the thumbnail (PNG)."""
    if not 3 <= seconds <= 15:
        raise RuntimeError("A clip must be between 3 and 15 seconds long.")
    if settings.practice_mode:
        data = await asyncio.to_thread(_practice_clip, prompt, seconds)
        return MediaResult(data=data, units=float(seconds), unit_kind=UnitKind.video_seconds)
    if reference_image is None:
        ask: str | list = prompt
    else:
        ask = [
            {
                "type": "image",
                "data": base64.b64encode(reference_image).decode(),
                "mime_type": "image/png",
            },
            {"type": "text", "text": f"Use the reference image for the subject and style. {prompt}"},
        ]
    client = _client(config)
    try:
        interaction = await client.aio.interactions.create(
            model=settings.video_model,
            input=ask,
            response_format={
                "type": "video",
                "aspect_ratio": "9:16",
                "duration": f"{seconds}s",
                "resolution": resolution,
                "delivery": "uri",
            },
            timeout=float(TIMEOUT_SECONDS),
        )
        video = interaction.output_video
        if video is None or not video.uri:
            raise RuntimeError("The video service did not return a clip. Press Retry to try again.")
        # The provider has accepted the job, so the seconds are paid
        # for from here on — even if preparing or downloading the
        # file then fails.
        try:
            data = await _download_video(client, video.uri)
        except Exception as exc:  # noqa: BLE001 — re-raised as the paid outcome
            message = (
                str(exc)
                if isinstance(exc, RuntimeError) and str(exc)
                else "The finished clip could not be downloaded. Press Retry to try again."
            )
            raise PaidButNotDelivered(message) from exc
    finally:
        await client.aio.aclose()
    return MediaResult(data=data, units=float(seconds), unit_kind=UnitKind.video_seconds)


async def generate_thumbnail(prompt: str, *, settings: Settings, config: Config) -> MediaResult:
    """One vertical thumbnail picture (PNG bytes)."""
    if settings.practice_mode:
        data = await asyncio.to_thread(_practice_thumbnail, prompt)
        return MediaResult(data=data, units=1.0, unit_kind=UnitKind.images)
    client = _client(config)
    try:
        interaction = await client.aio.interactions.create(
            model=settings.image_model,
            input=prompt,
            # 1K is the size the price table charges per image; inline
            # base64 is the default — sending a delivery key is a 400.
            response_format={
                "type": "image",
                "aspect_ratio": "9:16",
                "image_size": "1K",
            },
            timeout=float(TIMEOUT_SECONDS),
        )
        image = interaction.output_image
        if image is None or not image.data:
            raise RuntimeError("The picture service did not return a thumbnail. Press Retry to try again.")
        raw = base64.b64decode(image.data)
    finally:
        await client.aio.aclose()
    data = await asyncio.to_thread(_to_png, raw)
    return MediaResult(data=data, units=1.0, unit_kind=UnitKind.images)
