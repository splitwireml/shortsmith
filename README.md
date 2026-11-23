# Shortsmith

Shortsmith makes YouTube Shorts for you. It plans a video, generates the
clips with Google's Gemini models, checks the result, waits for your
approval, uploads it, and learns from how viewers respond. It runs
entirely on your own computer; nothing is hosted anywhere.

## Start in three steps (Mac or Windows)

All you need is a [Gemini API key](https://aistudio.google.com/apikey) with
billing turned on. You don't have to type any commands.

1. On this page, click **Code → Download ZIP**, then unzip it.
2. Open the unzipped folder and double-click the starter:
   - **Mac:** `start.command`. If your Mac says it cannot check the file,
     right-click it, choose **Open**, then **Open** again. On newer macOS,
     go to **System Settings → Privacy & Security** and choose **Open Anyway**.
   - **Windows:** `start.bat`. If Windows says it protected your PC, click
     **More info → Run anyway**.

   The first time, the starter installs the tools Shortsmith needs: `uv`,
   `ffmpeg`, Node and `pnpm`. On a Mac it uses Homebrew, installing that
   too if needed, and may ask for your Mac password. On Windows it uses
   winget. Then it asks you to paste your Gemini key and builds the app.
   This takes a few minutes, once. After that, Shortsmith opens in your
   browser at <http://127.0.0.1:8484>.
3. Follow the **Setup guide** in the app.

To stop Shortsmith, close the window the starter opened. To start it
again, double-click the starter. Later starts open in seconds.

**Practice mode is on at first.** Clips are free placeholder clips and
nothing is uploaded, so you can try everything without paying for video.
Text calls (planning, reviewing) still use your key, but they cost cents.
Turn practice mode off in **Settings** when you want real videos.

## What it costs

You pay Google directly for what Shortsmith uses on your key. Video is
most of it: at 1080p (the default video size), a 30-second Short is about
$3. You can choose a smaller video size on each recipe to pay less. Two
spending limits, set in **Settings**, stop work before money is spent:
$30 a month and $6 per video to start with. The **Costs** page lists every charge.

## Publishing to YouTube (optional, about 10 minutes, once)

Shortsmith can make and review videos without this. To upload them, it
needs a Google sign-in file called `credentials.json`:

1. In the [Google Cloud console](https://console.cloud.google.com/), create a project.
2. Under **APIs & Services → Library**, turn on **YouTube Data API v3** and
   **YouTube Analytics API**.
3. Under **OAuth consent screen**, choose **External**, fill in the required
   fields, and add your own Google account as a **test user**.
4. Under **Credentials → Create credentials → OAuth client ID**, choose
   **Desktop app**, then download the JSON file.
5. Rename it `credentials.json` and put it in the Shortsmith folder, next to the starter.
6. In Shortsmith, open **Settings → Connect YouTube**.

While the consent screen is in "Testing", Google ends the YouTube sign-in
after 7 days, and you have to connect again in Settings. Publishing the
consent screen ("In production") stops that.

## Updating

Download the new ZIP and unzip it. Then move these from your old folder
into the new one: `.env`, `credentials.json` (if you have it) and the
`data` folder. Start Shortsmith from the new folder.

## Linux

Install [uv](https://docs.astral.sh/uv/), ffmpeg, Node and pnpm. Then
create a file called `.env` in the folder containing
`GEMINI_API_KEY=your-key`, and run:

```sh
cd backend && uv run python -m app
```

## Your data and keys

The database, video files and YouTube sign-in live in `data/`. The key is
in `.env`, and the Google sign-in file is `credentials.json`. Git ignores
all three, so they are never committed. Shortsmith only listens on your
own computer (127.0.0.1), and it never sends your key anywhere but Google.

## For developers

Python backend (FastAPI + Pydantic AI + SQLite) serving a SvelteKit
frontend from one process. Read [docs/02-architecture.md](docs/02-architecture.md)
before writing code and [docs/research.md](docs/research.md) before touching any
Google / Gemini / Pydantic AI / YouTube call. [AGENTS.md](AGENTS.md) has the rules
(secrets and money are non-negotiable there).

```sh
cd backend && uv run pytest -q            # backend tests (everything external mocked)
cd frontend && pnpm check && pnpm build   # frontend types + production build
```

For UI work, use the practice server: it uses temporary data, a fake key
and scripted agents, so no paid call is possible. Even the real app in
practice mode makes real (cheap) text calls; the practice server does not.

```sh
cd backend && uv run python tests/practice_server.py
cd frontend && pnpm dev                   # Vite dev server, proxies /api to :8484
```

`scripts/real_run.py` is a one-off paid end-to-end check: it makes a real
20-second Short and uploads it as private. It spends real money, so read
its header before running it.

Layout: `backend/app` (API, pipeline, agents), `backend/tests`,
`frontend/src`, `docs/` (product, architecture, API research).
