<script setup>
import {
  computed,
  nextTick,
  onActivated,
  onDeactivated,
  onMounted,
  onUnmounted,
  reactive,
  ref,
  watch,
} from "vue";
import { ExternalLink, Search } from "@lucide/vue";
import { formatDate } from "../lib/format";
import {
  clearRecovery,
  draftKey,
  readRecovery,
  saveRecovery,
  sortProspects,
  isRedditPost,
  publicationBlocksPosting,
} from "../lib/prospects";

const run = ref(null);
const loading = ref(true);
const starting = ref(false);
const error = ref("");
const notice = ref("");
const copied = ref("");
const filter = ref("all");
const order = ref("fit");
const page = ref(1);
const pageSize = 10;
const expanded = ref("");
const reviewPageUrls = ref([]);
const details = ref({});
const detailLoading = ref({});
const drafts = ref({});
const saving = ref({});
const saveErrors = ref({});
const responseLoading = ref({});
const responseErrors = ref({});
const posting = ref({});
const postingErrors = ref({});
const versions = ref({});
const versionsLoading = ref({});
const research = ref(null);
const researchOpen = ref(false);
const researchLoading = ref(false);
const researchError = ref("");
const redditStatus = ref(null);
const searchStatus = ref(null);
const redditStatusLoading = ref(false);
const redditStatusError = ref("");
const resultsHeading = ref(null);
let active = false;
let disposed = false;
let timer;
let pollController;
let latestRequest = 0;
const saveTimers = reactive(new Map());
const saveRequests = new Map();

const running = computed(
  () => starting.value || run.value?.status === "running",
);
const publishing = computed(() => Object.values(posting.value).some(Boolean));
const allPosts = computed(() =>
  (run.value?.posts || []).filter(
    (post) => post.coverage_checked && Number(post.coverage) >= 45,
  ),
);
const sortedPosts = computed(() =>
  sortProspects(
    allPosts.value.filter(
      (p) => filter.value !== "ready" || p.recommendation === "Introduce Jovis",
    ),
    order.value,
  ),
);
const pageCount = computed(() =>
  Math.max(1, Math.ceil(sortedPosts.value.length / pageSize)),
);
const visiblePosts = computed(() =>
  expanded.value
    ? reviewPageUrls.value
        .map((url) => allPosts.value.find((post) => post.url === url))
        .filter(Boolean)
    : sortedPosts.value.slice(
        (page.value - 1) * pageSize,
        page.value * pageSize,
      ),
);
const searched = computed(() => run.value?.searched || 0);
const keyFor = (post) => draftKey(run.value.id, post.url);
const detailFor = (post) => details.value[keyFor(post)];
const publicationFor = (post) => detailFor(post)?.publication;
const textFor = (post) =>
  drafts.value[keyFor(post)] ??
  detailFor(post)?.draft_text ??
  detailFor(post)?.suggested_response ??
  "";
const hasDraft = (post) =>
  Object.hasOwn(drafts.value, keyFor(post)) ||
  Boolean(detailFor(post)?.suggested_response) ||
  typeof detailFor(post)?.draft_text === "string";
const hasNewSuggestion = (post) =>
  Boolean(
    detailFor(post)?.suggested_response &&
      textFor(post) !== detailFor(post).suggested_response,
  );
const postId = (post) => `prospect-${encodeURIComponent(post.url)}`;
const sourceLabel = (url) => new URL(url).hostname.replace("www.", "");
const postDate = (value) =>
  value
    ? new Intl.DateTimeFormat("en", {
        day: "numeric",
        month: "short",
        year: "numeric",
      }).format(new Date(value))
    : "Date unverified";
const statusLabels = {
  supported: "Supported in code",
  partial: "Partly supported",
  not_found: "Not found in inspection",
  unknown: "Needs verification",
};
const noticeLabels = {
  issues: "Source limitations",
  checks: "Checks before outreach",
  notes: "Methodology",
};

async function request(path, options) {
  const response = await fetch(path, options);
  const body = await response.json().catch(() => ({}));
  if (!response.ok)
    throw new Error(
      typeof body.detail === "string"
        ? body.detail
        : "Could not load customer research. Please retry.",
    );
  return body;
}

async function loadSearchStatus() {
  try {
    const status = await request("/api/prospects/sources/research/status");
    if (!disposed) searchStatus.value = status;
  } catch {
    if (!disposed) searchStatus.value = { configured: false, message: "Could not check public search configuration." };
  }
}

async function loadRedditStatus() {
  if (redditStatusLoading.value) return;
  redditStatusLoading.value = true;
  redditStatusError.value = "";
  try {
    const status = await request("/api/prospects/sources/reddit/status");
    if (!disposed) redditStatus.value = status;
  } catch {
    if (!disposed) redditStatusError.value = "Could not check Reddit connection. Research can still use web search.";
  } finally {
    if (!disposed) redditStatusLoading.value = false;
  }
}

function stopPolling() {
  clearTimeout(timer);
  pollController?.abort();
}

function schedulePoll() {
  clearTimeout(timer);
  if (
    active &&
    !document.hidden &&
    !disposed &&
    run.value?.status === "running"
  )
    timer = setTimeout(poll, 3000);
}

function updateRun(next) {
  if (run.value?.id !== next?.id) {
    expanded.value = "";
    page.value = 1;
    research.value = null;
    researchError.value = "";
  } else if (run.value?.revision !== next?.revision) research.value = null;
  run.value = next;
  if (researchOpen.value && !research.value) loadResearch();
}

