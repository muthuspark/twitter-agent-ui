<script setup>
import { computed, onMounted, onUnmounted, ref } from "vue";
import { AlertCircle, ExternalLink, Search } from "@lucide/vue";
import { formatDate } from "../lib/workbench";

const run = ref(null);
const starting = ref(false);
const error = ref("");
const filter = ref("all");
const drafts = ref({});
const responseLoading = ref({});
const responseErrors = ref({});
const copied = ref("");
let timer;
let disposed = false;
const running = computed(() => starting.value || run.value?.status === "running");
const searched = computed(() => run.value?.queries.filter(q => q.status === "searched").length || 0);
const attempted = computed(() => run.value?.queries.filter(q => q.status !== "pending").length || 0);
const posts = computed(() => (run.value?.posts || []).filter(post => filter.value !== "introduce" || post.recommendation === "Introduce Jovis"));
const evidence = computed(() => Object.fromEntries((run.value?.source_snapshot?.evidence || []).map(item => [item.id, item])));
const statusLabels = { supported: "Supported in code", partial: "Partly supported", not_found: "Not found in inspection", unknown: "Needs verification" };
const sourceLabel = url => new URL(url).hostname.replace("www.", "");
const replyKey = post => `${run.value.id}:${post.url}`;
const responseText = post => drafts.value[replyKey(post)] ?? post.suggested_response ?? "";
const hasResponse = post => Object.hasOwn(drafts.value, replyKey(post)) || Boolean(post.suggested_response);

async function generateResponse(post) {
  const key = replyKey(post);
  const runId = run.value.id;
  if (responseLoading.value[key]) return;
  responseLoading.value[key] = true;
  responseErrors.value[key] = "";
  try {
    const reply = await request(`/api/prospects/runs/${runId}/response`, {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ url: post.url }),
    });
    if (!disposed && run.value?.id === runId) {
      Object.assign(post, reply);
      drafts.value[key] = reply.suggested_response;
    }
  } catch (failure) {
    if (!disposed) responseErrors.value[key] = failure.message;
  } finally {
    responseLoading.value[key] = false;
  }
}

async function copyResponse(post) {
  const key = replyKey(post);
  try {
    await navigator.clipboard.writeText(responseText(post));
    copied.value = key;
    responseErrors.value[key] = "";
  } catch {
    responseErrors.value[key] = "Could not copy. Select the response and copy it manually.";
  }
}

async function request(path, options) {
  const response = await fetch(path, options);
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(body.detail || "Could not load customer research.");
  return body;
}

function schedulePoll() {
  clearTimeout(timer);
  if (!disposed && run.value?.status === "running") timer = setTimeout(poll, 3000);
}

async function poll() {
  try {
    const next = await request(`/api/prospects/runs/${run.value.id}`);
    if (!disposed) { run.value = next; error.value = ""; }
  } catch (failure) {
    if (!disposed) error.value = `${failure.message} Your research may still be running. Reconnecting…`;
  } finally {
    schedulePoll();
  }
}

async function start() {
  if (running.value) return;
  starting.value = true;
  error.value = "";
  try {
    const next = await request("/api/prospects/runs", { method: "POST" });
    if (!disposed) { run.value = next; filter.value = "all"; }
    schedulePoll();
  } catch (failure) {
    if (!disposed) error.value = failure.message;
  } finally {
    starting.value = false;
  }
}

onMounted(async () => {
  try {
    const body = await request("/api/prospects/runs/latest");
    if (!disposed) run.value = body.run;
    schedulePoll();
  } catch (failure) {
    if (!disposed) error.value = failure.message;
  }
});
onUnmounted(() => { disposed = true; clearTimeout(timer); });
</script>

