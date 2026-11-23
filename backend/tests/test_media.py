"""Real media branches against a fake google-genai client (offline, no money).

Only the request/response handling is under test: the thumbnail is
normalized to PNG, video has the one uri delivery path, and the key
check tells a rejection apart from no answer at all.
"""

import asyncio
import base64
import subprocess
from types import SimpleNamespace

import pytest

from app import media
from app.config import Config
from app.models import Settings


def _config(tmp_path, key="test-key") -> Config:
    return Config(_env_file=None, gemini_api_key=key, data_dir=tmp_path)


def _image(tmp_path, suffix: str) -> bytes:
    out = tmp_path / f"still{suffix}"
    subprocess.run(
        ["ffmpeg", "-v", "error", "-y", "-f", "lavfi",
         "-i", "color=c=red:s=16x16:d=0.04", "-frames:v", "1", str(out)],
        check=True,
    )
    return out.read_bytes()


class _Rejected(Exception):
    code = 403  # like google.genai.errors.APIError for a bad key


def _install(
    monkeypatch, *, image_data=b"", video=None, models_exc=None,
    file_state="ACTIVE", download_data=b"clip-bytes",
) -> dict:
    seen: dict = {}

    class Interactions:
        async def create(self, **kwargs):
            seen["create"] = kwargs
            return SimpleNamespace(
                output_image=SimpleNamespace(
                    data=base64.b64encode(image_data).decode(), uri=None
                ),
                output_video=video,
            )

    class Models:
        def get(self, *, model):
            seen["model"] = model
            if models_exc is not None:
                raise models_exc
            return object()

    class Files:
        async def get(self, *, name):
            return SimpleNamespace(state=SimpleNamespace(name=file_state))

        async def download(self, *, file):
            return download_data

    class Aio:
        def __init__(self):
            self.interactions = Interactions()
            self.files = Files()

        async def aclose(self):
            pass

    class Client:
        def __init__(self, **kwargs):
            seen["client_kw"] = kwargs
            self.aio = Aio()
            self.models = Models()

        def close(self):
            pass

    monkeypatch.setattr(media.genai, "Client", Client)
    return seen


def test_thumbnail_jpeg_becomes_png(tmp_path, monkeypatch):
    seen = _install(monkeypatch, image_data=_image(tmp_path, ".jpg"))
    out = asyncio.run(
        media.generate_thumbnail(
            "p", settings=Settings(practice_mode=False), config=_config(tmp_path)
        )
    )
    assert out.data.startswith(b"\x89PNG")
    assert "delivery" not in seen["create"]["response_format"]  # 400 if sent; inline is default


def test_thumbnail_png_passes_through_unchanged(tmp_path, monkeypatch):
    png = _image(tmp_path, ".png")
    _install(monkeypatch, image_data=png)
    out = asyncio.run(
        media.generate_thumbnail(
            "p", settings=Settings(practice_mode=False), config=_config(tmp_path)
        )
    )
    assert out.data == png  # already PNG: no conversion


def test_clip_downloads_through_the_files_api(tmp_path, monkeypatch):
    _install(monkeypatch, video=SimpleNamespace(uri="files/abc", data=None))
    out = asyncio.run(
        media.generate_clip(
            "p", 3, resolution="1080p", settings=Settings(practice_mode=False),
                config=_config(tmp_path),
        )
    )
    assert (out.data, out.units) == (b"clip-bytes", 3.0)


def test_clip_that_fails_preparation_is_paid_but_not_delivered(tmp_path, monkeypatch):
    # The provider accepted the job, so the seconds are charged even
    # though no file arrives; the distinct type lets the pipeline
    # record the cost before failing.
    _install(
        monkeypatch, video=SimpleNamespace(uri="files/abc", data=None), file_state="FAILED"
    )
    with pytest.raises(media.PaidButNotDelivered, match="could not finish"):
        asyncio.run(
            media.generate_clip(
                "p", 3, resolution="1080p", settings=Settings(practice_mode=False),
                config=_config(tmp_path),
            )
        )


def test_clip_without_a_uri_is_an_error(tmp_path, monkeypatch):
    inline_only = SimpleNamespace(uri=None, data=base64.b64encode(b"x").decode())
    _install(monkeypatch, video=inline_only)
    with pytest.raises(RuntimeError, match="did not return a clip"):
        asyncio.run(
            media.generate_clip(
                "p", 3, resolution="1080p", settings=Settings(practice_mode=False),
                config=_config(tmp_path),
            )
        )


def test_check_key_outcomes(tmp_path, monkeypatch):
    seen = _install(monkeypatch)
    assert media.check_key(_config(tmp_path)) is True
    assert seen["model"] == "gemini-4-hydrogen"
    assert seen["client_kw"]["http_options"].timeout == 5000  # never blocks the page

    _install(monkeypatch, models_exc=_Rejected("bad key"))
    assert media.check_key(_config(tmp_path)) is False  # Google answered: no

    _install(monkeypatch, models_exc=RuntimeError("offline"))
    assert media.check_key(_config(tmp_path)) is None  # no answer: could not check

    assert media.check_key(_config(tmp_path, key="")) is False