async function loadLatest() {
  const serial = ++latestRequest;
  try {
    const body = await request("/api/prospects/runs/latest?compact=true");
    if (!disposed && active && serial === latestRequest) {
      updateRun(body.run);
      error.value = "";
    }
  } catch (failure) {
    if (!disposed && active) error.value = failure.message;
  } finally {
    if (!disposed) loading.value = false;
    schedulePoll();
  }
}

async function poll() {
  if (!active || document.hidden || !run.value) return;
  const runId = run.value.id;
  pollController = new AbortController();
  try {
    const progress = await request(`/api/prospects/runs/${runId}/progress`, {
      signal: pollController.signal,
    });
    if (!active || run.value?.id !== runId) return;
    if (progress.revision !== run.value.revision) {
      const next = await request(`/api/prospects/runs/${runId}?compact=true`, {
        signal: pollController.signal,
      });
      if (active && run.value?.id === runId) updateRun(next);
    } else Object.assign(run.value, progress);
    error.value = "";
  } catch (failure) {
    if (failure.name !== "AbortError" && active)
      error.value = `${failure.message} Research continues in the background.`;
  } finally {
    schedulePoll();
  }
}

async function start() {
  if (running.value || publishing.value) return;
  starting.value = true;
  error.value = "";
  ++latestRequest;
  try {
    await flushAll();
    const next = await request("/api/prospects/runs?compact=true", {
      method: "POST",
    });
    if (!disposed) {
      updateRun(next);
      filter.value = "all";
    }
  } catch (failure) {
    error.value = failure.message;
  } finally {
    starting.value = false;
    schedulePoll();
  }
}

async function review(post) {
  const key = keyFor(post);
  if (expanded.value === post.url) {
    await flushDraft(post);
    expanded.value = "";
    await nextTick();
    if (!visiblePosts.value.some((item) => item.url === post.url))
      resultsHeading.value?.focus();
    return;
  }
  reviewPageUrls.value = visiblePosts.value.map((item) => item.url);
  expanded.value = post.url;
  const runId = run.value.id;
  detailLoading.value[key] = true;
  responseErrors.value[key] = "";
  try {
    const body = await request(
      `/api/prospects/runs/${runId}/prospect?url=${encodeURIComponent(post.url)}`,
    );
    if (disposed || run.value?.id !== runId) return;
    details.value[key] = body;
    const recovered = readRecovery(window.localStorage, key);
    if (recovered !== null) {
      drafts.value[key] = recovered;
      await flushDraft(post);
    }
  } catch (failure) {
    responseErrors.value[key] = failure.message;
  } finally {
    detailLoading.value[key] = false;
  }
}

function edit(post, text) {
  const key = keyFor(post);
  drafts.value[key] = text;
  copied.value = "";
  saveErrors.value[key] = "";
  notice.value = "";
  try {
    saveRecovery(window.localStorage, key, text);
  } catch {
    saveErrors.value[key] =
      "Local recovery is unavailable. Keep this page open until the server save completes.";
  }
  clearTimeout(saveTimers.get(key));
  saveTimers.set(
    key,
    setTimeout(() => flushDraft(post), 600),
  );
}

async function flushDraft(post) {
  if (!run.value) return;
  const runId = run.value.id;
  const key = keyFor(post);
  clearTimeout(saveTimers.get(key));
  saveTimers.delete(key);
  while (saveRequests.has(key)) await saveRequests.get(key);
  if (!Object.hasOwn(drafts.value, key)) return;
  const text = drafts.value[key];
  if (details.value[key]?.draft_text === text && !saveErrors.value[key]) {
    try {
      clearRecovery(window.localStorage, key, text);
    } catch {
      /* The server already has this text. */
    }
    return;
  }
  saving.value[key] = true;
  const pending = (async () => {
    try {
      const reply = await request(`/api/prospects/runs/${runId}/draft`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url: post.url, text }),
      });
      Object.assign(details.value[key] || (details.value[key] = {}), reply);
      try {
        clearRecovery(window.localStorage, key, text);
      } catch {
        /* The server copy is durable. */
      }
      saveErrors.value[key] = "";
      if (versions.value[key]) await loadVersions(post);
    } catch (failure) {
      let recoverable = false;
      try {
        recoverable =
          readRecovery(window.localStorage, key) === drafts.value[key];
      } catch {
        /* Storage may be blocked. */
      }
      saveErrors.value[key] =
        `${failure.message} ${recoverable ? "Your browser recovery copy is kept. Retry saving before leaving this device." : "Keep this tab open; this edit is not saved yet. Copy it before leaving."}`;
    } finally {
      saving.value[key] = false;
    }
  })();
  saveRequests.set(key, pending);
  await pending;
  if (saveRequests.get(key) === pending) saveRequests.delete(key);
  if (run.value?.id === runId && drafts.value[key] !== text)
    await flushDraft(post);
}

async function flushAll() {
  await Promise.all(
    allPosts.value
      .filter((post) => Object.hasOwn(drafts.value, keyFor(post)))
      .map(flushDraft),
  );
}

async function generate(post) {
  const key = keyFor(post);
  const runId = run.value.id;
  if (responseLoading.value[key]) return;
  responseLoading.value[key] = true;
  copied.value = "";
  responseErrors.value[key] = "";
  try {
    await flushDraft(post);
    if (saveErrors.value[key])
      throw new Error(
        "Save your edits before regenerating. Use Retry save below.",
      );
    const startingText = textFor(post);
    const reply = await request(`/api/prospects/runs/${runId}/response`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url: post.url }),
    });
    if (!disposed && run.value?.id === runId) {
      const current = textFor(post);
      const editedDuringGeneration = current !== startingText;
      Object.assign(details.value[key], reply);
      if (!editedDuringGeneration) drafts.value[key] = reply.draft_text;
      if (versions.value[key]) await loadVersions(post);
      post.has_response = true;
      notice.value = `Response ready for ${post.title}. ${hasNewSuggestion(post) ? "Your edited draft is kept; review the new suggestion below." : "Review it before posting."}`;
    }
  } catch (failure) {
    responseErrors.value[key] = failure.message;
  } finally {
    responseLoading.value[key] = false;
  }
}

