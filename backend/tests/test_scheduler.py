"""S3 worker-loop steps: videos due by schedule, snapshots (L1), the analyst (L2).

Interface choices where docs/02-architecture.md is silent:
- Each step takes `now=` so a test can move the clock: `scheduler.create_due_videos(session, now=)`,
  `scheduler.take_due_snapshots(session, config, now=)`, `scheduler.run_due_analysis(session, config,
  now=)`. Sync or async, either is fine (`conftest.call`).
- `youtube.fetch_stats(config, youtube_id, *, with_analytics) -> dict` keyed by Snapshot field names
  (a plain sync function). `with_analytics=True` asks for the Analytics API fields too.
- A missed checkpoint is not back-filled: one snapshot, labelled with the latest checkpoint passed.
- `analyst.agent` returns `lessons_to_add: list[str]`, `lesson_ids_to_retire: list[int]`.
- "Once a day" is 24 hours since that recipe's last analysis, not a calendar day.
"""

from collections import Counter
from datetime import UTC, datetime, timedelta

import pytest
from sqlmodel import col, select

from app import scheduler, youtube
from app.models import CostEvent, Lesson, Pipeline, Snapshot, Video
from conftest import call
from fakes import fake_analyst
from test_engine import make_pipeline


def published(session, recipe: Pipeline, name: str, hours_ago: float, now: datetime,
              taken: tuple[int, ...] = ()) -> Video:
    """A published video `hours_ago` old with snapshots already taken at the `taken` checkpoints."""
    video = Video(pipeline_id=recipe.id, status="published", title=name, youtube_id=f"yt-{name}",
                  created_at=now - timedelta(hours=hours_ago + 2),
                  published_at=now - timedelta(hours=hours_ago))
    session.add(video)
    session.commit()
    session.refresh(video)
    for hours in taken:
        add_snapshot(session, video, hours)
    return video


def add_snapshot(session, video: Video, hours: int) -> None:
    session.add(Snapshot(video_id=video.id, checkpoint_hours=hours, views=10 * hours, likes=hours,
                         avg_view_percent=50.0 if hours >= 72 else None))
    session.commit()


def checkpoints(session, video: Video) -> list[int]:
    session.expire_all()
    return sorted(s.checkpoint_hours
                  for s in session.exec(select(Snapshot).where(Snapshot.video_id == video.id)))


def test_due_videos_follow_every_days_and_videos_per_run(session):
    now = datetime.now(UTC)
    every_two = make_pipeline(session, name="Every two days", every_days=2, videos_per_run=3,
                              last_run_at=now - timedelta(days=2, hours=1))
    never_run = make_pipeline(session, name="Never run", every_days=1, videos_per_run=1)
    not_yet = make_pipeline(session, name="Not yet", every_days=2, videos_per_run=1,
                            last_run_at=now - timedelta(hours=47))
    make_pipeline(session, name="Paused", active=False, last_run_at=now - timedelta(days=30))
    make_pipeline(session, name="Deleted", deleted_at=now - timedelta(days=1),
                  last_run_at=now - timedelta(days=30))

    def queued() -> Counter:
        session.expire_all()
        videos = session.exec(select(Video)).all()
        assert all(v.status == "queued" and not v.is_test for v in videos)
        return Counter(v.pipeline_id for v in videos)

    call(scheduler.create_due_videos, session, now=now)
    assert queued() == {every_two.id: 3, never_run.id: 1}  # a recipe that never ran is due at once

    call(scheduler.create_due_videos, session, now=now + timedelta(minutes=1))
    assert queued() == {every_two.id: 3, never_run.id: 1}  # nothing more until due again

    call(scheduler.create_due_videos, session, now=now + timedelta(days=2, minutes=1))
    assert queued() == {every_two.id: 6, never_run.id: 2, not_yet.id: 1}


