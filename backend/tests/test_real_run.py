"""S5: scripts/real_run.py — the one real, paid, private test upload — exercised only with fakes.

Interface choices where the spec is silent:
- The script defines `main(config: Config | None = None) -> int` (exit code; sync or async) and
  ends with `sys.exit(main())`. `None` means the real `Config()`; tests pass a temp-folder one.
  Nothing runs at import time (importing must not read `.env`).
- It reaches media, stitching and YouTube only through `app.media`, `app.stitch` and
  `app.youtube` module attributes (via `pipeline.advance`), so the fakes below replace them.
- "Ledger total" is every cost event ever recorded, not just this month's.
"""

import importlib.util
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlmodel import select

from app import media, stitch, youtube
from app.db import get_settings
from app.models import CostEvent, Pipeline, UnitKind, Video
from conftest import REPO, call
from fakes import PLAN, fake_text_agents

# A 20 s Short: two 10 s scenes.
TWO_SCENES = {**PLAN, "scenes": [
    {"prompt": "SCENE-ONE: a cat eyes a cardboard box.", "seconds": 10, "narration": "A box."},
    {"prompt": "SCENE-TWO: the cat leaps in and vanishes.", "seconds": 10, "narration": "Gone."},
]}
STATS = {"views": 4242, "likes": 17, "comments": 3, "avg_view_percent": 61.5}