async function copy(post) {
  try {
    await navigator.clipboard.writeText(textFor(post));
    copied.value = keyFor(post);
    notice.value = `Response copied for ${post.title}.`;
  } catch {
    responseErrors.value[keyFor(post)] =
      "Could not copy. Select the response and copy it manually.";
  }
}

async function postReply(post) {
  const key = keyFor(post);
  const runId = run.value.id;
  if (posting.value[key] || publicationBlocksPosting(publicationFor(post))) return;
  const text = textFor(post);
  posting.value[key] = true;
  postingErrors.value[key] = "";
  try {
    await flushDraft(post);
    if (saveErrors.value[key]) throw new Error("Save your reply before posting. Use Retry save below.");
    if (text !== textFor(post)) throw new Error("Your reply changed while saving. Review it before posting.");
    const publication = await request(`/api/prospects/runs/${runId}/publish`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({url: post.url, text, username: redditStatus.value?.username || ""}),
    });
    if (!disposed && run.value?.id === runId) {
      details.value[key].publication = publication;
      notice.value = publication.message;
    }
  } catch (failure) {
    postingErrors.value[key] = failure.message;
    // An interrupted HTTP response may hide a successful post. Re-read durable
    // server state before enabling any retry, even if the editor remains open.
    try {
      const body = await request(`/api/prospects/runs/${runId}/prospect?url=${encodeURIComponent(post.url)}`);
      if (!disposed && run.value?.id === runId) details.value[key].publication = body.publication;
    } catch {
      if (!disposed && run.value?.id === runId) details.value[key].publication = {
        status: "uncertain", message: "Posting could not be confirmed. Check Reddit before posting again.",
      };
    }
  } finally {
    posting.value[key] = false;
  }
}

async function loadVersions(post) {
  const key = keyFor(post);
  versionsLoading.value[key] = true;
  try {
    versions.value[key] = (
      await request(
        `/api/prospects/runs/${run.value.id}/versions?url=${encodeURIComponent(post.url)}`,
      )
    ).versions;
  } catch (failure) {
    responseErrors.value[key] = failure.message;
  } finally {
    versionsLoading.value[key] = false;
  }
}

async function restore(post, text) {
  edit(post, text);
  await flushDraft(post);
  if (!saveErrors.value[keyFor(post)])
    notice.value = `Draft restored for ${post.title}.`;
}

async function loadResearch() {
  if (research.value || researchLoading.value || !run.value) return;
  const runId = run.value.id;
  researchLoading.value = true;
  researchError.value = "";
  try {
    const body = await request(`/api/prospects/runs/${runId}/research`);
    if (run.value?.id === runId) research.value = body;
  } catch (failure) {
    researchError.value = failure.message;
  } finally {
    researchLoading.value = false;
    if (run.value?.id !== runId && researchOpen.value && !research.value)
      loadResearch();
  }
}

async function changePage(value) {
  await flushAll();
  page.value = Math.max(1, Math.min(pageCount.value, value));
  expanded.value = "";
  await nextTick();
  resultsHeading.value?.focus({ preventScroll: true });
  resultsHeading.value?.scrollIntoView({ block: "start" });
}

function activate() {
  if (active) return;
  active = true;
  loadSearchStatus();
  if (!document.hidden) loadLatest();
}
function deactivate() {
  active = false;
  ++latestRequest;
  stopPolling();
  flushAll();
}
function visibilityChanged() {
  if (document.hidden) {
    stopPolling();
    flushAll();
  } else if (active) loadLatest();
}
watch([filter, order], () => {
  page.value = 1;
  expanded.value = "";
  flushAll();
  notice.value = `${sortedPosts.value.length} conversations shown.`;
});
watch(pageCount, (count) => {
  if (page.value > count) page.value = count;
});
onMounted(() => {
  document.addEventListener("visibilitychange", visibilityChanged);
  activate();
});
onActivated(activate);
onDeactivated(deactivate);
onUnmounted(() => {
  deactivate();
  disposed = true;
  document.removeEventListener("visibilitychange", visibilityChanged);
  for (const t of saveTimers.values()) clearTimeout(t);
});
</script>

