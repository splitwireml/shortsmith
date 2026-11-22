# Shortsmith — product & functional requirements

A local web app that plans, generates, reviews, publishes and learns from YouTube Shorts,
for one barely-technical person running it on their own laptop.

## Who uses it

One person. Comfortable with websites, not with terminals, APIs or "agents". They start the
app with one double-click, and everything else happens in the browser. Every screen must be
understandable without reading documentation. Plain words everywhere: "recipe", "make a
video", "money spent" — never "pipeline run", "inference", "tokens".

## Words we use

| Term | Meaning |
|---|---|
| **Pipeline** | A saved recipe for one kind of video (shown to the user as "Channel recipe"). Educational, animals, comedy… A user can have several. |
| **Video** | One Short moving through the stages below. |
| **Clip** | One generated video segment. A video is several clips stitched together. |
| **Lesson** | One short sentence the system has learned ("Hooks that ask a question get more views"). Comes from analytics or from the user. Fed back into planning. |
| **Cost event** | One row per paid AI call. The single source of truth for money. |
| **Snapshot** | The numbers for a published video at one moment (6h, 24h, … after publish). |

## The life of a video

```
queued → generating → reviewing → awaiting_approval → approved → publishing → published
                                           ↘ rejected
any stage ↘ failed (shows why, has a Retry button)        old media → archived
```

The status names the work that is due next (`queued` = waiting to be planned; the UI shows
it as "Planning").

| Stage | What happens | Model |
|---|---|---|
| Planning | Theme, hook, title, description, tags, scene-by-scene direction, art style, thumbnail idea. One call. | Gemini 4 Hydrogen, high effort |
| Generating | One clip per scene, a thumbnail, then stitch clips into a vertical MP4 with ffmpeg. | Gemini Omni Flash (video), Nano Banana 2 (thumbnail) |
| Reviewing | The model watches the whole stitched video once, scores it, and names any bad clip. Bad clips are regenerated once, then it is checked one final time. | Gemini 4 Argon, high effort |
| Approval | The human watches it in the dashboard and presses Approve or Reject. Optional per-pipeline auto-approve above a review score. | — |
| Publishing | Upload to YouTube with title, description, tags, thumbnail. | YouTube Data API |
| Learning | Snapshots are collected on a schedule. An analyst turns numbers into lessons. | Gemini 4 Hydrogen, medium effort |

## Functional requirements

Each has an ID so tests and reviews can point at it.

### Pipelines (recipes)
- **P1** Create, edit, pause, resume, delete a pipeline. Fields: name, niche, objective,
  audience, region & language quirks, genre/tone, art style, target length (15–60 s),
  how often (every N days, M videos each time), approval mode (manual / auto above score),
  YouTube visibility (private / unlisted / public), free-text extra notes. The form shows a
  live estimate: "about $X per video, about $Y per month" (video is ~$0.07 per second and
  is nearly all of the cost).
- **P2** Presets: start from "Educational", "Animals", "Comedy", "Motivation", "Facts" or
  blank. A preset fills every field with sensible values.
- **P3** "Describe it in a sentence" — the user types one sentence, AI fills the form, the
  user corrects it. (Hydrogen, low effort. Optional; the form works without it.)
- **P4** "Make a video now" and "Make a test batch (1–3)". Test videos never publish until
  approved.

### Making videos
- **V1** A video advances through the stages by itself and survives an app restart: every
  stage saves its result, and the app resumes from the last finished stage.
- **V2** The planner sees only: the pipeline brief, up to 10 active lessons, and the titles
  of the last 15 videos of that pipeline (to avoid repeats). Nothing else.
- **V3** Review regenerates only the clips named as bad, at most one round.
- **V4** A failed stage records a plain-language reason and offers Retry. Retry reuses
  everything already paid for (finished clips are not regenerated).
- **V5** Practice mode (global switch): video, thumbnail and YouTube upload are faked
  (coloured test clips, no upload). Text AI still runs — it costs cents. The UI shows a
  clear "Practice mode" banner.

### Approval & feedback
- **A1** An "Needs you" inbox on the home page lists videos awaiting approval.
- **A2** Approve, or reject with an optional reason. One click each.
- **A3** Thumbs up/down plus an optional note on any video, before or after publishing.
- **A4** Notes and rejection reasons become lessons (source: you) immediately, word for word.

### Publishing
- **Y1** Connect YouTube with one button (Google sign-in opens in the browser). Show which
  channel is connected. Disconnect button.
- **Y2** Upload on approval. Never upload the same video twice (guarded by a stored
  YouTube video id and a "publishing" lock).
- **Y3** Tell the user, in plain words, when the Google connection has expired and how to
  reconnect.

### Analytics & learning
- **L1** After publishing, take snapshots at fixed checkpoints (see architecture).
- **L2** The analyst runs at most once a day per pipeline, only when new mature snapshots
  exist, over a compact table of that pipeline's recent videos. It may add, replace or retire
  lessons. At most 10 active lessons per pipeline.
- **L3** The Insights page shows the lessons and a per-video performance table. The user can
  switch any lesson off or delete it.

### Money
- **C1** Every paid call writes a cost event: stage, model, amounts, dollars, and a one-line
  plain-language reason ("3 clips × 8 s of video").
- **C2** Costs page: this month vs budget, projected month end, spend by stage with the
  reason each stage costs what it does, by pipeline, by day, cost per video, cost per view.
- **C3** Monthly budget and per-video cap. Before any paid stage the app checks both; if
  either would be exceeded the video stops with a clear message and nothing is spent.
- **C4** Every video page shows exactly what that video cost, by stage.

### Storage
- **S1** All media lives under one data folder through a storage module with S3-style
  keys, so it can later be pointed at Cloudflare R2 / S3 without touching callers.
- **S2** Clean-up, daily: delete media of unpublished videos older than N days (they become
  "archived"), delete local copies of published videos older than N days, and if the
  folder exceeds X GB delete oldest first. Database rows are kept.

### Setup, settings, help
- **H1** Setup guide (onboarding): check everything is working → connect YouTube → create a
  first recipe → set a budget → make a practice video. Can be reopened from the menu at any
  time and skipped at any step.
- **H2** System check, always visible on the home page: Gemini key works, YouTube connected,
  ffmpeg present, disk space. Green tick or a plain-language fix.
- **H3** Settings page: budget, per-video cap, retention days, storage cap, practice mode,
  and an "Advanced" section (collapsed) for model names and effort levels.
- **H4** Help drawer on every page (button and `?` key): instant type-to-search over
  built-in articles, the current page's articles first, "Show me" links that jump to the
  right screen and highlight the control. No AI in the search.
- **H5** Every form field has a "What is this?" explanation.
- **H6** "Ask the assistant" inside the help drawer for when search does not find it:
  answers only from the help articles plus a short summary of the app's current state.
  (Hydrogen, low effort; cost recorded under "help".)

## Deliberately left out (add when someone asks)

- Scheduled publish times (we publish on approval).
- Burned-in captions and background-music mixing (the video model produces its own audio).
- Trend research with web search during planning.
- Multiple YouTube channels, user accounts, login. It is a single-user local app bound to
  `127.0.0.1`.
- Database migrations. Tables are created at start-up; this is a v1.