<template>
  <main class="manuscript-layout prospects-layout">
    <aside class="manuscript-sidebar">
      <div class="text-xs font-semibold uppercase text-muted">Customer research</div>
      <p class="text-sm leading-6">Find people describing a problem Jovis can help solve. Check their needs against the current product code before starting a conversation.</p>
      <button class="prospects-run" type="button" :disabled="running" @click="start">
        <Search :size="16" aria-hidden="true" />
        {{ running ? "Research in progress…" : run ? "Run analysis again" : "Find potential customers" }}
      </button>
      <p class="mt-3 text-xs leading-5 text-muted">20 searches across public X, Reddit, LinkedIn and Hacker News posts. Results arrive in batches; a full pass can take 10–30 minutes. You can switch tabs and come back.</p>
      <details v-if="run?.queries.length" class="prospects-queries">
        <summary>20 search queries · {{ searched }} confirmed</summary>
        <ol class="mt-3 grid gap-4">
          <li v-for="(item, index) in run.queries" :key="item.query">
            <span class="text-xs text-muted">{{ index + 1 }}. {{ item.theme }} · {{ item.status }}</span>
            <p class="mt-1 text-sm">{{ item.query }}</p>
            <p v-if="item.finding" class="mt-1 text-xs leading-5 text-muted">{{ item.finding }}</p>
          </li>
        </ol>
      </details>
    </aside>

    <section class="manuscript-content" :aria-busy="running" aria-labelledby="prospects-title">
      <div>
        <h2 id="prospects-title" class="text-2xl font-bold">Potential customers</h2>
        <p class="mt-2 text-sm leading-6 text-muted">Real complaints, an honest product fit, and a useful way to join the conversation.</p>
      </div>
      <p v-if="error" role="alert" class="prospects-notice text-danger"><AlertCircle :size="18" aria-hidden="true" />{{ error }}</p>
      <div v-if="run" class="prospects-progress" role="status" aria-live="polite">
        <div class="flex flex-wrap items-center justify-between gap-3 text-sm">
          <strong>{{ run.stage }}</strong>
          <span class="text-muted">{{ run.status }}</span>
        </div>
        <progress v-if="running" :value="attempted" max="20" class="mt-3 w-full" aria-label="Finished search attempts out of 20"></progress>
        <p class="mt-2 text-xs text-muted">Started {{ formatDate(run.started_at) }}<template v-if="run.completed_at"> · Finished {{ formatDate(run.completed_at) }}</template></p>
        <p v-if="run.error" role="alert" class="mt-3 text-sm text-danger">{{ run.error }}</p>
      </div>
      <details v-if="run?.warnings.length" class="prospects-warnings">
        <summary>{{ run.warnings.length }} research limitation{{ run.warnings.length === 1 ? '' : 's' }}</summary>
        <ul class="mt-3 list-disc pl-5 text-sm leading-6"><li v-for="(warning, i) in run.warnings" :key="i">{{ warning }}</li></ul>
      </details>
      <details v-if="run?.source_snapshot" class="prospects-audit text-sm">
        <summary>Jovis code inspection · {{ run.source_snapshot.evidence.length }} evidence excerpts</summary>
        <p class="mt-3 leading-6 text-muted">{{ run.source_snapshot.scope }}</p>
        <p class="mt-2 text-xs text-muted">Inspected {{ formatDate(run.source_snapshot.inspected_at) }} · Source fingerprint {{ run.source_snapshot.fingerprint.slice(0, 12) }}</p>
        <p v-if="run.source_snapshot.semantic_searches?.length" class="mt-2 text-xs text-muted">{{ run.source_snapshot.semantic_searches.length }} complaint-specific searches across Jovis code.</p>
        <p class="mt-3 leading-6">Connector files inspected: {{ run.source_snapshot.provider_files.join(', ') }}</p>
      </details>

      <div v-if="run?.posts.length" class="prospects-results-heading">
        <p class="text-sm">{{ run.posts.length }} potential conversation{{ run.posts.length === 1 ? '' : 's' }} · ranked by confidence</p>
        <label class="flex items-center gap-2 text-sm">
          <span>Show</span>
          <select v-model="filter" class="rounded-sm border border-rule-strong bg-paper px-2 py-2">
            <option value="all">All prospects</option>
            <option value="introduce">Ready to introduce</option>
          </select>
        </label>
      </div>
      <p v-if="run?.posts.length" class="text-xs leading-5 text-muted">Confidence is a rule-based research score, not a probability of purchase. It combines personal pain, buyer evidence, product coverage, solution requests, recency and source access. Dates need a live check before outreach.</p>

      <article v-for="post in posts" :key="post.url" class="prospect-row">
        <div class="flex flex-wrap items-center justify-between gap-3 text-xs text-muted">
          <span>{{ sourceLabel(post.url) }}<template v-if="post.author"> · {{ post.author }}</template></span>
          <span class="prospect-confidence" :class="{ 'text-success': post.confidence >= 75 }">{{ post.confidence }}/100 confidence</span>
        </div>
        <h3 class="mt-3 text-lg font-bold leading-7"><a :href="post.url" target="_blank" rel="noopener noreferrer" class="prospect-link">{{ post.title }} <ExternalLink :size="15" class="inline" aria-hidden="true" /><span class="sr-only"> (opens in a new tab)</span></a></h3>
        <div class="mt-2 flex flex-wrap gap-x-4 gap-y-2 text-xs text-muted">
          <strong :class="post.recommendation === 'Introduce Jovis' ? 'text-success' : 'text-warning'">{{ post.recommendation }}</strong>
          <span>{{ post.coverage }}% of identified needs supported</span>
          <span>{{ post.evidence_kind === 'full_post' ? 'Original post inspected' : 'Search snippet only' }}</span>
          <span>{{ post.published_at ? formatDate(post.published_at) : 'Date unverified' }}</span>
        </div>
        <blockquote class="prospect-quote">“{{ post.quote }}”</blockquote>
        <p v-if="post.summary" class="text-sm leading-6">{{ post.summary }}</p>
        <p v-if="post.date_note" class="mt-2 text-xs leading-5 text-muted">Date: {{ post.date_note }}</p>
        <details class="mt-4 text-sm">
          <summary class="font-semibold">Can Jovis solve this? <span v-if="post.requirements.length" class="font-normal text-muted">· {{ post.requirements.length }} needs checked</span></summary>
          <p v-if="!post.requirements.length" class="mt-3 text-warning">Product coverage could not be assessed. Verify the prospect's needs before introducing Jovis.</p>
          <ul class="prospect-requirements">
            <li v-for="(item, i) in post.requirements" :key="i">
              <div class="flex flex-wrap justify-between gap-2"><strong>{{ item.need }}</strong><span :class="item.status === 'supported' ? 'text-success' : 'text-warning'">{{ statusLabels[item.status] }}</span></div>
              <p class="mt-1 leading-6 text-muted">{{ item.explanation }}</p>
              <p v-if="item.next_step" class="mt-1 leading-6"><strong>Next:</strong> {{ item.next_step }}</p>
              <details v-for="id in item.evidence_ids" :key="id" class="mt-2 text-xs text-muted">
                <summary>Code evidence: {{ evidence[id]?.path }}:{{ evidence[id]?.line }}</summary>
                <pre class="prospect-code">{{ evidence[id]?.excerpt }}</pre>
              </details>
            </li>
          </ul>
        </details>
        <div v-if="post.introduction_angle" class="mt-4 text-sm leading-6"><strong>Conversation angle</strong><p class="mt-1">{{ post.introduction_angle }}</p></div>
        <p v-if="post.next_action" class="mt-3 text-sm leading-6"><strong>Next step:</strong> {{ post.next_action }}</p>
        <div class="prospect-response">
          <div class="flex flex-wrap items-center justify-between gap-3">
            <h4 class="text-sm font-semibold">Suggested response</h4>
            <button class="response-button" type="button" :disabled="responseLoading[replyKey(post)]" @click="generateResponse(post)">
              {{ responseLoading[replyKey(post)] ? 'Writing response…' : hasResponse(post) ? 'Regenerate response' : 'Suggest response' }}
            </button>
          </div>
          <p v-if="responseLoading[replyKey(post)]" role="status" class="mt-2 text-xs text-muted">Writing a useful reply in your solo founder voice. This may take a few minutes.</p>
          <template v-if="hasResponse(post)">
            <textarea class="response-draft mt-3" :aria-label="`Response to ${post.title}`" :value="responseText(post)" rows="5" @input="drafts[replyKey(post)] = $event.target.value; copied = ''"></textarea>
            <div class="mt-2 flex flex-wrap items-center justify-between gap-3">
              <p class="text-xs text-muted">Review and edit before posting. Edits stay in this tab.</p>
              <button class="response-button" type="button" :disabled="!responseText(post).trim()" @click="copyResponse(post)">{{ copied === replyKey(post) ? 'Copied' : 'Copy response' }}</button>
            </div>
            <p v-if="post.response_note" class="mt-2 text-xs leading-5 text-warning">Before posting: {{ post.response_note }}</p>
          </template>
          <p v-else-if="!responseLoading[replyKey(post)]" class="mt-2 text-xs leading-5 text-muted">Answer their question first. Mention Jovis where it fits, with an honest founder disclosure.</p>
          <p v-if="responseErrors[replyKey(post)]" role="alert" class="mt-2 text-sm text-danger">{{ responseErrors[replyKey(post)] }}</p>
        </div>
        <ul v-if="post.caveats.length" class="mt-3 list-disc pl-5 text-xs leading-5 text-muted"><li v-for="(caveat, i) in post.caveats" :key="i">{{ caveat }}</li></ul>
        <details class="mt-4 text-xs text-muted">
          <summary>Why this confidence score?</summary>
          <dl class="mt-3 grid gap-2"><div v-for="(points, label) in post.confidence_factors" :key="label" class="flex max-w-sm justify-between gap-4"><dt>{{ label }}</dt><dd>{{ points }} points</dd></div></dl>
          <p class="mt-2 leading-5">Unverified dates, older posts and snippet-only sources cap confidence at 59. Uncertain buyers and general discussions cap it at 49. Requirements are weighted equally; partial support receives half credit.</p>
        </details>
      </article>
      <div v-if="!posts.length" class="manuscript-empty">
        <div>
          <p class="font-semibold">{{ running ? 'Looking for useful conversations' : run?.posts.length ? 'No prospects are ready for an introduction yet' : run ? 'No qualified conversations found' : 'Start with people who already have the problem' }}</p>
          <p class="mt-2 text-sm leading-6 text-muted">{{ running ? 'Results appear as each search group completes. Each prospect is checked against Jovis code.' : run?.posts.length ? 'Choose All prospects to review product gaps and research leads.' : run ? 'Review search coverage and limitations above, then run a fresh analysis. Results are never filled with invented leads.' : 'Run the analysis to search 20 problem-focused queries, inspect original posts, and compare each person’s needs with Jovis.' }}</p>
        </div>
      </div>
    </section>
  </main>
