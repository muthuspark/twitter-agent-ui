# Twitter Agent

Minimal Vue/Vite + FastAPI UI for the installed `twitter` CLI.

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
workspaces with shell, app and image tools disabled, and return schema-constrained
JSON. The research step enables live web search; curation and drafting use only
the gathered sources. Each CLI request times out after three minutes; at most two run at once.
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

The app opens on Feed, which fetches the timeline through the FastAPI backend. The former Workbench screen, command presets, raw command runner and result inspector have been removed.

## Frontend structure

- `App.vue` owns navigation and article deep links. Its view list defines the five
  screens; screens load on first visit and retain their state through `KeepAlive`.
- `components/Feeds.vue` owns its timeline, thread and block list and is the
  default screen. Shared date/number formatting lives in `lib/format.js`; shared
  social action payloads and links live in `lib/social.js`.
- Each screen owns its requests and lifecycle. Feed paging and customer polling
  stop when their screen is inactive. A draft operation can finish while another
  screen is open without discarding the draft.
- `style.css` owns shared colors, system typography, spacing and the three button
  styles: `button`, `button button-primary`, `button button-quiet`. Component styles
  cover layouts specific to that screen. Use monospace only for code.
- `ReportTable.vue` renders analytics using captions, column headers and formatted
  values. New reports are column definitions in `AnalyticsDashboard.vue`.

Keep visible copy to task names, controls, data and actionable state. Use layout
and ordering to explain the workflow. Put supporting evidence and configuration
behind named disclosures; keep accessible labels even when their visible duplicate
is removed. Preserve draft storage keys, API payloads and explicit publishing actions.

The legacy `GET /api/presets` and `POST /api/run` endpoints and their request
models have been removed. X search, bookmarks and identity reads remain dedicated
helpers for the other features. Existing Post Ideas and Customers draft storage
keys remain compatible with saved drafts.

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

`essay.md` at the project root is the editorial foundation for every generation
mode. The backend rereads the complete file on every request and fingerprints the
version. Missing or incomplete essays stop generation. Popularity and voice
memory cannot replace this foundation. Each draft includes its idea type,
an explicit connection to the essay and validated references. Ideas can develop,
test or challenge the thesis; hypothetical claims must not become measured facts.

Every source and draft must answer: **What does this reveal about the future of
companies as software factories run by one person or a small group of people?**
The connection must explain a change in how the company operates, or a concrete
barrier to that change. Both supporting evidence and counterevidence qualify.

Research runs automatically. The full essay guides live web searches across recent
news, Hacker News discussions, public social posts, project releases and research
papers from the past seven days. Direct Hacker News, GitHub and publisher feeds
supplement those results with source-specific engagement data. Inaccessible or
empty search pools are reported; search results are not proof of viral reach.
Codex then selects only sources with a concrete connection to the essay, including
counterevidence. The research panel shows this selected set. If no sources qualify
or research is unavailable, the app explicitly falls back to the essay alone and
does not invent current events.

The form offers **All types**, **Projects**, or
**Thought leadership**, plus draft count. Project posts examine
actual recent projects, their mechanisms and limits for a solo operator. Thought
leadership posts develop specific arguments, tradeoffs and implications within the
essay's subject. There is no research-source or angle control; the essay supplies
the direction. Saved source and angle choices do not affect new requests. Legacy
explicit API source modes remain available for existing integrations.

The UI shows the essay title and each draft's connection, and prevents posting
saved drafts from a previous essay version. Earlier general-purpose drafts remain
in their original browser storage; essay-based drafts use a separate storage key.

All generation modes use the requested ASD-STE100-inspired writing style (roughly
80% of its principles, without claiming formal compliance): short active sentences,
one main idea per sentence, common words, consistent technical terms and concrete
examples where useful. Drafts must retain accuracy, uncertainty and important nuance;
clarity takes priority over brevity. This style overrides conflicting voice memory.

