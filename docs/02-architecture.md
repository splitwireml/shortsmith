# Architecture

One Python process: FastAPI serves the JSON API, the built SvelteKit app, and runs one
background worker loop. SQLite for data, a local folder for media. Nothing else to install
or run. Requirement IDs (P1, V2, C3…) refer to `docs/01-product.md`.

## Stack

| Concern | Choice | Why |
|---|---|---|
| Language / tooling | Python 3.13, `uv` | Pin 3.13 in `pyproject.toml` (3.14 wheels are not universal yet). |
| API | FastAPI + uvicorn | — |
| Data | SQLite through SQLModel | Table classes double as API schemas. `create_all` at start-up, no migrations. |
| Text agents | **Pydantic AI** | Planner, reviewer, analyst, helper. Typed outputs, built-in usage numbers, offline test models. |
| Video + image generation | **google-genai**, only inside `media.py` | Pydantic AI does not generate video. One file owns the SDK. |
| Stitching | `ffmpeg` via `subprocess` | Already on the machine. |
| YouTube | `google-api-python-client`, `google-auth-oauthlib`, only inside `youtube.py` | — |
| Background work | One `asyncio` task started in FastAPI's lifespan | No Celery, no APScheduler. State lives in the database, so a laptop that sleeps simply resumes. |
| Frontend | SvelteKit (Svelte 5 runes, TypeScript), `adapter-static` SPA, plain CSS | No UI kit, no chart library — bars are CSS. |

The rule on SDKs: `agents/` is the only place that imports `pydantic_ai`; `media.py` the only
place that imports `google.genai`; `youtube.py` the only place that imports Google API
clients. Everything else is plain Python and is testable without a network.

## Layout

```
backend/
  pyproject.toml
  app/
    main.py            FastAPI app, lifespan starts the worker loop, mounts API + built frontend
    config.py          Paths and secrets from the repo-root .env (pydantic-settings)
    db.py              Engine, session dependency, create_all
    models.py          SQLModel tables and the status / stage enums
    presets.py         The recipe presets (plain dicts)
    storage.py         Local media store with S3-style keys
    costs.py           Price table, record(), check_budget(), summary()
    media.py           generate_clip(), generate_thumbnail() — real and practice versions
    stitch.py          ffmpeg: join clips into one 1080×1920 MP4
    youtube.py         connect(), status(), upload(), fetch_stats()
    pipeline.py        One function per stage + advance(video)
    scheduler.py       The worker loop: what is due, do it
    retention.py       Clean-up by age and by size
    help_articles.json Help content (served to the UI, and the grounding for "ask")
    agents/
      base.py          build_model(role), run_agent() — the one path that records cost
      planner.py  reviewer.py  analyst.py  helper.py
    api/
      pipelines.py videos.py media.py costs.py insights.py settings.py status.py youtube.py help.py
  tests/
frontend/              SvelteKit app (see "Frontend")
data/                  Created at runtime, git-ignored: app.db, media/, youtube_token.json
start.command          Double-click launcher for macOS
```

## Data model

All tables have `id` (int, primary key) and `created_at`.

- **Settings** (exactly one row): `monthly_budget_usd=30`, `per_video_cap_usd=6`,
  `retention_days=14`, `max_storage_gb=5`, `practice_mode=True`, `onboarding_done=False`,
  and per role a model and effort: `planner_model/effort`, `reviewer_model/effort`,
  `analyst_model/effort`, `helper_model/effort`, `video_model`, `video_resolution="720p"`,
  `image_model` (defaults below).
- **Pipeline**: `name, niche, objective, audience, region_notes, genre, art_style,
  target_seconds, every_days, videos_per_run, approval_mode (manual|auto),
  auto_approve_score=8, visibility (private|unlisted|public), extra_notes, active,
  last_run_at`.
- **Video**: `pipeline_id, status, is_test, title, plan (JSON), review (JSON),
  review_rounds, error, failed_status, youtube_id, published_at, rating (-1|0|1),
  media_deleted_at`.
