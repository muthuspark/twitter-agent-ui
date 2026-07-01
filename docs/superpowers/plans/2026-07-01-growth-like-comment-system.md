# Growth Like Comment System Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a Growth Mode that discovers relevant X posts, uses DeepSeek to recommend like/comment/skip decisions, and executes only individually approved write actions.

**Architecture:** FastAPI exposes growth endpoints for discovery, DeepSeek analysis, approval execution, and history. The backend executes `twitter` commands with argument arrays only and stores recommendation/action history in SQLite. Vue adds a Growth Mode tab with keyword settings, candidate discovery, recommendation cards, edit-before-approval controls, and history.

**Tech Stack:** FastAPI, SQLite, httpx, Vue 3, Vite, Tailwind CSS, DeepSeek chat completions JSON mode.

---

## Task 1: Backend Growth Core

**Files:**
- Create: `backend/app/growth.py`
- Create: `backend/app/deepseek_client.py`
- Create: `backend/app/storage.py`
- Modify: `backend/app/twitter_cli.py`
- Test: `backend/tests/test_growth.py`

- [ ] Write failing tests for candidate normalization, DeepSeek recommendation parsing, approval command construction, and SQLite history.
- [ ] Run `python3 -m pytest backend/tests/test_growth.py -q`; expect missing module failures.
- [ ] Implement growth service modules.
- [ ] Re-run `python3 -m pytest backend/tests/test_growth.py -q`; expect pass.

## Task 2: Backend API Routes

**Files:**
- Modify: `backend/app/main.py`
- Test: `backend/tests/test_growth_api.py`

- [ ] Write failing tests for `/api/growth/discover`, `/api/growth/analyze`, `/api/growth/approve`, `/api/growth/reject`, and `/api/growth/history`.
- [ ] Run `python3 -m pytest backend/tests/test_growth_api.py -q`; expect missing route failures.
- [ ] Implement routes and exception mapping.
- [ ] Re-run `python3 -m pytest backend/tests/test_growth_api.py -q`; expect pass.

## Task 3: Frontend Growth Mode

**Files:**
- Modify: `frontend/src/lib/workbench.js`
- Modify: `frontend/src/lib/workbench.test.js`
- Modify: `frontend/src/App.vue`

- [ ] Add frontend helper tests for recommendation normalization and action labels.
- [ ] Run `npm --prefix frontend test`; expect missing helper failures.
- [ ] Add Growth Mode UI with discovery, analysis, approval, rejection, and history panels.
- [ ] Re-run `npm --prefix frontend test`; expect pass.
- [ ] Run `npm --prefix frontend run build`; expect pass.

## Task 4: Verification

**Files:**
- Modify: `README.md`

- [ ] Document `DEEPSEEK_API_KEY`, `DEEPSEEK_MODEL`, and `GROWTH_DB_PATH`.
- [ ] Run `python3 -m pytest backend/tests -q`; expect pass.
- [ ] Run `npm --prefix frontend test`; expect pass.
- [ ] Run `npm --prefix frontend run build`; expect pass.
- [ ] Verify discovery with the real installed CLI via `/api/growth/discover`.