@pytest.fixture
def stats(monkeypatch) -> list[tuple[str, bool]]:
    calls: list[tuple[str, bool]] = []

    def fetch_stats(config, youtube_id, *, with_analytics):
        calls.append((youtube_id, with_analytics))
        numbers = {"views": 1000, "likes": 50, "comments": 4}
        if with_analytics:
            numbers |= {"avg_view_seconds": 17.5, "avg_view_percent": 61.0, "shares": 3,
                        "subscribers_gained": 2}
        return numbers

    monkeypatch.setattr(youtube, "fetch_stats", fetch_stats)
    return calls


def test_snapshots_are_taken_exactly_at_the_due_checkpoints(session, config, stats):
    now = datetime.now(UTC)
    recipe = make_pipeline(session)
    too_soon = published(session, recipe, "too-soon", 0.5, now)
    first = published(session, recipe, "first", 1.5, now)
    done = published(session, recipe, "done", 7, now, taken=(1, 6))
    slept = published(session, recipe, "slept", 30, now, taken=(1,))  # laptop slept through 6 h
    mature = published(session, recipe, "mature", 80, now, taken=(1, 6, 24, 48))
    session.add(Video(pipeline_id=recipe.id, status="awaiting_approval", title="not published",
                      created_at=now - timedelta(hours=10)))
    session.commit()

    call(scheduler.take_due_snapshots, session, config, now=now)

    # Analytics API numbers only from 72 h on: before that they do not exist yet.
    assert sorted(stats) == [("yt-first", False), ("yt-mature", True), ("yt-slept", False)]
    assert [checkpoints(session, v) for v in (too_soon, first, done, slept, mature)] == [
        [], [1], [1, 6], [1, 24], [1, 6, 24, 48, 72]]
    new = {s.video_id: s for s in session.exec(select(Snapshot).order_by(col(Snapshot.id))).all()}
    assert (new[first.id].views, new[first.id].likes, new[first.id].avg_view_percent) == (1000, 50, None)
    assert (new[mature.id].views, new[mature.id].avg_view_percent, new[mature.id].shares) == (1000, 61.0, 3)

    call(scheduler.take_due_snapshots, session, config, now=now + timedelta(minutes=5))
    assert len(stats) == 3  # never twice for the same checkpoint


def lesson(session, recipe: Pipeline, text: str, source: str, at: datetime, active=True) -> Lesson:
    row = Lesson(pipeline_id=recipe.id, text=text, source=source, active=active, created_at=at)
    session.add(row)
    session.commit()
    session.refresh(row)
    return row


def test_analyst_runs_at_most_once_a_day_per_pipeline_and_keeps_ten_lessons(session, config):
    base = datetime.now(UTC)
    cats, dogs = make_pipeline(session, name="Cats"), make_pipeline(session, name="Dogs")
    cat_video = published(session, cats, "CATS-VIDEO", 200, base, taken=(72,))
    published(session, cats, "CATS-OTHER", 100, base, taken=(72,))
    dog_video = published(session, dogs, "DOGS-VIDEO", 100, base, taken=(24,))  # nothing mature yet
    yours = [lesson(session, cats, f"YOU-{i}", "you", base - timedelta(days=40 - i)) for i in range(3)]
    old = [lesson(session, cats, f"OLD-{i}", "analytics", base - timedelta(days=30 - i)) for i in range(6)]
    lesson(session, cats, "SWITCHED-OFF", "analytics", base - timedelta(days=20), active=False)
    dogs_own = lesson(session, dogs, "DOGS-LESSON", "you", base)
    fresh = [f"FRESH-{i}" for i in range(4)]
    # 9 active - 1 retired + 4 new = 12: over the cap of 10. The dogs id is not cats' to retire.
    first = {"lessons_to_add": fresh, "lesson_ids_to_retire": [old[0].id, dogs_own.id]}
    no_change = {"lessons_to_add": [], "lesson_ids_to_retire": []}
    t0 = datetime.now(UTC)

    with fake_analyst(first, no_change) as calls:
        call(scheduler.run_due_analysis, session, config, now=t0)
        assert len(calls) == 1  # dogs has no mature snapshot yet
        prompt = calls[0].prompt
        assert "CATS-VIDEO" in prompt and "DOGS-VIDEO" not in prompt
        assert all(row.text in prompt for row in yours + old)

        session.expire_all()
        cat_lessons = session.exec(select(Lesson).where(Lesson.pipeline_id == cats.id)).all()
        active = {row.text for row in cat_lessons if row.active}
        assert len(active) == 10
        # The analyst's new lessons win over the oldest of its own; yours are never trimmed.
        assert set(fresh) | {row.text for row in yours} <= active
        assert old[0].text not in active
        assert {row.source for row in cat_lessons if row.text in fresh} == {"analytics"}
        assert session.get(Lesson, dogs_own.id).active

        call(scheduler.run_due_analysis, session, config, now=t0 + timedelta(hours=1))
        assert len(calls) == 1  # nothing new

        add_snapshot(session, dog_video, 72)
        call(scheduler.run_due_analysis, session, config, now=t0 + timedelta(hours=2))
        assert len(calls) == 2 and "DOGS-VIDEO" in calls[1].prompt  # once a day is per recipe

        add_snapshot(session, cat_video, 168)
        call(scheduler.run_due_analysis, session, config, now=t0 + timedelta(hours=3))
        assert len(calls) == 2  # cats already had today's run

        call(scheduler.run_due_analysis, session, config, now=t0 + timedelta(hours=25))
        assert len(calls) == 3 and "CATS-VIDEO" in calls[2].prompt

        call(scheduler.run_due_analysis, session, config, now=t0 + timedelta(hours=50))
        assert len(calls) == 3  # a day has passed, but nothing new matured

    session.expire_all()
    events = session.exec(select(CostEvent).order_by(col(CostEvent.id))).all()
    assert [(e.stage, e.pipeline_id) for e in events] == [
        ("analytics", cats.id), ("analytics", dogs.id), ("analytics", cats.id)]