</template>

<style scoped>
.prospects-run { display: flex; align-items: center; justify-content: center; gap: .5rem; width: 100%; margin-top: 1.5rem; min-height: 2.75rem; padding: .6rem .8rem; border-radius: 2px; background: var(--ink); color: var(--paper); font-size: .875rem; font-weight: 600; }
.prospects-run:hover { background: var(--ink-hover); }
.prospects-run:disabled { opacity: .55; }
.prospects-queries { margin-top: 2rem; border-top: 1px solid var(--rule); padding-top: 1rem; }
summary { cursor: pointer; padding-block: .5rem; overflow-wrap: anywhere; }
.prospects-queries summary { font-size: .8125rem; }
.prospects-notice { display: flex; align-items: start; gap: .75rem; border: 1px solid var(--danger-rule); background: var(--danger-wash); padding: 1rem; font-size: .875rem; }
.prospects-notice svg { flex-shrink: 0; }
.prospects-progress { border-block: 1px solid var(--rule); padding-block: 1rem; }
progress { accent-color: var(--accent); height: .5rem; }
.prospects-warnings { padding: .5rem 1rem; background: var(--warning-wash); border: 1px solid var(--warning-rule); color: var(--warning); font-size: .875rem; }
.prospects-audit { border-bottom: 1px solid var(--rule); padding-bottom: .75rem; overflow-wrap: anywhere; }
.prospects-results-heading { display: flex; align-items: center; justify-content: space-between; gap: 1rem; flex-wrap: wrap; }
.prospect-row { border-top: 1px solid var(--rule-strong); padding-block: 1.5rem .5rem; overflow-wrap: anywhere; }
.prospect-row p, .prospect-quote { max-width: 75ch; }
.prospect-confidence { font-weight: 700; white-space: nowrap; }
.prospect-link { text-decoration: underline; text-underline-offset: 4px; text-decoration-color: var(--rule-strong); }
.prospect-link:hover { color: var(--accent); text-decoration-color: currentColor; }
.prospect-quote { padding: 1rem; margin-block: 1rem; background: var(--paper-shade); font-size: .875rem; line-height: 1.75; }
.prospect-requirements { display: grid; gap: 1rem; margin-top: .75rem; }
.prospect-requirements > li { border-top: 1px solid var(--rule); padding-top: .75rem; }
.prospect-code { max-height: 18rem; overflow: auto; margin-top: .5rem; padding: .75rem; background: var(--paper-shade); line-height: 1.6; white-space: pre-wrap; overflow-wrap: anywhere; }
.prospect-response { margin-top: 1.25rem; border-top: 1px solid var(--rule); padding-top: 1rem; }
.response-button { border: 1px solid var(--rule-strong); border-radius: 2px; padding: .5rem .75rem; font-size: .75rem; background: var(--paper); }
.response-button:hover { background: var(--paper-shade); }
.response-button:disabled { opacity: .55; }
.response-draft { border: 1px solid var(--rule-strong); border-radius: 2px; background: var(--paper); padding: .75rem; font-size: .875rem; line-height: 1.75; }
</style>
