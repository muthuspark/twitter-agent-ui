# Twitter CLI Workbench Design

## Goal

Build a minimal professional UI for the installed `twitter` CLI. The app must pull real data through local CLI execution, starting with feed data, and present it in a Vue workbench UI.

## Stack

- Frontend: Vue 3, Vite, Tailwind CSS.
- Backend: FastAPI.
- CLI integration: Python subprocess wrapper around the local `twitter` binary.

## Product Shape

The first screen is a workbench, not a landing page. It has a restrained product layout: a left command preset panel, a center command/result area, and a right inspector/raw-output panel.

The initial command presets are:

- Feed: `twitter feed --max <n> --json`
- Search: `twitter search "<query>" --max <n> --json`
- Bookmarks: `twitter bookmarks --max <n> --json`
- Status: `twitter status --json`
- Whoami: `twitter whoami --json`

Write actions are out of scope for the first version.

## Backend Behavior

FastAPI exposes a small API:

- `GET /api/health` returns backend availability.
- `GET /api/presets` returns supported commands and field metadata.
- `POST /api/run` accepts a preset id plus typed options, builds a safe argument list, executes `twitter`, parses JSON, and returns normalized data.

The backend must avoid shell execution. It must validate preset ids, max values, and required fields before running the command.

## Frontend Behavior

The Vue app loads presets, allows the user to choose a command, edits command options, previews the command, runs it, and renders structured output.

Tweet arrays render as readable cards with author, handle, timestamp, text, media badge, and metrics. Non-tweet objects render as a compact JSON inspector. Errors and empty states are visible inline.

## Error Handling

The UI shows:

- CLI not found.
- CLI timeout.
- Auth failures and other non-zero CLI exits.
- Invalid JSON output.
- Empty result sets.

## Verification

Backend tests cover command construction, validation, JSON parsing, and subprocess error mapping. Frontend build verifies the Vue/Tailwind app compiles. Manual verification runs the dev servers and confirms real feed data appears.