@pytest.fixture
def real_run():
    spec = importlib.util.spec_from_file_location("real_run", REPO / "scripts" / "real_run.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def fakes(monkeypatch, config, session):
    """Paid media, stitching and YouTube replaced; a fake token file in the temp data folder."""
    config.youtube_token_path.write_text('{"token": "fake-test-token"}')
    spy = SimpleNamespace(clips=[], uploads=[], stats=[], fail_clips=False)

    async def clip(prompt, seconds, **kwargs):
        spy.clips.append(seconds)
        if spy.fail_clips:
            raise RuntimeError("The video service did not answer in time.")
        return media.MediaResult(data=b"fake-clip", units=float(seconds), unit_kind=UnitKind.video_seconds)

    async def thumbnail(prompt, **kwargs):
        return media.MediaResult(data=b"fake-png", units=1.0, unit_kind=UnitKind.images)

    def stitched(clip_paths, output_path):
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        Path(output_path).write_bytes(b"fake-final")

    def upload(config_, **kwargs):
        session.expire_all()  # what practice mode really was while uploading
        spy.uploads.append({**kwargs, "practice_mode_setting": get_settings(session).practice_mode})
        return f"yt-real-{len(spy.uploads)}"

    def fetch_stats(config_, youtube_id, *, with_analytics):
        spy.stats.append((youtube_id, with_analytics))
        return dict(STATS)

    monkeypatch.setattr(media, "generate_clip", clip)
    monkeypatch.setattr(media, "generate_thumbnail", thumbnail)
    monkeypatch.setattr(stitch, "stitch", stitched)
    monkeypatch.setattr(youtube, "upload", upload)
    monkeypatch.setattr(youtube, "set_thumbnail", lambda *args, **kwargs: None)
    monkeypatch.setattr(youtube, "fetch_stats", fetch_stats)
    monkeypatch.setattr(
        youtube, "status",
        lambda config_: {"connected": True, "channel_title": "Test channel",
                         "needs_reconnect": False},
    )
    return spy


def practice_mode(session) -> bool:
    session.expire_all()
    return get_settings(session).practice_mode


def test_one_private_upload_then_refuses_a_second_run(real_run, fakes, config, session, capsys):
    with fake_text_agents(plan=TWO_SCENES):
        assert call(real_run.main, config) == 0, capsys.readouterr()

    [up] = fakes.uploads
    assert (up["privacy"], up["practice"], up["practice_mode_setting"]) == ("private", False, False)
    assert practice_mode(session) is True  # switched back on before exiting
    assert fakes.clips == [10, 10]
    assert fakes.stats == [("yt-real-1", True)]
    assert "4242" in capsys.readouterr().out  # the statistics are printed

    [recipe] = session.exec(select(Pipeline)).all()
    assert (recipe.active, recipe.visibility, recipe.approval_mode, recipe.target_seconds) == (
        False, "private", "manual", 20)
    [video] = session.exec(select(Video)).all()
    assert (video.status, video.youtube_id, video.is_test) == ("published", "yt-real-1", True)
    # Every paid call is in the ledger at real prices (practice media would be $0).
    events = session.exec(select(CostEvent).where(CostEvent.video_id == video.id)).all()
    assert {e.stage for e in events} == {"planning", "thumbnail", "video", "review"}
    assert all(e.cost_usd > 0 for e in events)

    # A real video is already up: a second run refuses and spends nothing.
    with fake_text_agents(plan=TWO_SCENES) as calls:
        assert call(real_run.main, config) != 0
    out = capsys.readouterr()
    assert (out.out + out.err).strip(), "refusal must say why"
    assert (len(fakes.uploads), calls["planner"]) == (1, [])
    assert len(session.exec(select(Pipeline)).all()) == 1  # refused before a fresh recipe
    assert practice_mode(session) is True


@pytest.mark.parametrize("why", ["no YouTube token", "ledger would pass $10"])
def test_refuses_before_spending(real_run, fakes, config, session, capsys, why):
    if why == "no YouTube token":
        config.youtube_token_path.unlink()
    else:
        # $9 spent last month: with the run's ~$1.42 estimate the all-time ledger passes $10.
        session.add(CostEvent(stage="video", model="gemini-omni-1.2-flash", cost_usd=9.0,
                              unit_kind="video_seconds", reason="Earlier test clips",
                              created_at=datetime.now(UTC) - timedelta(days=40)))
        session.commit()

    with fake_text_agents(plan=TWO_SCENES) as calls:
        assert call(real_run.main, config) != 0
    out = capsys.readouterr()
    assert (out.out + out.err).strip(), "refusal must say why"
    if why == "no YouTube token":
        assert "youtube" in (out.out + out.err).lower()
    assert (calls["planner"], fakes.clips, fakes.uploads) == ([], [], [])
    session.expire_all()
    assert session.exec(select(Video)).all() == []
    assert len(session.exec(select(CostEvent)).all()) == (0 if why == "no YouTube token" else 1)
    assert practice_mode(session) is True


def test_refuses_when_the_youtube_sign_in_is_not_usable(
    real_run, fakes, config, session, capsys, monkeypatch
):
    # Review steer: a live status check before spending, not just the token file.
    monkeypatch.setattr(
        youtube, "status",
        lambda config_: {"connected": False, "channel_title": None, "needs_reconnect": True},
    )
    with fake_text_agents(plan=TWO_SCENES) as calls:
        assert call(real_run.main, config) != 0
    out = capsys.readouterr()
    assert "youtube" in (out.out + out.err).lower()
    assert (calls["planner"], fakes.clips, fakes.uploads) == ([], [], [])
    assert session.exec(select(Video)).all() == []
    assert practice_mode(session) is True


def test_refuses_while_another_video_is_in_flight(real_run, fakes, config, session, capsys):
    from test_engine import make_pipeline

    recipe = make_pipeline(session)
    session.add(Video(pipeline_id=recipe.id, status="queued"))
    session.commit()
    with fake_text_agents(plan=TWO_SCENES) as calls:
        assert call(real_run.main, config) != 0
    out = capsys.readouterr()
    assert (out.out + out.err).strip(), "refusal must say why"
    assert (calls["planner"], fakes.uploads) == ([], [])
    assert len(session.exec(select(Video)).all()) == 1  # only the seeded video
    assert practice_mode(session) is True


def test_refuses_after_an_uncertain_upload_attempt(real_run, fakes, config, session, capsys):
    # Failed out of publish: YouTube may have the video although no id was saved.
    from test_engine import make_pipeline

    recipe = make_pipeline(session)
    session.add(Video(pipeline_id=recipe.id, status="failed", failed_status="approved"))
    session.commit()
    with fake_text_agents(plan=TWO_SCENES) as calls:
        assert call(real_run.main, config) != 0
    out = capsys.readouterr()
    assert (out.out + out.err).strip(), "refusal must say why"
    assert (calls["planner"], fakes.uploads) == ([], [])
    assert len(session.exec(select(Video)).all()) == 1
    assert practice_mode(session) is True


def test_refuses_while_the_app_is_running(real_run, fakes, config, session, capsys):
    import socket

    listener = None
    try:
        listener = socket.socket()
        listener.bind(("127.0.0.1", 8484))
        listener.listen(1)
    except OSError:
        listener = None  # something already answers there; same refusal applies
    try:
        with fake_text_agents(plan=TWO_SCENES) as calls:
            assert call(real_run.main, config) != 0
    finally:
        if listener is not None:
            listener.close()
    out = capsys.readouterr()
    assert (out.out + out.err).strip(), "refusal must say why"
    assert (calls["planner"], fakes.uploads) == ([], [])
    assert session.exec(select(Video)).all() == []
    assert practice_mode(session) is True


def test_a_failed_video_stops_the_run_without_retrying(real_run, fakes, config, session, capsys):
    fakes.fail_clips = True

    with fake_text_agents(plan=TWO_SCENES) as calls:
        assert call(real_run.main, config) != 0

    [video] = session.exec(select(Video)).all()
    assert (video.status, video.failed_status) == ("failed", "generating")
    assert (len(calls["planner"]), fakes.clips, fakes.uploads) == (1, [10], [])  # no retry
    out = capsys.readouterr()
    assert (out.out + out.err).strip(), "a failed run must say why"
    assert practice_mode(session) is True
