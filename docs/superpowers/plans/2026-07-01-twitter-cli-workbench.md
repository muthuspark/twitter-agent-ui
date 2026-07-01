# Twitter CLI Workbench Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Vue/Vite + Tailwind frontend backed by FastAPI that runs the installed `twitter` CLI and displays real feed data.

**Architecture:** FastAPI owns command validation and subprocess execution with argument arrays only. Vue consumes `/api/presets` and `/api/run`, rendering tweet arrays as cards and JSON objects in an inspector. Vite proxies `/api` to FastAPI in development.

**Tech Stack:** Vue 3, Vite, Tailwind CSS, FastAPI, pytest, httpx, uvicorn.

---

## File Structure

- `backend/app/models.py`: Pydantic request/response models.
- `backend/app/twitter_cli.py`: Preset definitions, safe command building, subprocess execution, JSON parsing.
- `backend/app/main.py`: FastAPI routes.
- `backend/tests/test_twitter_cli.py`: Unit tests for backend command behavior.
- `backend/tests/test_api.py`: API tests using dependency overrides.
- `frontend/src/App.vue`: Workbench UI.
- `frontend/src/main.js`: Vue entrypoint.
- `frontend/src/style.css`: Tailwind imports and app-level styling.
- `frontend/index.html`, `frontend/vite.config.js`, `frontend/package.json`, `frontend/tailwind.config.js`, `frontend/postcss.config.js`: Vite/Tailwind setup.
- `README.md`: Run instructions.

## Tasks

### Task 1: Backend CLI Core

**Files:**
- Create: `backend/app/models.py`
- Create: `backend/app/twitter_cli.py`
- Create: `backend/tests/test_twitter_cli.py`

- [ ] Write tests for preset command building, max validation, required search query validation, successful JSON parsing, non-zero exits, timeouts, missing binary, and invalid JSON.
- [ ] Run: `python3 -m pytest backend/tests/test_twitter_cli.py -q`; expected failure because modules do not exist yet.
- [ ] Implement `models.py` and `twitter_cli.py` with safe argument-list execution.
- [ ] Re-run: `python3 -m pytest backend/tests/test_twitter_cli.py -q`; expected pass.

### Task 2: FastAPI Routes

**Files:**
- Create: `backend/app/main.py`
- Create: `backend/tests/test_api.py`

- [ ] Write API tests for health, presets, run success, and run validation failure.
- [ ] Run: `python3 -m pytest backend/tests/test_api.py -q`; expected failure because routes do not exist yet.
- [ ] Implement FastAPI routes and dependency injection for the CLI runner.
- [ ] Re-run: `python3 -m pytest backend/tests/test_api.py -q`; expected pass.

### Task 3: Frontend Workbench

**Files:**
- Create: `frontend/package.json`
- Create: `frontend/index.html`
- Create: `frontend/vite.config.js`
- Create: `frontend/tailwind.config.js`
- Create: `frontend/postcss.config.js`
- Create: `frontend/src/main.js`
- Create: `frontend/src/style.css`
- Create: `frontend/src/App.vue`

- [ ] Create Vite/Vue/Tailwind configuration.
- [ ] Implement command presets, option controls, command preview, run button, tweet cards, JSON inspector, and error/empty states.
- [ ] Run: `npm --prefix frontend install`.
- [ ] Run: `npm --prefix frontend run build`; expected pass.

### Task 4: Project Setup And Verification

**Files:**
- Create: `backend/requirements.txt`
- Create: `backend/app/__init__.py`
- Create: `backend/tests/__init__.py`
- Create: `README.md`
- Create: `.gitignore`

- [ ] Add Python requirements and project docs.
- [ ] Run: `python3 -m pytest backend/tests -q`; expected pass.
- [ ] Run: `npm --prefix frontend run build`; expected pass.
- [ ] Start FastAPI and Vite dev servers.
- [ ] Confirm `POST /api/run` with feed returns real CLI data.