- **Clip**: `video_id, index, prompt, seconds, storage_key (null until generated)`.
  To regenerate a clip, set `storage_key` to null; "generate" only makes clips without one.
  That single rule gives both V3 and V4.
- **Lesson**: `pipeline_id, video_id (optional origin), text, source (analytics|you), active`.
- **CostEvent**: `pipeline_id?, video_id?, stage, model, input_tokens, output_tokens,
  units, unit_kind (tokens|video_seconds|images), cost_usd, reason`.
  Stages: `planning, video, thumbnail, review, analytics, help`.
- **Snapshot**: `video_id, checkpoint_hours, views, likes, comments, avg_view_seconds?,
  avg_view_percent?, shares?, subscribers_gained?`.

### Default models

| Role | Model id | Effort |
|---|---|---|
| planner | `gemini-4-hydrogen` | high |
| reviewer | `gemini-4-argon` | high |
| analyst | `gemini-4-hydrogen` | medium |
| helper (help "ask", recipe suggestion) | `gemini-4-hydrogen` | low |
| video | `gemini-omni-1.2-flash` (720p, 9:16) | — |
| thumbnail | `gemini-nano-banana-2.1` (the current Nano Banana 2 line; half the price of 2.0). `gemini-3-pro-image` = Nano Banana Pro, selectable in Advanced settings | — |

All six ids were confirmed on the owner's API key with a free metadata call. Exact call shapes, effort
parameter names, prices and limits are in `docs/research.md` — that file wins over anyone's
memory, including this document.

## The video state machine (`pipeline.py`)

`status` names the work that is due. `advance(video)` looks up the stage function for the
current status, runs it, and saves. The stage function returns the next status.

| Status | Stage function | Next |
|---|---|---|
| `queued` | `plan` — planner agent → `Video.plan`, `title`, one `Clip` row per scene | `generating` |
| `generating` | `generate` — every clip without a `storage_key`, thumbnail if missing, then stitch | `reviewing` |
| `reviewing` | `review` — reviewer agent watches `final.mp4` | `generating` if clips were flagged and `review_rounds < 1`; else `approved` if the pipeline auto-approves and the score is high enough; else `awaiting_approval` |
| `awaiting_approval` | — waits for the human | `approved` / `rejected` |
| `approved` | `publish` — set `publishing`, commit, upload, store `youtube_id` | `published` |

Terminal or resting: `published`, `rejected`, `failed`, `archived`.

- Any exception in a stage → `status=failed`, `failed_status=<where it was>`, `error=<plain
  sentence>`. Retry sets `status` back to `failed_status`.
- A video found in `publishing` when the app starts was interrupted mid-upload → `failed`
  with "The upload was interrupted. Check your YouTube channel; if the video is not there,
  press Retry." (Y2). `# ponytail:` we do not query YouTube to auto-resolve this.
- Before `plan`, `generate` and `review`: `costs.check_budget(video, upcoming_usd)` (C3).
  For `generate`, `upcoming_usd` = missing clip seconds × the video price.

## The worker loop (`scheduler.py`)

One task, one video at a time (`# ponytail:` sequential; parallelise clips if speed matters).

```
every 30 s:
    create_due_videos()     # active pipeline and now ≥ last_run_at + every_days → queue videos_per_run
    while a video is in queued | generating | reviewing | approved:  advance(oldest)
    take_due_snapshots()    # published videos whose next checkpoint has passed
    run_due_analysis()      # per pipeline, at most once a day, only if new mature snapshots
    retention.clean()       # at most once a day
```

Blocking work (ffmpeg, Google API client) runs in `asyncio.to_thread`. "Make a video now"
just inserts a `queued` row; the loop picks it up.

Snapshot checkpoints, hours after publish: `1, 6, 24, 48, 72, 168, 672` (research §6).
Views / likes / comments come from the Data API at every checkpoint. Average view duration,
average % viewed, shares and subscribers gained come from the Analytics API and are only
requested from the 72 h checkpoint on — that API lags 48–72 h and is daily. "Mature" for the
analyst means a snapshot at 72 h or later.

