# Twitter CLI Workbench

Minimal Vue/Vite + FastAPI UI for the installed `twitter` CLI.

![Twitter CLI Workbench UI](./twitui.png)

## Prerequisites

- `twitter` is installed and authenticated on this machine.
- Python 3.12 or compatible Python 3.
- Node.js 22 or compatible Node.js.

## Run Backend

```bash
python3 -m pip install -r backend/requirements.txt
python3 -m uvicorn app.main:app --app-dir backend --reload
```

The API runs on `http://127.0.0.1:8000`.

All AI requests use the installed `codex` CLI. Run `codex login` before starting
the backend. No DeepSeek API key is used. Text requests run in temporary, read-only
workspaces with tools and image generation disabled, and return schema-constrained
JSON. Requests time out after three minutes; at most two text requests run at once.
There is no API fallback.

Optional backend environment variables:

- `CODEX_MODEL`: optional model override; omit to use the Codex CLI default.
- `GROWTH_DB_PATH`: defaults to `backend/growth.sqlite3`.

Put these in `.env` at the project root or `backend/.env`. Shell environment variables still win over `.env` values.

## Run Frontend

```bash
npm --prefix frontend install
npm --prefix frontend run dev
```

Open the Vite URL, usually `http://localhost:5173`.

## Run Both Services

```bash
./start.sh
./stop.sh
```

Defaults:

- Backend: `http://127.0.0.1:8010`
- Frontend: `http://localhost:5173`
- Logs and PID files: `.run/`

You can override ports:

```bash
BACKEND_PORT=8011 FRONTEND_PORT=5174 ./start.sh
```

## Verify

```bash
python3 -m pytest backend/tests -q
npm --prefix frontend test
npm --prefix frontend run build
```

The first screen fetches real data with `twitter feed --max 20 --json` through the FastAPI backend.

## Growth Mode

Growth Mode discovers candidate posts with `twitter search`, sends the candidate list to Codex CLI for `like`, `comment`, or `skip` recommendations, and shows each recommendation for manual approval.

No write action runs automatically. The UI shows the exact command and requires one approval per action before the backend executes `twitter like <tweet_id> --json` or `twitter reply <tweet_id> <text> --json`.

## Preference Memory

The app records approval and rejection context in the local Growth Mode SQLite database. For each decision it stores the source post, recommendation reason, available comment drafts, selected or edited comment, action, and outcome.

Before Codex CLI analyzes new candidates, the backend summarizes recent approved comments, rejected recommendations, and approved skips, then includes that memory in the Codex CLI request. This lets recommendations adapt toward the comments you approve and away from posts or drafts you skip or reject.

## Credits

