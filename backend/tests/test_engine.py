"""S2 engine: plan → generate → review → approval, in practice mode with scripted text agents.

Interface choices where docs/02-architecture.md is silent:
- `await pipeline.advance(session, video, config)` runs one stage, saves, and never raises
  (a failing stage leaves the video `failed`).
- The pipeline calls `media.generate_clip` / `media.generate_thumbnail` through the module,
  so a test can wrap them.
- Clip.index is 0-based (keys look like `clip_0.mp4`); the reviewer's bad_clips use it.
"""

import asyncio
import json
import re
import subprocess
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from pytest import approx
from sqlmodel import select

from app import media, pipeline
from app.db import get_settings
from app.models import Clip, CostEvent, Lesson, Pipeline, UnitKind, Video
from fakes import BETTER_PROMPT, GOOD_REVIEW, PLAN, fake_text_agents, flag_clip
from test_api import PIPELINE

# The stages the worker loop keeps advancing. `approved` (publish) is S3's, so it rests here.
WORKING = {"queued", "generating", "reviewing"}
PLAN_SECONDS = sum(s["seconds"] for s in PLAN["scenes"])


def make_pipeline(session, **fields) -> Pipeline:
    p = Pipeline.model_validate({**PIPELINE, **fields})
    session.add(p)
    session.commit()
    session.refresh(p)
    return p


def queue_video(session, p: Pipeline) -> Video:
    v = Video(pipeline_id=p.id, status="queued")
    session.add(v)
    session.commit()
    session.refresh(v)
    return v


def advance_until_rest(session, video: Video, config) -> Video:
    for _ in range(10):
        session.refresh(video)
        if video.status not in WORKING:
            return video
        asyncio.run(pipeline.advance(session, video, config))
    raise AssertionError(f"Video never came to rest; stuck in {video.status}")


def events_for(session, video: Video) -> list[CostEvent]:
    session.expire_all()
    return list(session.exec(select(CostEvent).where(CostEvent.video_id == video.id)).all())


def scene(prompt: str) -> str:
    return re.search(r"SCENE-[A-Z]+", prompt).group()


def probe(path) -> dict:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
         "stream=width,height:format=duration", "-of", "json", str(path)],
        capture_output=True, text=True, check=True).stdout
    data = json.loads(out)
    return {**data["streams"][0], "duration": float(data["format"]["duration"])}


@pytest.fixture
def media_calls(monkeypatch):
    """Counts media calls (practice versions still run). Prompt fragments in `fail` fail once."""
    spy = SimpleNamespace(clips=[], thumbnails=0, fail=set())
    real_clip, real_thumbnail = media.generate_clip, media.generate_thumbnail

    async def clip(*args, **kwargs):
        prompt = args[0] if args else kwargs["prompt"]
        spy.clips.append(prompt)
        for marker in [m for m in spy.fail if m in prompt]:
            spy.fail.discard(marker)
            raise RuntimeError("The video service did not answer in time.")
        return await real_clip(*args, **kwargs)

    async def thumbnail(*args, **kwargs):
        spy.thumbnails += 1
        return await real_thumbnail(*args, **kwargs)

    monkeypatch.setattr(media, "generate_clip", clip)
    monkeypatch.setattr(media, "generate_thumbnail", thumbnail)
    return spy