<template>
  <main class="prospects-page" aria-labelledby="prospects-title">
    <header class="prospects-heading">
      <div><h2 id="prospects-title">Customers</h2></div>
      <button
        class="button button-primary"
        type="button"
        :disabled="running || loading || publishing"
        @click="start"
      >
        <Search :size="16" aria-hidden="true" />{{
          running ? "Searching…" : "Find customers"
        }}
      </button>
    </header>
    <section class="reddit-connection" aria-label="Research sources">
      <div class="reddit-connection-heading">
        <p role="status" aria-live="polite">
          <strong>Public research</strong> · {{ searchStatus?.message || "Checking search configuration…" }}
        </p>
        <button class="button button-quiet" type="button" @click="loadSearchStatus">Refresh search status</button>
      </div>
      <details v-if="searchStatus?.communities?.length">
        <summary>Additional communities ({{ searchStatus.communities.length }})</summary>
        <ul class="source-directory">
          <li v-for="source in searchStatus.communities" :key="source.url">
            <a :href="source.url" target="_blank" rel="noopener noreferrer">{{ source.name }}</a>
          </li>
        </ul>
        <p class="muted">Five sites are searched together per problem query, rotating across all 20 communities. Index coverage varies; a search does not guarantee results from every site.</p>
      </details>
      <details>
        <summary>Optional Reddit posting account</summary>
        <p class="muted">Research uses Exa and public Hacker News search. Checking a posting account uses your signed-in Chrome session only when you click the button below.</p>
        <button class="button" type="button" :disabled="redditStatusLoading" @click="loadRedditStatus">Check Reddit posting account</button>
        <p v-if="redditStatus || redditStatusError" class="muted">{{ redditStatusError || redditStatus?.message }} <span v-if="redditStatus?.username">(u/{{ redditStatus.username }})</span></p>
      </details>
    </section>
    <p v-if="error" role="alert" class="error-notice">
      {{ error }}
      <button type="button" class="button button-quiet" @click="loadLatest">
        Retry connection
      </button>
    </p>
    <!-- Announcements remain outside every busy region. -->
    <p class="sr-only" role="status" aria-live="polite" aria-atomic="true">
      {{ notice }}
    </p>
    <p class="sr-only" role="status" aria-live="polite" aria-atomic="true">
      {{ running ? run?.stage : "" }}
    </p>
    <div v-if="run" class="research-status">
      <p v-if="running">{{ run.stage }}</p>
      <p v-else>
        {{
          run.status === "failed"
            ? "Research could not finish"
            : run.status === "interrupted"
              ? "Research interrupted; completed results kept"
              : "Research complete"
        }}
        <span class="muted"
          >· {{ searched }}/{{ run.total_queries }} searches<span
            class="status-date"
          >
            · {{ formatDate(run.completed_at || run.started_at) }}</span
          ></span
        >
      </p>
      <progress
        v-if="running"
        :value="run.attempted"
        :max="run.total_queries"
        aria-label="Search progress"
      ></progress>
      <p v-if="run.error" role="alert" class="error-text">{{ run.error }}</p>
    </div>

    <section aria-labelledby="prospects-results-heading">
      <div class="results-toolbar">
        <h3 id="prospects-results-heading" ref="resultsHeading" tabindex="-1">
          {{
            loading
              ? "Loading conversations…"
              : `${sortedPosts.length} conversations`
          }}
        </h3>
        <div class="result-controls">
          <label
            ><span class="sr-only">Show</span
            ><select v-model="filter" aria-label="Show prospects">
              <option value="all">45%+ product fit</option>
              <option value="ready">Ready to introduce</option>
            </select></label
          >
          <label
            ><span class="sr-only">Sort</span
            ><select v-model="order" aria-label="Sort prospects">
              <option value="fit">Best product fit</option>
              <option value="signal">Conversation signal</option>
              <option value="newest">Newest first</option>
            </select></label
          >
        </div>
      </div>
      <div v-if="loading" class="loading-state" aria-busy="true">
        <p>Loading saved research…</p>
      </div>
      <article
        v-for="post in visiblePosts"
        :key="post.url"
        class="prospect-row"
        :aria-labelledby="`${postId(post)}-title`"
      >
        <div class="prospect-summary">
          <div class="prospect-main">
            <p class="prospect-meta">
              {{ sourceLabel(post.url)
              }}<template v-if="post.author"> · {{ post.author }}</template> ·
              {{ postDate(post.published_at) }}
              <template v-if="post.collection_source === 'reddit_cli'"> · Reddit CLI (saved run)</template>
              <template v-if="post.collection_source === 'exa'"> · Exa excerpt</template>
              <template v-if="post.collection_source === 'exa_community'"> · Public community excerpt</template>
              <template v-if="post.collection_source === 'hn_algolia'"> · Hacker News public search</template>
              <template v-else-if="post.collection_source === 'web_fallback'"> · Web fallback</template>
            </p>
            <h4 :id="`${postId(post)}-title`" class="prospect-title">
              <a :href="post.url" target="_blank" rel="noopener noreferrer"
                >{{ post.title }}
                <ExternalLink
                  :size="14"
                  class="inline"
                  aria-hidden="true"
                /><span class="sr-only"> (opens in a new tab)</span></a
              >
            </h4>
            <p v-if="expanded !== post.url" class="quote-preview">
              {{ post.quote_preview }}
            </p>
          </div>
          <div class="prospect-actions">
            <p class="fit-metric">
              {{
                post.coverage_checked
                  ? `${post.coverage}% product fit`
                  : "Fit unverified"
              }}
            </p>
            <p class="signal-metric">
              Conversation signal {{ post.confidence }}/100
            </p>
            <button
              :id="`${postId(post)}-review`"
              class="button"
              type="button"
              :aria-expanded="expanded === post.url"
              :aria-controls="`${postId(post)}-detail`"
              :aria-label="`${expanded === post.url ? 'Close review of' : 'Review and reply to'} ${post.title}`"
              @click="review(post)"
            >
              {{ expanded === post.url ? "Close review" : "Review & reply" }}
            </button>
          </div>
        </div>
        <div
          v-if="expanded === post.url"
          :id="`${postId(post)}-detail`"
          class="prospect-detail"
        >
          <p v-if="detailLoading[keyFor(post)]" role="status">
            Loading this conversation…
          </p>
          <template v-else-if="detailFor(post)">
            <p class="recommendation">
              {{ post.recommendation }}
              <span
                v-if="detailFor(post).evidence_kind !== 'full_post'"
                class="muted"
                >· Search snippet only</span
              >
            </p>
            <blockquote>
              {{ detailFor(post).quote?.replace(/^>\s*/, "") }}
            </blockquote>
            <p>{{ detailFor(post).summary }}</p>
            <p v-if="detailFor(post).date_note" class="muted">
              Date check: {{ detailFor(post).date_note }}
            </p>
            <details class="fit-details">
              <summary>
                Product fit and gaps ·
                {{ detailFor(post).requirements.length }} needs checked
              </summary>
              <p v-if="!detailFor(post).requirements.length">
                Coverage has not been assessed. Verify the needs before
                introducing Jovis.
              </p>
              <ul class="requirements">
                <li v-for="(need, i) in detailFor(post).requirements" :key="i">
                  <div class="need-heading">
                    <strong>{{ need.need }}</strong
                    ><span
                      :class="
                        need.status === 'supported'
                          ? 'supported'
                          : 'needs-check'
                      "
                      >{{ statusLabels[need.status] }}</span
                    >
                  </div>
                  <p>{{ need.explanation }}</p>
                  <p v-if="need.next_step">
                    <strong>Next:</strong> {{ need.next_step }}
                  </p>
                  <details
                    v-for="id in need.evidence_ids"
                    :key="id"
                    class="code-evidence"
                  >
                    <summary>
                      Code evidence:
                      {{
                        detailFor(post).code_evidence.find((e) => e.id === id)
                          ?.path
                      }}:{{
                        detailFor(post).code_evidence.find((e) => e.id === id)
                          ?.line
                      }}
                    </summary>
                    <pre>{{
                      detailFor(post).code_evidence.find((e) => e.id === id)
                        ?.excerpt
                    }}</pre>
                  </details>
                </li>
              </ul>
            </details>
            <p v-if="detailFor(post).next_action">
              <strong>Next step:</strong> {{ detailFor(post).next_action }}
            </p>
            <div class="response-editor">
              <div class="editor-heading">
                <h5>Reply</h5>
                <button v-if="!hasDraft(post)" class="button button-quiet" type="button" @click="edit(post, '')">Write a reply</button>
                <button
                  class="button"
                  type="button"
                  :disabled="responseLoading[keyFor(post)] || posting[keyFor(post)]"
                  :aria-label="`${hasDraft(post) ? 'Regenerate response to' : 'Suggest a response to'} ${post.title}`"
                  @click="generate(post)"
                >
                  {{
                    responseLoading[keyFor(post)]
                      ? "Writing response…"
                      : hasDraft(post)
                        ? "Regenerate"
                        : "Suggest reply"
                  }}
                </button>
              </div>
              <p v-if="responseLoading[keyFor(post)]" role="status">
                Writing a useful reply. Your edits will be kept.
              </p>
              <template v-if="hasDraft(post)">
                <label class="sr-only" :for="`${postId(post)}-draft`"
                  >Your reply</label
                >
                <textarea
                  :id="`${postId(post)}-draft`"
                  :value="textFor(post)"
                  :aria-label="`Your reply to ${post.title}`"
                  rows="6"
                  :readonly="posting[keyFor(post)]"
                  @input="edit(post, $event.target.value)"
                  @blur="flushDraft(post)"
                ></textarea>
                <div class="editor-footer">
                  <p
                    class="save-state"
                    :class="{ 'error-text': saveErrors[keyFor(post)] }"
                    :role="saveErrors[keyFor(post)] ? 'alert' : undefined"
                  >
                    {{
                      saving[keyFor(post)] || saveTimers.has(keyFor(post))
                        ? "Saving draft…"
                        : saveErrors[keyFor(post)]
                          ? saveErrors[keyFor(post)]
                          : "Saved"
                    }}
                  </p>
                  <button
                    class="button"
                    type="button"
                    :disabled="!textFor(post).trim()"
                    :aria-label="`${copied === keyFor(post) ? 'Response copied for' : 'Copy response to'} ${post.title}`"
                    @click="copy(post)"
                  >
                    {{ copied === keyFor(post) ? "Copied" : "Copy" }}
                  </button>
                </div>
                <section v-if="isRedditPost(post.url)" class="reply-publication" aria-label="Post reply on Reddit">
                  <template v-if="publicationFor(post)">
                    <p role="status" aria-live="polite">{{ publicationFor(post).message }}</p>
                    <a v-if="publicationFor(post).status === 'posted' && publicationFor(post).comment_url"
                      :href="publicationFor(post).comment_url" target="_blank" rel="noopener noreferrer">View posted reply on Reddit</a>
                    <a v-else-if="publicationBlocksPosting(publicationFor(post))"
                      :href="post.url" target="_blank" rel="noopener noreferrer">Check the thread on Reddit</a>
                    <details v-if="publicationFor(post).status === 'posted' && publicationFor(post).text !== textFor(post)">
                      <summary>Reply that was posted</summary>
                      <p class="published-text">{{ publicationFor(post).text }}</p>
                    </details>
                  </template>
                  <div v-if="!publicationBlocksPosting(publicationFor(post))" class="editor-footer">
                    <p class="muted" v-if="redditStatus?.authenticated && redditStatus?.username">
                      Posts publicly as u/{{ redditStatus.username }}.
                    </p>
                    <p class="muted" v-else>Connect Reddit above to post this reply.</p>
                    <button type="button" class="button button-primary"
                      :disabled="posting[keyFor(post)] || responseLoading[keyFor(post)] || !redditStatus?.authenticated || !redditStatus?.username || !textFor(post).trim() || textFor(post).length > 10000"
                      :aria-label="`Post reply on Reddit to ${post.title}`" @click="postReply(post)">
                      {{ posting[keyFor(post)] ? "Posting…" : "Post on Reddit" }}
                    </button>
                  </div>
                  <p v-if="textFor(post).length > 10000" class="error-text">Shorten this reply to 10,000 characters before posting.</p>
                  <p v-if="postingErrors[keyFor(post)]" role="alert" class="error-text">{{ postingErrors[keyFor(post)] }}</p>
                </section>
                <button
                  v-if="saveErrors[keyFor(post)]"
                  class="button button-quiet"
                  type="button"
                  @click="flushDraft(post)"
                >
                  Retry save
                </button>
                <details v-if="hasNewSuggestion(post)" class="new-suggestion">
                  <summary>
                    Generated suggestion; your edited draft is kept
                  </summary>
                  <p>{{ detailFor(post).suggested_response }}</p>
                  <button
                    class="button"
                    type="button"
                    :aria-label="`Use the generated suggestion for ${post.title}`"
                    @click="restore(post, detailFor(post).suggested_response)"
                  >
                    Use suggestion
                  </button>
                </details>
                <p v-if="detailFor(post).response_note" class="needs-check">
                  Before posting: {{ detailFor(post).response_note }}
                </p>
                <details
                  class="draft-history"
                  @toggle="$event.target.open && loadVersions(post)"
                >
                  <summary>Previous versions</summary>
                  <p v-if="versionsLoading[keyFor(post)]">Loading versions…</p>
                  <ul v-else class="versions">
                    <li
                      v-for="version in versions[keyFor(post)] || []"
                      :key="version.id"
                    >
                      <p class="muted">
                        {{ formatDate(version.saved_at) }} · {{ version.kind }}
                      </p>
                      <p>{{ version.text || "(Empty draft)" }}</p>
                      <button
                        class="button button-quiet"
                        type="button"
                        :disabled="version.text === textFor(post)"
                        :aria-label="`Restore response version ${version.id} for ${post.title}`"
                        @click="restore(post, version.text)"
                      >
                        Restore this version
                      </button>
                    </li>
                  </ul>
                  <p
                    v-if="
                      !versionsLoading[keyFor(post)] &&
                      !versions[keyFor(post)]?.length
                    "
                  >
                    Versions will appear as you edit or regenerate.
                  </p>
                </details>
              </template>
            </div>
            <details>
              <summary>Conversation signal breakdown</summary>
              <dl class="score-factors">
                <div
                  v-for="(points, name) in detailFor(post).confidence_factors"
                  :key="name"
                >
                  <dt>{{ name }}</dt>
                  <dd>{{ points }} points</dd>
                </div>
              </dl>
            </details>
            <details v-if="detailFor(post).caveats?.length">
              <summary>Checks for this conversation</summary>
              <ul class="caveats">
                <li v-for="(item, i) in detailFor(post).caveats" :key="i">
                  {{ item }}
                </li>
              </ul>
            </details>
          </template>
          <p
            v-if="responseErrors[keyFor(post)]"
            role="alert"
            class="error-text"
          >
            {{ responseErrors[keyFor(post)] }}
            <button
              v-if="!detailFor(post)"
              class="button button-quiet"
              type="button"
              @click="
                expanded = '';
                review(post);
              "
            >
              Retry loading
            </button>
          </p>
        </div>
      </article>
      <div v-if="!loading && !visiblePosts.length" class="empty-state">
        <h4>
          {{
            running
              ? "Looking for useful conversations"
              : allPosts.length
                ? "No prospects are ready for an introduction yet"
                : run
                  ? "No conversations with at least 45% product fit"
                  : "No conversations yet"
          }}
        </h4>
      </div>
      <nav
        v-if="pageCount > 1"
        class="pagination"
        aria-label="Prospect result pages"
      >
        <button
          class="button"
          type="button"
          :disabled="page === 1"
          @click="changePage(page - 1)"
        >
          Previous
        </button>
        <p aria-live="polite">
          {{ (page - 1) * pageSize + 1 }}–{{
            Math.min(page * pageSize, sortedPosts.length)
          }}
          of {{ sortedPosts.length }}
        </p>
        <button
          class="button"
          type="button"
          :disabled="page === pageCount"
          @click="changePage(page + 1)"
        >
          Next
        </button>
      </nav>
    </section>

    <details
      v-if="run"
      :open="researchOpen"
      class="research-details"
      @toggle="
        researchOpen = $event.target.open;
        researchOpen && loadResearch();
      "
    >
      <summary>
        Research details<span v-if="run.notices.issues.length" class="muted">
          · {{ run.notices.issues.length }} limitations</span
        >
      </summary>
      <p v-if="researchLoading">Loading research details…</p>
      <p v-if="researchError" role="alert" class="error-text">
        {{ researchError }}
        <button class="button button-quiet" type="button" @click="loadResearch">
          Retry research details
        </button>
      </p>
      <template v-if="research">
        <section v-for="(items, group) in research.notices" :key="group">
          <h4 v-if="items.length">{{ noticeLabels[group] }}</h4>
          <ul v-if="items.length" class="caveats">
            <li v-for="(item, i) in items" :key="i">{{ item }}</li>
          </ul>
        </section>
        <details>
          <summary>20 search queries · {{ searched }} confirmed</summary>
          <ol class="queries">
            <li v-for="(item, i) in research.queries" :key="item.query">
              <strong>{{ i + 1 }}. {{ item.query }}</strong>
              <p class="muted">{{ item.theme }} · {{ item.status }}</p>
              <p>{{ item.finding }}</p>
              <p v-if="item.reddit" class="muted">
                Reddit ({{ item.reddit.provider || "legacy CLI" }}): {{ item.reddit.status }} · {{ item.reddit.result_count }} results ·
                {{ item.reddit.inspected_count }} posts inspected.
                <template v-if="item.reddit.web_fallback !== 'not_needed'"> Web fallback: {{ item.reddit.web_fallback }}.</template>
              </p>
              <p v-if="item.reddit?.error" class="muted">{{ item.reddit.error }}</p>
              <p v-if="!item.reddit" class="muted">Reddit search coverage: not recorded.</p>
              <p v-if="item.hackernews" class="muted">Hacker News public search: {{ item.hackernews.status }} · {{ item.hackernews.result_count }} results · {{ item.hackernews.inspected_count }} excerpts inspected.</p>
              <p v-if="item.hackernews?.error" class="muted">{{ item.hackernews.error }}</p>
              <p v-if="item.communities" class="muted">Community search: {{ item.communities.status }} · {{ item.communities.result_count }} excerpts · {{ item.communities.inspected_count }} inspected.</p>
              <p v-if="item.communities?.domains" class="muted">Sites queried together: {{ item.communities.domains.join(", ") }}.</p>
              <p v-if="item.communities?.error" class="muted">{{ item.communities.error }}</p>
            </li>
          </ol>
        </details>
        <details v-if="research.source_snapshot.fingerprint">
          <summary>
            Jovis code inspection ·
            {{ research.source_snapshot.evidence_count }} excerpts
          </summary>
          <p>{{ research.source_snapshot.scope }}</p>
          <p class="muted">
            Inspected {{ formatDate(research.source_snapshot.inspected_at) }} ·
            {{
              research.source_snapshot.semantic_search_count
            }}
            complaint-specific searches
          </p>
          <p class="muted">
            Source fingerprint
            {{ research.source_snapshot.fingerprint.slice(0, 12) }}
          </p>
          <p>
            Connector files:
            {{ research.source_snapshot.provider_files?.join(", ") }}
          </p>
        </details>
        <details>
          <summary>How ranking works</summary>
          <p>
            Product fit is the share of identified needs supported in code, with
            half credit for partial support. It does not prove deployment
            readiness. Conversation signal combines personal pain (25), buyer
            evidence (20), product coverage (25), asking for a solution (15),
            recency (10), and source access (5). Unverified dates, older posts
            and snippet-only sources cap the signal at 59. Uncertain buyers cap
            it at 49. Neither score predicts purchase.
          </p>
        </details>
        <p class="muted">
          Research runs 20 problem queries across X, Reddit, Hacker News and 20 additional public communities, limited to the last 48 hours. A full pass can take 10–30 minutes. Nothing is posted or sent.
        </p>
      </template>
    </details>
  </main>