This project uses [`public-clis/twitter-cli`](https://github.com/public-clis/twitter-cli) as the local Twitter/X command-line interface for fetching feeds, searching posts, and executing approved actions.

## License

Apache License 2.0. See [LICENSE](./LICENSE).

## Post Ideas

Both generation modes use the requested ASD-STE100-inspired writing style (roughly
80% of its principles, without claiming formal compliance): short active sentences,
one main idea per sentence, common words, consistent technical terms and concrete
examples where useful. Drafts must retain accuracy, uncertainty and important nuance;
clarity takes priority over brevity. This style overrides conflicting voice memory.

The UI defaults to **Trending AI & technology**. Each research run gathers the past
seven days of technology stories from Hacker News, recently created AI repositories
from GitHub, and official OpenAI, Hugging Face and Google DeepMind publisher feeds.
Drafts include validated source links, dates and available engagement counts. Hacker
News points and cumulative GitHub stars are separate popularity signals; publisher
announcements have no measured popularity. This is a curated source sample, not a
ranking of the entire internet. Provider failures are reported and usable sources
continue to work; a run with no recent sources fails without inventing replacements.
Draft generation uses the signed-in Codex CLI and posting still requires
manual approval. Select **My likes & bookmarks** for the personal interest mode below.

**Images and publishing:** Drafts are text-only by default. Enable **Generate images with drafts** to create an
editorial illustration for each draft through the installed, signed-in `codex` CLI.
The backend uses native Codex image generation in an isolated working directory,
with two image jobs at a time. No separate OpenAI API key is required for this path.
Run `codex login` locally if sign-in is needed. Native image access and usage limits
depend on the signed-in account. Generated files and job status live in
`backend/media/` (gitignored); set `POST_IMAGE_DIR` to change that location.

Review the image preview and editable text, then click **Approve and post text +
image** to publish both with one Twitter CLI command. This button waits for the
image to finish. Regenerate an image to replace it, or turn off **Include image**
to publish text alone. A failed or missing selected image never silently becomes a
text-only post. Drafts and image job references are saved in browser storage across
tab switches and reloads. Interrupted backend jobs show a retry message. The exact
image brief is available under each preview.

Post Ideas uses both likes and bookmarks, with a rolling 48-hour window. App-recorded
approved likes and bookmarks are filtered by their action time, so an older post
saved today still qualifies. The Twitter CLI does not expose engagement timestamps:
imported likes and bookmarks are filtered by the post publication date instead.
The UI shows this limitation and any source-fetch failures. Undated or future-dated
imports are excluded. Up to 100 posts per source are fetched, with up to 40 matching
posts per source sent to the generator; overlapping IDs are identified as the same
reference. If neither source has usable recent context, generation stops with an
explanation instead of producing unrelated generic ideas.

Profile focus and themes are optional. Recent interests lead topic selection, while
past approvals guide voice. Drafts still require explicit approval before posting.

## Feeds

The Feeds tab reads the authenticated account's actual For you home timeline.
Scrolling near the bottom loads the next Twitter cursor page, with duplicate post
IDs removed. Each post offers Like, Bookmark, and Open on X. Successful likes
and bookmarks are recorded with source context for Post Ideas. Latest posts starts a fresh timeline. The loaded feed stays available
when switching tabs. Photos load lazily; video links open the original post on X.

The public `twitter feed` command drops pagination cursors, so
`backend/app/feed_bridge.py` runs a one-page adapter inside the installed
`twitter-cli` Python environment, using the same authentication and serializer.
The adapter isolates the dependency on the client's internal timeline methods;
it does not modify the installed CLI. Set `TWITTER_CLI_PYTHON` to that environment's
Python executable if the `twitter` entry point is not a Python script.

Scrolling continues while Twitter returns advancing cursors. An exhausted timeline
shows an end message. Three consecutive pages without new posts pause automatic
requests and leave a Load more posts button available.

### Feed block list

Select a word or phrase in a post, right-click, and choose **Block**. Matching posts
are immediately hidden from Feeds, including later pages and quoted post text.
Matching ignores case and normalizes Unicode and whitespace, with whole-word
boundaries to avoid matching `AI` inside `said`. Punctuation is matched literally.

The **Block list** panel supports adding phrases manually and removing entries.
Selections also expose a Block button beneath the post, and Shift+F10 opens the
selection menu from the keyboard. Escape dismisses it. Preferences are saved in
this browser's local storage and apply only to this app's Feeds tab. Storage
failures are shown explicitly, with filtering retained for the current session.

Filtered posts remain available in memory, so removing a term restores matching
loaded posts in their original order. Automatic paging pauses after three pages
with no new visible posts, with manual loading still available.

### English-only feed and conversations

Feeds only displays posts marked `en` by Twitter. Other languages and missing or
unknown language labels are excluded, including quoted post text. This relies on
Twitter's language labels; the feed adapter preserves the language of quoted posts.
Language filtering and the block list both apply to newly loaded pages.

Click a feed post or use **View thread** to open its conversation alongside the
feed. The conversation column has its own scroll area and **Load more replies**
button. Like, Bookmark, Open on X, text selection, and block-list rules remain
available. Rapid post changes cancel previous thread requests. On narrow screens,
the conversation uses the full content width; Close thread returns to the saved
feed position. Escape closes the thread (or dismisses the text context menu first).
