import calendar
from datetime import UTC, date, datetime, timedelta

import pytest
from pytest import approx
from sqlmodel import select

from app import costs
from app.models import CostEvent, Pipeline, Snapshot, Video


def at(year, month, day, hour):
    # SQLModel stores aware datetimes as UTC; "day" and "month" in summaries are UTC days.
    return datetime(year, month, day, hour, tzinfo=UTC)


def make_pipeline(session, name="Cats"):
    p = Pipeline(name=name, niche="cats", objective="grow", audience="kids", region_notes="",
                 genre="funny", art_style="cartoon", target_seconds=30, every_days=1,
                 videos_per_run=1, approval_mode="manual", auto_approve_score=8,
                 visibility="private", extra_notes="", active=True)
    session.add(p)
    session.commit()
    session.refresh(p)
    return p


def make_video(session, pipeline, title="A video", status="awaiting_approval"):
    v = Video(pipeline_id=pipeline.id, status=status, title=title, is_test=False)
    if status == "published":
        v.youtube_id, v.published_at = f"yt-{title}", at(2026, 3, 1, 12)
    session.add(v)
    session.commit()
    session.refresh(v)
    return v


def spend(session, usd, *, when=None, stage="video", video=None):
    """Seed a cost event directly: these tests are about the maths, not the price table."""
    e = CostEvent(stage=stage, model="gemini-omni-1.2-flash", input_tokens=0, output_tokens=0,
                  units=0, unit_kind="video_seconds", cost_usd=usd, reason="test spend",
                  video_id=video.id if video else None,
                  pipeline_id=video.pipeline_id if video else None)
    if when:
        e.created_at = when
    session.add(e)
    session.commit()


def snapshot(session, video, hours, views, when):
    session.add(Snapshot(video_id=video.id, checkpoint_hours=hours, views=views, likes=0,
                         comments=0, created_at=when))
    session.commit()


def test_record_prices_each_call_and_survives_a_rollback(session):
    v = make_video(session, make_pipeline(session))
    plan = costs.record(session, stage="planning", model="gemini-4-hydrogen", reason="Planned 1 video",
                        input_tokens=10_000, output_tokens=2_000, video=v)
    review = costs.record(session, stage="review", model="gemini-4-argon", reason="Watched it once",
                          input_tokens=100_000, output_tokens=10_000, video=v)
    clip = costs.record(session, stage="video", model="gemini-omni-1.2-flash",
                        reason="1 clip × 10 s of video", units=10, unit_kind="video_seconds", video=v)
    ask = costs.record(session, stage="help", model="gemini-4-hydrogen", reason="Answered a question",
                       input_tokens=1_000_000)

    assert plan.cost_usd == approx(0.03)  # Hydrogen $1.50 / $7.50 per 1M
    assert review.cost_usd == approx(0.60)  # Argon at the post-2026-12-01 rate, $4 / $20 per 1M
    assert clip.cost_usd == approx(0.69504, rel=0.01)  # 720p: 5,792 tokens/s × $12 per 1M
    assert ask.cost_usd == approx(1.50)
    assert plan.reason == "Planned 1 video"
    assert (plan.video_id, plan.pipeline_id) == (v.id, v.pipeline_id)  # pipeline taken from the video
    assert (ask.video_id, ask.pipeline_id) == (None, None)

    session.rollback()  # a stage failing later must not lose what was already paid for
    assert len(session.exec(select(CostEvent)).all()) == 4


def test_summary_maths(session):
    cats, dogs = make_pipeline(session, "Cats"), make_pipeline(session, "Dogs")
    a = make_video(session, cats, "A", status="published")
    b = make_video(session, dogs, "B", status="published")
    c = make_video(session, cats, "C")
    spend(session, 100.0, video=a, when=at(2026, 2, 28, 12))  # before the range
    spend(session, 0.50, video=a, stage="planning", when=at(2026, 3, 1, 12))
    spend(session, 3.00, video=a, stage="video", when=at(2026, 3, 1, 13))
    spend(session, 0.50, video=a, stage="thumbnail", when=at(2026, 3, 3, 12))
    spend(session, 1.75, video=b, stage="video", when=at(2026, 3, 3, 12))
    spend(session, 0.25, video=b, stage="review", when=at(2026, 3, 3, 14))
    spend(session, 5.00, video=c, stage="video", when=at(2026, 3, 31, 12))  # end is inclusive
    spend(session, 0.10, stage="help", when=at(2026, 3, 31, 18))
    spend(session, 100.0, video=c, when=at(2026, 4, 1, 12))  # after the range
    snapshot(session, a, 24, 100, at(2026, 3, 2, 12))
    snapshot(session, a, 168, 400, at(2026, 3, 8, 12))  # latest views count, not the sum
    snapshot(session, b, 24, 600, at(2026, 3, 4, 12))

    # Doc is silent on the shape: a JSON-ready dict; start/end are dates, both inclusive.
    s = costs.summary(session, date(2026, 3, 1), date(2026, 3, 31))

    assert s["total_usd"] == approx(11.10)
    assert {k: v for k, v in s["by_stage"].items() if v} == approx(
        {"planning": 0.50, "video": 9.75, "thumbnail": 0.50, "review": 0.25, "help": 0.10})
    assert {r["pipeline_id"]: r["usd"] for r in s["by_pipeline"]} == approx(
        {cats.id: 9.00, dogs.id: 2.00, None: 0.10})
    assert {str(r["day"]): r["usd"] for r in s["by_day"]} == approx(
        {"2026-03-01": 3.50, "2026-03-03": 2.50, "2026-03-31": 5.10})
    assert {r["video_id"]: r["usd"] for r in s["by_video"]} == approx({a.id: 4.00, b.id: 2.00, c.id: 5.00})
    # Spend in range on published videos (A + B = $6) ÷ their latest views (400 + 600).
    assert s["cost_per_view"] == approx(0.006)