</template>

<style scoped>
.source-directory {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(min(100%, 15rem), 1fr));
  gap: 0.5rem 1.5rem;
  padding-block: 0.75rem;
  font-size: 0.875rem;
}
.source-directory a { text-decoration: underline; text-underline-offset: 3px; }

.prospects-page {
  font-size: 1rem;
  line-height: 1.6;
  padding-block: 1.5rem 3rem;
  color: var(--ink);
}
.prospects-heading,
.results-toolbar,
.result-controls,
.editor-heading,
.editor-footer,
.need-heading,
.pagination {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
  flex-wrap: wrap;
}
.prospects-heading {
  align-items: start;
  margin-bottom: 1rem;
}
.prospects-heading h2 {
  font-size: 1.5rem;
  font-weight: 600;
  line-height: 1.25;
}
.muted,
.prospect-meta,
.signal-metric,
.save-state {
  color: var(--muted);
  font-size: 0.875rem;
}
.research-status {
  padding-block: 0.25rem 0.8rem;
  font-size: 0.875rem;
}
.reddit-connection {
  margin-bottom: 1rem;
  padding-block: 0.5rem 0.8rem;
  border-bottom: 1px solid var(--rule);
  font-size: 0.875rem;
  overflow-wrap: anywhere;
}
.reddit-connection-heading {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 0.5rem;
}
.reddit-connection details p {
  margin-top: 0.5rem;
  max-width: 75ch;
}
.research-status progress {
  display: block;
  width: 100%;
  height: 0.5rem;
  margin-top: 0.6rem;
  accent-color: var(--accent);
}
.results-toolbar {
  border-top: 1px solid var(--rule);
  padding-top: 1rem;
}
.results-toolbar h3 {
  font-size: 1rem;
  font-weight: 650;
}
.result-controls {
  gap: 1rem;
}
.result-controls label {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-size: 0.875rem;
}
select {
  min-height: 44px;
  padding: 0.5rem 0.8rem;
  font-size: 0.875rem;
  width: auto;
  border: 1px solid var(--rule-strong);
  background: var(--paper);
}
.prospect-row {
  border-top: 1px solid var(--rule);
  padding-block: 1.15rem;
  overflow-wrap: anywhere;
}
.prospect-summary {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 1.5rem;
  align-items: start;
}
.prospect-main {
  min-width: 0;
}
.prospect-meta {
  margin-bottom: 0.35rem;
}
.prospect-title {
  font-size: 1.0625rem;
  line-height: 1.45;
  font-weight: 600;
}
.prospect-title a {
  text-decoration: underline;
  text-decoration-color: var(--rule-strong);
  text-underline-offset: 3px;
}
.prospect-title a:hover {
  color: var(--accent);
}
.quote-preview {
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  max-width: 75ch;
  margin-top: 0.5rem;
  font-size: 0.9375rem;
  color: var(--muted);
}
.prospect-actions {
  display: grid;
  gap: 0.2rem;
  justify-items: end;
}
.fit-metric {
  font-size: 1rem;
  font-weight: 650;
  white-space: nowrap;
}
.signal-metric {
  white-space: nowrap;
}
.prospect-actions button {
  margin-top: 0.4rem;
}
.prospect-detail {
  margin-top: 1.25rem;
  border-top: 1px solid var(--rule);
  padding-top: 1rem;
}
.prospect-detail > p,
.prospect-detail blockquote {
  max-width: 75ch;
  margin-bottom: 0.8rem;
}
.recommendation {
  font-weight: 600;
}
blockquote {
  padding: 0.85rem 1rem;
  background: var(--paper-shade);
  border-radius: 3px;
}
summary {
  cursor: pointer;
  min-height: 44px;
  padding-block: 0.65rem;
  line-height: 1.5;
  overflow-wrap: anywhere;
}
summary:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: 3px;
}
details > p {
  max-width: 75ch;
  margin-block: 0.5rem;
}
.requirements {
  display: grid;
  gap: 1rem;
  margin-block: 0.5rem 1rem;
}
.requirements > li {
  padding-top: 0.75rem;
  border-top: 1px solid var(--rule);
}
.requirements p {
  margin-top: 0.4rem;
  max-width: 75ch;
}
.need-heading {
  align-items: start;
}
.supported {
  color: var(--success);
}
.needs-check {
  color: var(--warning);
}
.code-evidence {
  font-size: 0.875rem;
}
pre {
  max-height: 20rem;
  overflow: auto;
  padding: 1rem;
  background: var(--paper-shade);
  font-family: ui-monospace, monospace;
  font-size: 0.8125rem;
  line-height: 1.6;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}
