# Build report — Shortsmith (2026-11-22)

All five sprints are done and committed locally (S1 `4b00bff`, S2 `ac3f904`, S3 `bbc61c6`,
S4 `a2059aa`, live-call fix `aad31a2`, S5 `57e8134`; nothing pushed). The real upload is
**still pending**: `data/youtube_token.json` did not exist at the end of the build (the Allow
click in the `yt-oauth` tab hasn't happened yet).

## What works
- The whole app: recipes with presets and one-sentence suggest, the video pipeline (plan →
  clips + thumbnail → stitch → review → one remake round → approval → private/unlisted/public
  upload), snapshots, the daily analyst and lessons, clean-up by age and size, money pages,
  budget caps, setup guide, help drawer with search, "Show me" and ask, practice mode.
- Checks at the end: backend `uv run pytest -q` **66 passed**; frontend `pnpm test` **20
  passed**, `pnpm check` 0 errors, `pnpm build` OK. `start.command` was tested from a fresh
  clone: it builds the pages on the first start, then serves them on 127.0.0.1:8484 with plain
  status messages. After the final clean-up, only the home page was checked in a browser.

## Verified with real APIs vs. practice only
- **Real calls, made through the app's own `pipeline.advance` so the ledger recorded them:**
  - Planner (Hydrogen, Pydantic AI structured output): worked, 15 s.
  - Thumbnail (Nano Banana 2.1): the first attempt got a 400 because the code sent
    `delivery: "inline"` for images. The fix is in the code and in `research.md`. The retry worked.
  - One 3 s 720p 9:16 Omni clip: thumbnail, clip, download and stitch took 59 s together.
  - Argon review of that clip: score 7.
  - The free Gemini key check in the status panel.
- **Only in mocks and practice mode:** everything on YouTube (OAuth connect inside the app,
  upload, thumbnail set, Data and Analytics stats), analyst and helper calls, a multi-clip video
  with real clips, the clip-remake path, and the Files API path for review uploads over 15 MB.

## Real spend (from the app's cost ledger)

| Stage | Model | Cost |
|---|---|---|
| planning | gemini-4-hydrogen | $0.0154 |
| thumbnail | gemini-nano-banana-2.1 | $0.0336 |
| video (3 s) | gemini-omni-1.2-flash | $0.2085 |
| review | gemini-4-argon | $0.0113 |
| **Total** | | **$0.2689** of the $10 cap |

The failed 400 attempt was rejected before any work started and was not billed.

## YouTube video id of the real upload
**None yet.** Once the token exists, close the app and run this one command:
`cd backend && uv run python ../scripts/real_run.py`
- It makes one 20 s Short (two 10 s clips at 720p), approves it on your behalf and uploads it
  **private** exactly once. Then it reads the stats once, including Analytics, and prints them.
- Expected cost: about $1.45, or up to about $2.15 if one clip is remade. The ledger would end
  at about $2.50 at most.
- It checks everything before spending anything. It refuses if the app is running, YouTube
  isn't connected or the sign-in has expired, the $10 ledger cap would be passed, or any real
  upload was ever attempted. Practice mode is switched back on at every exit.
- I ran it during the build with no token, and it refused correctly.

## Decisions you might not expect
- **New recipes start paused.** Saving a recipe never starts spending. The recipe page has
  one "Start the schedule" button, and it shows the monthly estimate.
- **Practice mode still makes real text calls**, as the spec asks (V5), so a practice video
  in the real app costs cents. Development and UI walkthroughs instead used
  `backend/tests/practice_server.py`: scripted AI, a fake key and temp data, so nothing can be spent.
- **Leftovers from the early real calls (1–4) are in your app:** they ran right after S3
  against the real `data/app.db`. You'll see a paused recipe "Real-call check (manager)"
  and its 3 s video #1, marked rejected. You can delete both; their costs stay in the ledger.
- **API key name:** the app reads the Gemini key from `GEMINI_API_KEY` or `GOOGLE_API_KEY`.
  Nobody opened `.env`; code only confirmed that a key is present.
- **Budget reserves:**
  - Before planning a real video, the whole video's estimate is reserved.
  - A review reserves $0.10.
  - Help, suggest and analyst calls also check the monthly cap.
  - Practice mode reserves no media cost.
- **Approvals:**
  - Auto-approve happens when the score is at or above the threshold.
  - Test videos never auto-approve.
  - Practice approvals say "Nothing was uploaded to YouTube".
- **Review suggestions I declined:**
  - Owner notes are never retired automatically, so more than 10 can be active. The
    planner still uses only 10.
  - Switching practice off while a practice video is still being made makes its remaining
    steps real.
  - A clip that was paid for but never arrived is recorded, but Retry pays for it again.
- **Tooling:**
  - `scripts/youtube_connect.py` is now part of `app/youtube.py`, with the same token path
    and scopes. The running `yt-oauth` process is unaffected.
  - pnpm was missing, so I enabled Node's bundled shim with
    `corepack enable pnpm --install-directory ~/.local/bin`. Undo it with
    `corepack disable pnpm --install-directory ~/.local/bin`.

## What is left
1. Click Allow in the `yt-oauth` tab (or use Connect YouTube in the app). Then run the
   command above and note the printed YouTube id here.
2. Nothing on YouTube has run live yet, so the first real publish is the real test of upload,
   thumbnail-after-processing and stats. Analytics data arrives 48–72 h after publishing.
3. The Google app is in "Testing", so the sign-in expires every 7 days. The app says so and
   offers Reconnect (Y3). Publishing the OAuth app removes that limit.
4. The app has no database migrations (v1). A later change to a table needs a fresh `data/app.db`.
