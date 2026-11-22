# Shortsmith

Shortsmith makes YouTube Shorts for you: it plans a video, generates the
clips, checks the result, waits for your approval, uploads it, and learns
from how viewers respond. It runs entirely on your own laptop.

## How to start it

Double-click **start.command**. The first start builds the app's pages
(this takes a few minutes, once), then Shortsmith opens in your browser
at <http://127.0.0.1:8484>. Later starts open straight away. To stop it,
close the black window it opened (or press Ctrl-C in it).

Before the first start, three things need to be in place — ask whoever set
this up for you if they are missing:

- A `.env` file in this folder holding your Gemini API key
  (`GEMINI_API_KEY=…`). Never share it or send it anywhere.
- For publishing: a `credentials.json` file (Google sign-in details) in
  this folder. The app itself walks you through connecting YouTube.
- The tools the app leans on: `uv`, `ffmpeg`, and Node with `pnpm`
  (only needed to build the pages on the first start).

Inside the app, the **Setup guide** walks through everything in order:
checking all is well, connecting YouTube, making your first channel
recipe, setting a budget, and making a practice video. Practice mode is
on when you first start — clips are free test clips and nothing is
uploaded, so you can try everything safely. Turn it off in Settings when
you are ready to make a real video.

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

Run it for real (reads the repo `.env` and `data/`):

```sh
cd backend && uv run python -m app        # http://127.0.0.1:8484, opens the browser
```

For UI work, prefer the practice server — temp data, fake key, scripted
agents, no paid call is possible. Note even the real app in practice mode
still makes real (cheap) text calls; the practice server does not:

```sh
cd backend && uv run python tests/practice_server.py
cd frontend && pnpm dev                   # Vite dev server, proxies /api to :8484
```

`scripts/real_run.py` is the one-off paid end-to-end proof (real 20 s
Short, uploaded private, with ledger and duplicate-upload guards). Do not
run it casually — it spends real money; see its header for the exact rules.

Layout: `backend/app` (API, pipeline, agents), `backend/tests`,
`frontend/src`, `docs/` (product, architecture, API research). Runtime
state lives in `data/` (database, media, YouTube token) and is never
committed.