.response-editor {
  margin-block: 1rem;
  padding-top: 1rem;
  border-top: 1px solid var(--rule);
}
.reply-publication {
  border-top: 1px solid var(--rule);
  padding-top: 0.8rem;
  margin-top: 0.8rem;
}
.reply-publication a {
  text-decoration: underline;
  text-underline-offset: 3px;
}
.published-text {
  white-space: pre-wrap;
}
.editor-heading h5 {
  font-size: 1rem;
  font-weight: 650;
}
textarea {
  width: 100%;
  padding: 0.8rem;
  border: 1px solid var(--rule-strong);
  border-radius: 3px;
  background: var(--paper);
  font-size: 1rem;
  line-height: 1.6;
}
.editor-footer {
  margin-block: 0.5rem;
}
.save-state {
  max-width: 65ch;
}
.new-suggestion {
  margin-block: 1rem;
  padding: 0.5rem 1rem;
  border: 1px solid var(--rule-strong);
}
.versions {
  display: grid;
  gap: 1rem;
}
.versions li {
  border-top: 1px solid var(--rule);
  padding-top: 0.75rem;
}
.versions li > p {
  max-width: 75ch;
  white-space: pre-wrap;
}
.score-factors {
  max-width: 32rem;
}
.score-factors > div {
  display: flex;
  justify-content: space-between;
  gap: 1rem;
  padding-block: 0.25rem;
}
.caveats {
  list-style: disc;
  padding-left: 1.3rem;
}
.caveats li {
  margin-block: 0.5rem;
  max-width: 75ch;
}
.error-notice {
  border: 1px solid var(--danger-rule);
  padding: 0.75rem 1rem;
  background: var(--danger-wash);
  margin-bottom: 1rem;
}
.error-text,
.error-notice {
  color: var(--danger);
}
.empty-state,
.loading-state {
  border-block: 1px solid var(--rule);
  padding-block: 2rem;
}
.empty-state h4 {
  font-weight: 600;
}
.empty-state p {
  margin-top: 0.5rem;
  max-width: 65ch;
}
.pagination {
  justify-content: center;
  padding-block: 1rem;
  border-top: 1px solid var(--rule);
  font-size: 0.875rem;
}
.research-details {
  border-top: 1px solid var(--rule);
  margin-top: 1.5rem;
  padding-top: 0.5rem;
}
.research-details > section h4 {
  font-weight: 650;
  margin-top: 1rem;
}
.queries {
  display: grid;
  gap: 1rem;
  margin-block: 1rem;
}
@media (max-width: 639px) {
  .prospects-page {
    padding-top: 1rem;
  }
  .prospects-heading {
    gap: 0.6rem;
  }
  .prospects-heading h2 {
    font-size: 1.5rem;
  }
  .status-date {
    display: none;
  }
  .prospects-heading > div {
    width: 100%;
  }
  .results-toolbar {
    gap: 0.5rem;
  }
  .result-controls {
    width: 100%;
    gap: 0.5rem;
    display: grid;
    grid-template-columns: 1fr 1fr;
  }
  .result-controls label {
    display: grid;
    gap: 0.2rem;
  }
  .result-controls select {
    width: 100%;
    min-width: 0;
    padding-inline: 0.4rem;
  }
  .prospect-summary {
    grid-template-columns: minmax(0, 1fr);
    gap: 0.6rem;
  }
  .prospect-actions {
    display: flex;
    align-items: center;
    justify-content: space-between;
    flex-wrap: wrap;
    gap: 0.3rem 0.75rem;
  }
  .fit-metric {
    font-size: 0.9375rem;
  }
  .signal-metric {
    font-size: 0.875rem;
  }
  .prospect-actions button {
    margin-top: 0;
  }
  .editor-heading,
  .editor-footer {
    align-items: start;
  }
  .research-status {
    padding-bottom: 0.5rem;
  }
}
</style>