The UI uses essay-led research. Each research run gathers the past
seven days of technology stories from Hacker News, recently created AI repositories
from GitHub, and official OpenAI, Hugging Face and Google DeepMind publisher feeds.
Drafts include validated source links, dates and available engagement counts. Hacker
News points and cumulative GitHub stars are separate popularity signals; publisher
announcements have no measured popularity. This is a curated source sample, not a
ranking of the entire internet. Provider failures are reported and usable sources
continue to work; a run with no recent sources fails without inventing replacements.
Draft generation uses the signed-in Codex CLI and posting still requires
manual approval. Interest-based research remains available to existing API clients.

**Publishing:** Review and edit the final draft, then click **Post to X**
to publish text through the Twitter CLI. Posts are text-only; image generation and
attachments are not supported. Saved drafts from earlier versions still load,
without their image controls or attachments.

The **My likes & bookmarks** mode uses a rolling 48-hour window. App-recorded
approved likes and bookmarks are filtered by their action time, so an older post
saved today still qualifies. The Twitter CLI does not expose engagement timestamps:
imported likes and bookmarks are filtered by the post publication date instead.
The UI shows this limitation and any source-fetch failures. Undated or future-dated
imports are excluded. Up to 100 posts per source are fetched, with up to 40 matching
posts per source sent to the generator; overlapping IDs are identified as the same
reference. If neither source has usable recent context, generation stops with an
explanation instead of producing unrelated generic ideas.

The optional angle narrows the essay's subject. Recent interests supply references
within that boundary, while past approvals guide voice. Drafts still require explicit
approval before posting.

## Feeds

The **Feed** tab reads the authenticated account's actual For you home timeline.
Scrolling near the bottom loads the next Twitter cursor page, with duplicate post
IDs removed. Each post offers Like, Bookmark, and Open on X. Successful likes
and bookmarks are recorded with source context for Post Ideas. **Refresh** starts a fresh timeline. The loaded feed stays available
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

## Potential Customers

The **Customers** tab runs 20 problem-focused queries across public X,
Reddit, LinkedIn and Hacker News. Reddit uses OpenCLI and your signed-in Chrome;
X, LinkedIn and Hacker News use Codex live web research. It opens original
posts, distinguishes personal pain from vendor promotion, and compares prospect
requirements with the current local Jovis source. Research never contacts people
or publishes replies automatically. X access is not required; inaccessible platforms and failed
search groups appear as limitations rather than invented results.

Click **Find customers**. The background run publishes partial results
as each group of four queries completes. Refreshing or switching tabs reconnects
to the latest run. Repeated clicks join the active run. Completed results persist
in `backend/prospects.sqlite3`; an interrupted server run preserves completed
results and is labeled interrupted. This local tool uses a single backend worker
process for research coordination.

- `JOVIS_REPO_PATH`: defaults to the sibling `../agent` repository. Inspection is
  read-only and never changes Jovis. Missing source stops research with an error.
- `PROSPECTS_DB_PATH`: optional override for the research database.
- `OPENCLI_PATH`: optional path to the `opencli` executable when it is not on the
  backend's PATH. This is a path, not a shell command.
- `OPENCLI_PROFILE`: optional connected Chrome profile alias/context ID. With
  multiple profiles, choose explicitly using `opencli profile list`.
- `REDDIT_CLI_BACKEND`: defaults to `opencli`. Set `rdt` only to opt into the legacy
  cookie client (`uv tool install rdt-cli==0.4.1`, then `rdt login`). That optional
  client uses `REDDIT_CLI_PATH` when provided; it can be blocked even with valid
  cookies, so the app does not automatically fall back to it.

### Connect Reddit

Install the supported CLI release on the machine running the backend:

```bash
npm install -g @jackwener/opencli@2.0.2
```

