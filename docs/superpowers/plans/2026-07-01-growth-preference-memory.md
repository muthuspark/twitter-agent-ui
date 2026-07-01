# Growth Preference Memory Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Phase 1 and Phase 2 memory so DeepSeek recommendations learn from approved comments, rejected comments, skipped posts, and selected drafts.

**Architecture:** Reuse the existing SQLite-backed `GrowthStore`. Store source candidate snapshots and recommendation metadata in action history, derive a compact preference memory summary from recent actions, and pass that memory into DeepSeek analysis prompts.

**Tech Stack:** FastAPI, SQLite, pytest, DeepSeek chat completions JSON mode.

---

## Tasks

### Task 1: Persist Decision Context

**Files:**
- Modify: `backend/app/storage.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/test_growth.py`
- Test: `backend/tests/test_growth_api.py`

- [ ] Write failing tests for storing source tweet text, author, recommendation reason, selected draft, and available drafts on approve/reject records.
- [ ] Implement action metadata persistence with backward-compatible SQLite migration.
- [ ] Verify tests pass.

### Task 2: Preference Memory Summary

**Files:**
- Modify: `backend/app/storage.py`
- Test: `backend/tests/test_growth.py`

- [ ] Write failing tests for deriving approved comment examples, rejected/skip patterns, and concise preference summary.
- [ ] Implement `preference_memory()`.
- [ ] Verify tests pass.

### Task 3: Inject Memory Into DeepSeek

**Files:**
- Modify: `backend/app/deepseek_client.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/test_growth.py`
- Test: `backend/tests/test_growth_api.py`

- [ ] Write failing tests proving DeepSeek receives `preference_memory`.
- [ ] Add optional `preference_memory` parameter to `analyze_with_deepseek`.
- [ ] Inject store-derived memory in `/api/growth/analyze`.
- [ ] Verify full backend and frontend checks pass.