def test_practice_run_reaches_approval_and_records_every_paid_step(client, session, config, tmp_path):
    pid = client.post("/api/pipelines", json=PIPELINE).json()["id"]  # manual approval
    [queued] = client.post(f"/api/pipelines/{pid}/run", json={"count": 1}).json()
    video = session.get(Video, queued["id"])

    with fake_text_agents() as calls:
        advance_until_rest(session, video, config)

    assert video.status == "awaiting_approval", video.error  # a 9/10 still waits: manual recipe
    assert (len(calls["planner"]), len(calls["reviewer"])) == (1, 1)
    # Doc is silent on the shape: the video's own fields plus clips, cost_events, snapshots.
    page = client.get(f"/api/videos/{video.id}").json()
    assert (page["status"], page["title"], page["review_rounds"]) == (
        "awaiting_approval", PLAN["title"], 0)
    assert page["plan"]["hook"] == PLAN["hook"]
    assert page["review"]["score"] == GOOD_REVIEW["score"]
    assert [(c["index"], c["seconds"]) for c in page["clips"]] == [(0, 3), (1, 3), (2, 3)]
    for clip in page["clips"]:
        assert client.get(f"/api/media/{clip['storage_key']}").status_code == 200

    final = client.get(f"/api/media/videos/{video.id}/final.mp4")
    assert final.status_code == 200
    (tmp_path / "final.mp4").write_bytes(final.content)
    info = probe(tmp_path / "final.mp4")
    assert (info["width"], info["height"]) == (1080, 1920)
    assert info["duration"] == approx(PLAN_SECONDS, abs=0.5)
    assert client.get(f"/api/media/videos/{video.id}/thumb.png").status_code == 200
    assert client.get("/api/media/..%2Fapp.db").status_code in (400, 404)  # outside media/

    # C1 / V5: every paid step is in the ledger; practice media is recorded at $0,
    # the text agents are real calls priced as the models in Settings.
    events = page["cost_events"]
    assert {e["stage"] for e in events} == {"planning", "thumbnail", "video", "review"}
    assert all(e["reason"] and e["pipeline_id"] == pid for e in events)
    for e in events:
        if e["stage"] in ("video", "thumbnail"):
            assert e["cost_usd"] == 0, e
        else:
            assert e["cost_usd"] > 0 and e["input_tokens"] > 0, e
    assert {e["model"] for e in events if e["stage"] == "planning"} == {"gemini-4-hydrogen"}
    assert {e["model"] for e in events if e["stage"] == "review"} == {"gemini-4-argon"}
    assert sum(e["units"] for e in events if e["stage"] == "video") == PLAN_SECONDS


def test_planner_sees_only_the_brief_ten_lessons_and_fifteen_titles(session, config):
    cats = make_pipeline(session, niche="NICHE-cats", objective="OBJECTIVE-grow",
                         audience="AUDIENCE-kids", genre="GENRE-funny", art_style="STYLE-cartoon",
                         region_notes="REGION-uk", extra_notes="NOTES-no-dogs")
    dogs = make_pipeline(session, name="Dogs", niche="NICHE-dogs")
    start = datetime(2026, 1, 1, tzinfo=UTC)
    for i in range(1, 21):
        session.add(Video(pipeline_id=cats.id, status="published", title=f"CATS-TITLE-{i:02}",
                          created_at=start + timedelta(days=i)))
    session.add(Video(pipeline_id=dogs.id, status="published", title="DOGS-TITLE"))
    # The four you-lessons are the oldest: "newest ten" alone would drop two of them.
    lessons = [(f"LESSON-YOU-{i}", "you", True, cats) for i in range(1, 5)]
    lessons += [(f"LESSON-DATA-{i}", "analytics", True, cats) for i in range(1, 9)]
    lessons += [("LESSON-OFF", "you", False, cats), ("LESSON-DOGS", "you", True, dogs)]
    for n, (text, source, active, p) in enumerate(lessons):
        session.add(Lesson(pipeline_id=p.id, text=text, source=source, active=active,
                           created_at=start + timedelta(days=n)))
    session.commit()
    video = queue_video(session, cats)

    with fake_text_agents() as calls:
        asyncio.run(pipeline.advance(session, video, config))

    prompt = calls["planner"][0].prompt
    for value in ("NICHE-cats", "OBJECTIVE-grow", "AUDIENCE-kids", "GENRE-funny", "STYLE-cartoon",
                  "REGION-uk", "NOTES-no-dogs"):
        assert value in prompt
    shown = set(re.findall(r"LESSON-[A-Z]+-\d", prompt))
    assert len(shown) == 10
    assert {f"LESSON-YOU-{i}" for i in range(1, 5)} <= shown  # you-sourced first
    assert set(re.findall(r"CATS-TITLE-\d\d", prompt)) == {f"CATS-TITLE-{i:02}" for i in range(6, 21)}
    for other in ("LESSON-OFF", "LESSON-DOGS", "NICHE-dogs", "DOGS-TITLE"):
        assert other not in prompt