def test_one_failed_analysis_does_not_stop_other_recipes(session, config, monkeypatch):
    # Review S3 #6: a failing recipe is logged, waits a day, and the
    # rest of the loop still runs.
    from app.agents import analyst

    now = datetime.now(UTC)
    cats, dogs = make_pipeline(session, name="Cats"), make_pipeline(session, name="Dogs")
    published(session, cats, "CATS-VIDEO", 100, now, taken=(72,))
    published(session, dogs, "DOGS-VIDEO", 100, now, taken=(72,))
    attempted: list[str] = []

    async def analyse(_session, recipe, _config):
        attempted.append(recipe.name)
        if recipe.name == "Cats":
            raise RuntimeError("the model did not answer")
        return analyst.Analysis(lessons_to_add=["DOGS-LEARNED"], lesson_ids_to_retire=[])

    monkeypatch.setattr(analyst, "analyse_pipeline", analyse)

    call(scheduler.run_due_analysis, session, config, now=now)  # must not raise

    session.expire_all()
    assert attempted == ["Cats", "Dogs"]
    assert [row.text for row in session.exec(select(Lesson).where(Lesson.pipeline_id == dogs.id))] == [
        "DOGS-LEARNED"]
    assert session.get(Pipeline, cats.id).last_analysis_at is not None

    call(scheduler.run_due_analysis, session, config, now=now + timedelta(hours=1))
    assert attempted == ["Cats", "Dogs"]  # the failure waits a day, not a tick


def test_analysis_defers_when_the_monthly_budget_is_spent(session, config):
    # Review S3 #3: the analyst is a paid call; with no budget left it
    # is deferred (not stamped as attempted), so it runs once the
    # budget has room again.
    from app.db import get_settings

    now = datetime.now(UTC)
    cats = make_pipeline(session, name="Cats")
    published(session, cats, "CATS-VIDEO", 100, now, taken=(72,))
    settings = get_settings(session)
    settings.monthly_budget_usd = 0
    session.add(settings)
    session.commit()

    with fake_analyst({"lessons_to_add": ["X"], "lesson_ids_to_retire": []}) as calls:
        call(scheduler.run_due_analysis, session, config, now=now)

    assert calls == []
    session.expire_all()
    assert session.get(Pipeline, cats.id).last_analysis_at is None
    assert session.exec(select(Lesson)).all() == []