Add the [OpenCLI Browser Bridge extension](https://chromewebstore.google.com/detail/opencli/ildkmabpimmkaediidaifkhjpohdnifk)
to the Chrome profile where you use Reddit. Sign in to reddit.com normally and
keep Chrome open. Verify the connection from the backend machine:

```bash
opencli doctor
opencli reddit whoami
```

The Customers tab shows Reddit connection status and a **Refresh Reddit status**
button. Its status endpoint is `GET /api/prospects/sources/reddit/status`.
The backend must reach OpenCLI's local daemon and the connected Chrome profile.
Refresh browser login normally if necessary. Restart the backend after changing
its PATH or environment configuration.

The app verifies identity through `opencli reddit whoami`. Search navigates a
dedicated browser search tab and reads its rendered result units; OpenCLI's built-in
fetch-based search can hit a login wall even when browser navigation works.
The app reads selected posts with `opencli reddit read`, using the search result's
date and permalink and the reader's original text/author. Empty results require
an explicit empty-state message; loading pages and markup changes become errors.
Each worker owns its own search session, which is released after the run without
closing user tabs.

Reddit searches use the same 20 queries, relevance sorting, a past-month filter,
and at most 10 results per query. Codex selects up to three candidates per query
without browsing. Each selected post is fetched by ID with up to 25 comments;
post IDs are deduplicated across the run. Comments provide context, not separate
leads. Deleted/removed posts and vendor pitches are excluded. Pain quotes must
match the fetched original title or body; author, date and URL come from CLI data.
Partial comment coverage is labeled. No exhaustive comment expansion or pagination
is performed in this version.

The adapter uses the existing browser session without exporting cookies. The app
never accepts cookie uploads or puts credentials or raw CLI diagnostics into AI
prompts, research records or API responses. It only invokes identity checks,
read-only search-page navigation/extraction, post reading, and owned-tab cleanup.
The separate **Post on Reddit** action publishes only the reply you choose in the
editor. It does not expose messaging, voting or subscription commands.

Missing authentication, CLI errors or rate limits do not stop the other platforms.
Reddit web search is allowed as an explicitly labeled fallback, and does not count
as a successful CLI search. Rate limits or authentication/access failures suspend
further Reddit CLI requests for that run. Research details show per-query CLI
status, returned/inspected counts, errors and fallback attempts. Successful empty
searches count as searched. Coverage failures make a run partial; old saved runs
show Reddit coverage as not recorded. CLI calls run sequentially with a 60-second
timeout. The existing 20-query counter counts a query when either CLI search or
web research succeeded; it is not a count of successful searches on every platform.

For a local smoke test after login:

```bash
opencli reddit whoami
opencli reddit read POST_ID --limit 25 --depth 1 --max-length 40000
```

Use an actual Reddit post ID in place of `POST_ID`, then run **Find customers**
to test the app's browser-backed search. OpenCLI 2.0.2 returns `ok/data/error` JSON
envelopes; unsupported responses are reported instead of accepted as empty results.
Post reads request up to 25 top-level comments, with no reply or "more comments"
expansion. Their coverage is always labeled partial because the reader's output
does not certify completeness. Search navigation and browser reads were verified
with extension 1.0.26.

### Product assessment and review

In **Review and reply**, edit the suggested reply or choose **Write a reply** to
start from scratch. Drafts autosave and retain version history. For Reddit posts,
**Post on Reddit** publishes the exact editor text as a top-level comment using
the account displayed next to the button. Chrome must remain connected. The
backend rechecks that account immediately before submission and saves the reviewed
text first. Other platforms retain their existing edit/copy workflow.

`POST /api/prospects/runs/{run_id}/publish` accepts `url`, `text`, and `username`,
and returns a publication status and comment link when confirmed. Posting is
limited to saved Reddit prospects and replies of 1–10,000 characters. Publication
records persist per Reddit thread across research runs, so repeated clicks do not
duplicate a confirmed or in-flight reply. Definite rejections may be retried
manually; timeouts or missing confirmation pause further posting for that thread
and direct you to check Reddit. Existing replies are not edited by changing the
draft after publication. Posting code is tested with mocked Reddit responses;
automated verification does not publish test comments to real discussions.

The code inspection extracts connector interfaces, read/write tool inventories,
and selected commitment, journal, scheduling and delivery policy excerpts. It
rereads these on every run and fingerprints the evidence. When the `semble` CLI is
installed, each discovered complaint also runs a semantic search across Jovis
code. The five best chunks supplement the inventory after their paths and contents
are checked against current application source. Missing semantic search and stale
index entries are explicit limitations. This wider retrieval can find relevant
services and UI implementations beyond connector files. It does not load `.env`,
credentials, customer data, or execute/import the Jovis application. Source excerpts
are sent only to the existing Codex analysis call with web search disabled; public
research receives the positioning and queries, not the source code.

Coverage is static source evidence, not proof of a deployed or tested integration.
An unmet requirement is labeled supported, partial, not found in this inspection,
or unknown, with source references and next steps. MCP/plugin coverage must be
verified separately. This is a targeted inspection, not a complete codebase audit.

The list defaults to **Best product fit**, shows ten prospects per page, and opens
one review at a time. All prospects remain available through paging. **Conversation
signal** (formerly confidence) is a transparent ranking score, not purchase probability: personal pain
25 points, buyer-role evidence 20, product coverage 25, explicit solution request
15, recency 10, original-post access 5. Partial coverage earns half credit; needs
are equally weighted. Unknown dates, posts over 90 days old, snippet-only sources,
or missing personal pain cap the score at 59; uncertain buyers cap it at 49.
Review original dates, community rules, product gaps and the actual conversation
before introducing Jovis. No keyword search-volume claims are made.

Source failures, checks before outreach, and methodology notes appear separately
under **Research details**. Methodology notes alone do not make a completed run
partial. Source inspection, full complaints and product gaps load when requested;
the initial list uses `compact=true` API responses. While visible, the page polls
a small `/progress` response and refreshes summaries only when results change.
Polling pauses when the page is hidden or its tab is deactivated; research itself
continues. Status announcements remain outside busy regions.

### Suggested responses

New prospect analyses include a suggested public response in a concise solo-founder
voice, guided by approved comment preferences when available. Existing saved
prospects have a **Suggest reply** button, so drafting does not rerun discovery.
Replies answer the question first, disclose the founder relationship when mentioning
Jovis, and use the saved product coverage to avoid unsupported promises. They must
not invent personal experience, customer results, prices, or offers of free work.

Generated responses and edited drafts are saved separately from research so
background updates do not overwrite them. Edits autosave to SQLite and are kept
in browser local storage until acknowledged, allowing recovery after refresh or
a failed save. Saves are serialized per draft to prevent an older request from
overwriting a newer edit. Inline status shows failures and offers retry.

Regenerating an edited response keeps the user's draft and presents the generated
suggestion separately. **Previous versions** preserves generated and edited text;
restoring a version saves it without deleting other versions. Edits made while
generation is running are preserved. Copying announces success in a live region.
Nothing is posted or sent by these controls.

## Article Reader

Open **Articles**, paste an X/Twitter post link containing an article, and
click **Open**. The reader uses the installed Twitter CLI's authenticated
article client through an isolated Python bridge. It retains the raw rich content
before the CLI's text parser discards embedded media. It displays the full article,
cover and inline images in document order, author, publication date, reading time, and original
source link. It does not generate or summarize the author's text. A missing full
article produces an explicit error instead of substituting the post preview.

**Print / Save PDF** opens the browser print dialog. The printed view contains the
article and attribution, with app navigation and controls removed. Articles remain
one continuous reading page on screen and paginate naturally on paper. Headings,
lists, emphasis, code, tables and HTTPS images use print-aware styles. Printing waits
for article images to load and reports failed images before opening the dialog. Article
styles use a named print page so other app views retain their print settings.

A successful load creates a reusable `?article=<encoded-X-post-URL>` app link.
Reloading it opens the reader directly. Switching tabs keeps the loaded article;
the browser title follows the article while the reader is active, providing a useful
PDF filename. Loading a new article clears the old print target until the new
content is available.

Only HTTPS X/Twitter status links are accepted; queries and fragments are discarded
and only the numeric post ID reaches the CLI. Original article media is accepted only
from X's HTTPS image CDN. The server does not fetch arbitrary
URLs. Markdown rendering disables raw HTML and rejects executable link schemes;
the Markdown parser is loaded only with the reader tab. This feature requires an
installed Twitter CLI version that supports the `article` command and access to
the requested article through its current sign-in.