def test_cost_per_view_ignores_practice_uploads(session):
    # Practice charges stay in the totals, but a video that never aired
    # must not move cost per view.
    cats = make_pipeline(session)
    real = make_video(session, cats, "Real", status="published")
    practice = make_video(session, cats, "Practice", status="published")
    practice.youtube_id = "practice-abc"
    session.add(practice)
    session.commit()
    spend(session, 1.00, video=real, when=at(2026, 3, 2, 12))
    spend(session, 9.00, video=practice, when=at(2026, 3, 2, 12))
    snapshot(session, real, 24, 100, at(2026, 3, 3, 12))
    snapshot(session, practice, 24, 10_000, at(2026, 3, 3, 12))

    s = costs.summary(session, date(2026, 3, 1), date(2026, 3, 31))

    assert s["total_usd"] == approx(10.00)  # both charges are in the ledger totals
    assert s["cost_per_view"] == approx(0.01)  # $1 of real spend ÷ 100 real views


def test_month_to_date_and_projection_ignore_the_requested_range(session):
    v = make_video(session, make_pipeline(session))
    now = datetime.now(UTC)
    spend(session, 6.0, video=v, when=now)
    spend(session, 5.0, video=v, when=now)
    spend(session, 50.0, video=v, when=now - timedelta(days=45))  # an earlier month

    s = costs.summary(session, date(2020, 1, 1), date(2020, 1, 31))

    today = datetime.now(UTC).date()
    days_in_month = calendar.monthrange(today.year, today.month)[1]
    assert s["total_usd"] == 0
    assert s["cost_per_view"] is None  # no published video, no views
    assert s["month"]["spent_usd"] == approx(11.0)
    assert s["month"]["budget_usd"] == approx(30.0)  # default monthly budget
    # Straight-line projection: spend so far ÷ days elapsed (today included) × days in the month.
    assert s["month"]["projected_usd"] == approx(11.0 / today.day * days_in_month)


def test_budget_check_blocks_before_spending(session, client):
    cats = make_pipeline(session)
    spend(session, 500.0, video=make_video(session, cats), when=datetime.now(UTC) - timedelta(days=45))
    v = make_video(session, cats)
    costs.check_budget(session, v, upcoming_usd=2.0)  # defaults: $30 a month, $6 a video

    spend(session, 5.0, video=v)
    with pytest.raises(costs.BudgetExceeded) as err:
        costs.check_budget(session, v, upcoming_usd=2.0)  # $7 > $6 per-video cap
    assert str(err.value)  # a plain sentence for the video page
    costs.check_budget(session, v, upcoming_usd=1.0)  # reaching the cap exactly is allowed

    for _ in range(4):
        spend(session, 6.0, video=make_video(session, cats))  # $29 this month
    fresh = make_video(session, cats)
    costs.check_budget(session, fresh, upcoming_usd=1.0)
    with pytest.raises(costs.BudgetExceeded):
        costs.check_budget(session, fresh, upcoming_usd=1.5)  # $30.50 > $30 monthly budget

    settings = client.get("/api/settings").json()
    assert client.put("/api/settings", json={**settings, "monthly_budget_usd": 100}).status_code == 200
    session.expire_all()  # like the next stage starting with fresh state
    costs.check_budget(session, fresh, upcoming_usd=1.5)  # the budget is read from the database


def test_cost_routes(client, session):
    v = make_video(session, make_pipeline(session))
    costs.record(session, stage="planning", model="gemini-4-hydrogen", reason="Planned 1 video",
                 input_tokens=1_000_000, video=v)
    costs.record(session, stage="video", model="gemini-omni-1.2-flash", reason="1 clip × 10 s",
                 units=10, unit_kind="video_seconds", video=v)
    costs.record(session, stage="help", model="gemini-4-hydrogen", reason="Answered a question",
                 output_tokens=1_000_000)

    events = client.get("/api/costs/events", params={"video_id": v.id}).json()
    assert sorted(e["stage"] for e in events) == ["planning", "video"]
    assert all(e["reason"] and e["cost_usd"] > 0 for e in events)

    today = datetime.now(UTC).date()
    expected = approx(1.50 + 0.69504 + 7.50, rel=0.01)
    ranged = client.get("/api/costs/summary",
                        params={"start": today.replace(day=1).isoformat(), "end": today.isoformat()})
    assert ranged.json()["total_usd"] == expected
    assert client.get("/api/costs/summary").json()["total_usd"] == expected  # defaults to this month