## Agents and context discipline

Every agent is one file: an output model, a short instruction string, and one async function.
All of them go through `agents.base.run_agent(agent, prompt, *, stage, session, video=None,
pipeline=None)`, which runs the agent and writes the CostEvent from the run's usage numbers.
No agent has tools, memory or multi-turn history. Each is a single call with a small,
purpose-built prompt:

| Agent | Sees | Returns |
|---|---|---|
| planner | The pipeline brief rendered as ~15 lines · up to 10 active lessons (you-sourced first) · the last 15 titles · allowed clip durations | `VideoPlan`: `title, hook, description, tags, style_bible, thumbnail_prompt, scenes[{prompt, seconds, narration}]` |
| reviewer | The stitched video · the plan's title, hook and scene list with timestamps | `Review`: `score (1–10), summary, bad_clips[{index, problem, better_prompt}]` |
| analyst | A compact table of the pipeline's last ≤20 published videos (title, hook, seconds, views, likes, avg % viewed, your rating) · current lessons | `lessons_to_add[]`, `lesson_ids_to_retire[]` |
| helper.ask | The question · the 5 best-matching help articles · a 5-line app state summary | A short plain-language answer |
| helper.suggest | One sentence from the user · the preset names | A filled-in pipeline form |

`style_bible` (a few sentences describing look, palette, character) is prepended to every
clip prompt — that is how clips stay visually consistent. The thumbnail is generated first and
passed to every clip call as a subject reference image (research §1) for the same reason.
Clips are independent calls of 3–15 whole seconds each (the model's limit), so a 60 s Short is
four or more clips. We do not use the model's "extend" feature: separate clips are simpler to
retry and to regenerate one at a time.

## Media (`media.py`) and practice mode

```python
async def generate_clip(prompt: str, seconds: int, *, settings) -> MediaResult      # bytes + units for costing
async def generate_thumbnail(prompt: str, *, settings) -> MediaResult
```

Both real versions use the Interactions API (`client.interactions.create`, research §1–2),
always with `delivery: "uri"` for video so there is one download path, and a generous
timeout — latency is undocumented. Video cost = seconds × tokens-per-second for the
resolution × the video output rate (≈ $0.07 per second at 720p).

Each starts with `if settings.practice_mode: return _practice_clip(...)`, which makes a
coloured test clip with ffmpeg's `lavfi` source (free, instant, no network). `youtube.upload`
does the same and returns a fake id starting with `practice-`. Practice results are recorded
as cost events of $0 so the UI still has something to show. Text agents are not faked in
practice mode — they cost cents and make the practice run meaningful.

## Storage (`storage.py`)

One small class, S3-shaped on purpose so an R2 / S3 version is a drop-in later (S1):
`put(key, data)`, `path(key)`, `exists(key)`, `delete(key)`, `list(prefix)`, `size(prefix)`.
Keys: `videos/{video_id}/clip_{index}.mp4`, `videos/{video_id}/final.mp4`,
`videos/{video_id}/thumb.png`. Reject any key that resolves outside the media folder.
No interface class — there is one implementation.

## Costs (`costs.py`)

- `PRICES`: one dict, model id → rates, copied from `docs/research.md` with the date. This is
  the only place prices live. We do not use Pydantic AI's built-in cost figure: it does not
  know the video model. Use Argon's post-2026-12-01 rate ($4 / $20) from day one.
- `record(session, *, stage, model, reason, input_tokens=0, output_tokens=0, units=0,
  unit_kind="tokens", video=None, pipeline=None) -> CostEvent`.
- `check_budget(session, video, upcoming_usd=0)` raises `BudgetExceeded` (C3).
- `summary(session, start, end)` → totals by stage, by pipeline, by day, per video, cost per
  view (spend on published videos ÷ their latest views), month to date vs budget, projection.

## HTTP API

JSON, prefix `/api`. Table models are returned directly unless noted.

```
GET  /status                         {checks:[{name, ok, message}], onboarding_done, practice_mode}
GET  /settings        PUT /settings
GET  /presets
GET  /pipelines       POST /pipelines        GET|PUT|DELETE /pipelines/{id}
POST /pipelines/suggest   {description}  → pipeline fields (not saved)
POST /pipelines/{id}/run  {count:1..3, is_test}  → queued videos
GET  /videos?pipeline_id=&status=    GET /videos/{id}  → video + clips + cost events + snapshots
POST /videos/{id}/approve | /reject {reason?} | /retry | /feedback {rating, note?}
DELETE /videos/{id}
GET  /media/{key}                    file from storage (FileResponse)
GET  /costs/summary?start=&end=      GET /costs/events?video_id=
GET  /insights?pipeline_id=          {lessons:[…], videos:[{id,title,published_at,views,likes,comments,avg_view_percent,cost_usd}]}
PUT|DELETE /lessons/{id}
GET  /youtube/status                 {connected, channel_title, needs_reconnect}
POST /youtube/connect | /youtube/disconnect
GET  /help/articles                  POST /help/ask {question, page} → {answer}
```

Errors: `{"detail": "<one plain sentence the user can act on>"}`.

## Frontend

Routes: `/` home (system check, "Needs you" inbox, what is in progress, this month's spend) ·
`/pipelines`, `/pipelines/new`, `/pipelines/[id]` · `/videos`, `/videos/[id]` (player, plan,
review notes, approve/reject, feedback, cost) · `/costs` · `/insights` · `/settings` ·
`/setup` (the guide). The help drawer lives in the root layout.

- `src/lib/api.ts` — one typed `fetch` wrapper; all server access goes through it.
- `src/lib/help/search.ts` — plain token-overlap ranking over the articles; no library.
- A handful of shared components: `Field` (label + "What is this?"), `StatusBadge`, `Money`,
  `BarList`, `HelpDrawer`. Do not build a component library.
- Pages with work in flight poll every 5 s. No websockets.
- Laptop first, usable at 375 px. Large readable type, generous spacing, one obvious primary
  action per screen, plain words. Dev: Vite proxies `/api` to the backend. Production: `pnpm
  build` → FastAPI serves `frontend/build` with SPA fallback.

Help article shape: `{id, title, body, pages:[route…], keywords:[…], show_me?:{href, highlight}}`.
"Show me" navigates to `href?highlight=<element id>`; the layout scrolls to and pulses that
element.

## YouTube notes (`youtube.py`)

- Token at `data/youtube_token.json`; scopes exactly as in research §5. While the owner's
  Google app is in "Testing" the sign-in expires every 7 days: a failed refresh must surface
  as `needs_reconnect`, never as a crash (Y3).
- Upload with `containsSyntheticMedia: true`, `selfDeclaredMadeForKids: false`, and always an
  explicit `privacyStatus` (omitting it means public).
- Set the thumbnail only after `processingStatus == "succeeded"`; a thumbnail failure is
  logged on the video, it does not fail the publish.
- The reviewer sends the stitched video inline when under 15 MB, otherwise through the Files
  API (research §3–4).

## Testing

- `backend/tests`, pytest. A fixture gives each test a temp data folder and a fresh SQLite file.
- Text agents: Pydantic AI's offline test models through `agent.override(...)` (research §4).
- Media: practice mode (real ffmpeg, tiny clips). YouTube: monkeypatch the functions in
  `youtube.py`. No test touches the network.
- API routes through FastAPI's `TestClient`.
- Frontend: vitest for pure logic only, plus `pnpm check` and `pnpm build`.

## Start-up

`start.command` → `cd backend && uv run python -m app` → builds the frontend if
`frontend/build` is missing, starts uvicorn on `127.0.0.1:8484`, opens the browser.