def test_reviewer_flags_clip_2_only_clip_2_is_remade_once(session, config, media_calls):
    video = queue_video(session, make_pipeline(session))

    with fake_text_agents(reviews=(flag_clip(2),)) as calls:  # flags clip 2 on every look
        advance_until_rest(session, video, config)

    assert video.status == "awaiting_approval", video.error
    assert video.review_rounds == 1
    assert len(calls["reviewer"]) == 2  # first look, then one final check, no third round
    assert [scene(p) for p in media_calls.clips] == ["SCENE-ONE", "SCENE-TWO", "SCENE-THREE",
                                                     "SCENE-THREE"]
    assert BETTER_PROMPT in media_calls.clips[-1]  # remade with the reviewer's better prompt
    assert all(PLAN["style_bible"] in p for p in media_calls.clips)
    # Each clip request also carries its planned narration; the remake keeps its line.
    assert all(PLAN["scenes"][i]["narration"] in p for i, p in enumerate(media_calls.clips[:3]))
    assert PLAN["scenes"][2]["narration"] in media_calls.clips[-1]
    assert media_calls.thumbnails == 1
    video_seconds = sum(e.units for e in events_for(session, video) if e.stage == "video")
    assert video_seconds == PLAN_SECONDS + 3


def test_failure_then_retry_keeps_what_was_already_made(client, session, config, media_calls):
    video = queue_video(session, make_pipeline(session))
    media_calls.fail.add("SCENE-TWO")

    with fake_text_agents() as calls:
        advance_until_rest(session, video, config)
        assert (video.status, video.failed_status) == ("failed", "generating")
        assert video.error  # a plain sentence for the video page

        retried = client.post(f"/api/videos/{video.id}/retry")
        assert retried.status_code == 200, retried.text
        assert retried.json()["status"] == "generating"
        advance_until_rest(session, video, config)

    assert video.status == "awaiting_approval", video.error
    made = [scene(p) for p in media_calls.clips]
    assert (made.count("SCENE-ONE"), made.count("SCENE-TWO"), made.count("SCENE-THREE")) == (1, 2, 1)
    assert media_calls.thumbnails == 1
    assert len(calls["planner"]) == 1
    # Clip one was paid for before the failure, so it must be in the ledger exactly once.
    assert sum(e.units for e in events_for(session, video) if e.stage == "video") == PLAN_SECONDS


def test_over_the_monthly_budget_fails_before_planning(session, config):
    cats = make_pipeline(session)
    session.add(CostEvent(stage="video", model="gemini-omni-1.2-flash", cost_usd=31.0,
                          unit_kind="video_seconds", reason="Earlier videos", pipeline_id=cats.id))
    session.commit()  # $31 of the default $30 budget is gone
    video = queue_video(session, cats)

    with fake_text_agents() as calls:
        advance_until_rest(session, video, config)

    assert (video.status, video.failed_status) == ("failed", "queued")
    assert "nothing was spent" in video.error  # costs.BudgetExceeded's message
    assert calls["planner"] == []
    assert events_for(session, video) == []


def test_planning_reserves_the_whole_video(session, config):
    # The recipe targets 30 s (~$2.09 of video + a thumbnail). A $1 cap can
    # never hold the finished video, so planning must not spend even cents.
    # Practice is off here: in practice the media is free and only the
    # text call is reserved (next test).
    settings = get_settings(session)
    settings.practice_mode = False
    settings.per_video_cap_usd = 1.0
    session.add(settings)
    session.commit()
    video = queue_video(session, make_pipeline(session))

    with fake_text_agents() as calls:
        advance_until_rest(session, video, config)

    assert (video.status, video.failed_status) == ("failed", "queued")
    assert "nothing was spent" in video.error
    assert calls["planner"] == []
    assert events_for(session, video) == []


