# AGENTS.md

Instructions for AI coding agents (and future-you) working in this repo.

## What this is

RiverGuard: private-network river monitoring. FastAPI + SQLite backend (`api.py` sensor receiver on port 8000, `ui_api.py` web API on port 8501), React 19 + TypeScript + Plotly frontend (`frontend/`), local-AI chat assistant "Rill" over Ollama/Gemini. `dashboard.py`/`setup_ui.py` are the legacy Streamlit UI — not used by the live app, kept for reference/rollback only. See `README.md` for the full picture.

## Routine commands

Backend (from repo root, `.venv` already set up by `Setup RiverGuard.cmd`):
```
.venv\Scripts\python -m pytest tests -q        # run backend tests (NOT bare `pytest -q` from root — it picks up a stale output/repository/ snapshot and fails on duplicate module names)
.venv\Scripts\python serve.py --web-port 8504 --sensor-port 8001 --db output/review.db --no-browser   # isolated review server, safe sandbox, doesn't touch the real data/ db
```

Frontend (from `frontend/`):
```
npm run build      # tsc -b && vite build — do this before trusting any TS/CSS change
npm test           # node --test tests/*.test.mjs
```

Always run both test suites and a frontend build before calling a change done. For anything visual, actually open it — isolated review server + browser, not just a green build.

## Conventions already in place — follow them, don't fight them

- **No comments in source** unless the WHY is genuinely non-obvious. The existing code is dense/terse by design (no formatting whitespace in JSX/CSS); match that style rather than reformatting files you touch.
- **Pure logic lives in small `*State.ts` modules** (`modelState.ts`, `historyState.ts`, `chatState.ts`) next to their component, each with a `frontend/tests/*.test.mjs` file using Node's built-in test runner — no Vitest/Jest/RTL installed. When fixing a bug in a component, prefer extracting the fixable logic into one of these pure modules and testing it there over leaving it untested inside a component.
- **CSS custom properties live in `:root` in `frontend/src/styles.css`** (`--mint`, `--lavender`, `--amber`, `--red`, `--ease`, `--motion*`, spacing/radius/type tokens). Use them, don't add new raw hex — the file's long-standing problem was hundreds of one-off hex values drifting from the brand palette instead of reusing variables.
- **Dark-mode only**, no light theme or toggle. Respect `prefers-reduced-motion` on anything animated (already handled globally — don't bypass it).
- **No test-only tooling has been added without asking** (no Vitest/RTL, no visual-regression tool). If a fix would be much safer with one, say so and ask before adding a new dependency.
- Some local development copies have no `.git`. Ask before initializing Git in such a copy; use the existing repository history when publishing updates.

## Versioning

Starting from this point, `frontend/package.json`'s `version` moves on every real round of changes instead of sitting at a fixed `"2.0.0"` forever. Stay on major `2` (don't bump to `3.x`) unless there's an actual breaking/ground-up rewrite; within that:

- **Bump the minor version** (`2.1.0` → `2.2.0` → `2.3.0`) for a notable round of changes — a new feature, a visual/design pass, a cycle of real bug fixes. This is "a major change" in everyday terms, just not a semver-major one.
- **Bump the patch version** (`2.1.0` → `2.1.1` → `2.1.2`) for a small fix or tweak on top of the current minor version.
- Bump it as part of the change that earns it, not as a separate step — and mention the new version number when you do.