def test_practice_planning_reserves_no_media_cost(session, config):
    # Same $1 cap and 30 s recipe, but practice media is free: only the
    # text reserve counts, so planning goes ahead.
    settings = get_settings(session)
    settings.per_video_cap_usd = 1.0  # practice_mode defaults to on
    session.add(settings)
    session.commit()
    video = queue_video(session, make_pipeline(session))

    with fake_text_agents() as calls:
        asyncio.run(pipeline.advance(session, video, config))

    session.refresh(video)
    assert video.status == "generating", video.error
    assert len(calls["planner"]) == 1
    assert {e.stage for e in events_for(session, video)} == {"planning"}


def test_paid_but_not_delivered_clip_is_still_recorded(session, config, monkeypatch):
    video = queue_video(session, make_pipeline(session))
    with fake_text_agents():
        asyncio.run(pipeline.advance(session, video, config))  # planned in practice
    settings = get_settings(session)
    settings.practice_mode = False
    session.add(settings)
    session.commit()

    async def thumbnail(*args, **kwargs):
        return media.MediaResult(data=b"fake-png", units=1.0, unit_kind=UnitKind.images)

    async def clip(*args, **kwargs):
        raise media.PaidButNotDelivered(
            "The video service could not finish this clip. Press Retry to try again."
        )

    monkeypatch.setattr(media, "generate_thumbnail", thumbnail)
    monkeypatch.setattr(media, "generate_clip", clip)

    with fake_text_agents():
        asyncio.run(pipeline.advance(session, video, config))

    session.refresh(video)
    assert (video.status, video.failed_status) == ("failed", "generating")
    [charge] = [e for e in events_for(session, video) if e.stage == "video"]
    assert charge.units == 3 and charge.cost_usd > 0  # first clip's 3 s, at real prices
    assert "never arrived" in charge.reason
    assert all(
        c.storage_key is None
        for c in session.exec(select(Clip).where(Clip.video_id == video.id)).all()
    )


def test_over_the_per_video_cap_fails_before_generating(session, config, media_calls, monkeypatch):
    video = queue_video(session, make_pipeline(session))
    with fake_text_agents():
        asyncio.run(pipeline.advance(session, video, config))  # planned: 3 clips × 3 s
    settings = get_settings(session)
    settings.practice_mode = False  # real prices: 9 s × ~$0.07 ≈ $0.63 of video
    settings.per_video_cap_usd = 0.50
    session.add(settings)
    session.commit()

    # Practice is off from here: a regressed budget check must hit these
    # stubs, never the real (paid, network) media calls behind the spies.
    async def forbidden(*args, **kwargs):
        raise AssertionError("Media must not be generated when the video is over its cap.")

    monkeypatch.setattr(media, "generate_clip", forbidden)
    monkeypatch.setattr(media, "generate_thumbnail", forbidden)

    with fake_text_agents():
        advance_until_rest(session, video, config)

    assert (video.status, video.failed_status) == ("failed", "generating")
    assert "nothing was spent" in video.error
    assert (media_calls.clips, media_calls.thumbnails) == ([], 0)
    assert {e.stage for e in events_for(session, video)} == {"planning"}


@pytest.mark.parametrize(("score", "status"), [(9, "approved"), (7, "awaiting_approval")])
def test_auto_approve_above_the_score(session, config, score, status):
    video = queue_video(session, make_pipeline(session, approval_mode="auto", auto_approve_score=8))

    with fake_text_agents(reviews=({**GOOD_REVIEW, "score": score},)):
        advance_until_rest(session, video, config)

    assert video.status == status, video.error
