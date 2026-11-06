<script setup>
import {
  AlertCircle,
  CheckCircle2,
  ExternalLink,
  History,
  Search,
  ShieldCheck,
  Sparkles,
  X,
} from "@lucide/vue";
import { computed, onActivated, onDeactivated, ref } from "vue";

import { formatDate, formatMetric } from "../lib/format";
import { buildGrowthActionPayload, buildRecommendationMetadata, growthActionLabel, normalizeRecommendations } from "../lib/social";

const defaultQuery = "";
const profileFocus = ref("Jovis.ai target customers: founders, RevOps, sales ops, support ops, and business teams trying to get answers from live business data without waiting on SQL, dashboards, or data teams");
const query = ref(defaultQuery);
const maxResults = ref(12);
const candidates = ref([]);
const recommendations = ref([]);
const history = ref([]);
const loadingDiscover = ref(false);
const actionLoadingId = ref(null);
const alternativesLoadingId = ref(null);
const expandedAlternatives = ref(new Set());
const alternativesById = ref({});
const alternativesErrors = ref({});
const postingFailures = ref({});
const copiedReplyId = ref(null);
const error = ref("");
const discoverCommand = ref([]);
const lastRefresh = ref("");
const discoveryNotice = ref("");
let refreshTimer;

const enrichedRecommendations = computed(() =>
  normalizeRecommendations(recommendations.value, candidates.value),
);

async function requestJson(path, payload) {
  const response = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(body.detail || "Request failed");
  return body;
}

async function loadPendingCandidates() {
  const response = await fetch("/api/growth/comment-candidates");
  const body = await response.json().catch(() => ({}));
  if (!response.ok || body.ok !== true) throw new Error(body.detail || "Unable to load comment candidates.");
  recommendations.value = body.candidates ?? [];
  candidates.value = recommendations.value.map((item) => item.tweet).filter(Boolean);
}

async function discoverAndAnalyze({ automatic = false } = {}) {
  if (loadingDiscover.value) return;
  loadingDiscover.value = true;
  error.value = "";
  try {
    const body = await requestJson("/api/growth/comment-candidates/refresh", {
      query: query.value,
      max: maxResults.value,
      profile_focus: profileFocus.value,
    });
    recommendations.value = body.candidates ?? [];
    candidates.value = recommendations.value.map((item) => item.tweet).filter(Boolean);
    discoveryNotice.value = body.search_source === "home_timeline"
      ? "X search returned a 404, so these suggestions came from your recent home timeline and were checked against your topic."
      : "";
    discoverCommand.value = body.search_source === "home_timeline"
      ? ["twitter", "feed", "--max", String(maxResults.value)]
      : ["twitter", "search", body.query || query.value || "rotating topic"];
    lastRefresh.value = new Date().toLocaleString();
  } catch (failure) {
    if (!automatic || !recommendations.value.length) error.value = failure.message;
  } finally {
    loadingDiscover.value = false;
  }
}

async function approve(item) {
  if (actionLoadingId.value) return;
  actionLoadingId.value = item.id;
  error.value = "";
  postingFailures.value = { ...postingFailures.value, [item.id]: "" };
  try {
    await requestJson("/api/growth/approve", buildGrowthActionPayload(item));
    recommendations.value = recommendations.value.filter((entry) => entry.id !== item.id);
    await loadHistory();
  } catch (failure) {
    postingFailures.value = { ...postingFailures.value, [item.id]: failure.message };
  } finally {
    actionLoadingId.value = null;
  }
}

async function copyReply(item) {
  try {
    await navigator.clipboard.writeText(item.draft || "");
    copiedReplyId.value = item.id;
    window.setTimeout(() => {
      if (copiedReplyId.value === item.id) copiedReplyId.value = null;
    }, 1800);
  } catch {
    postingFailures.value = { ...postingFailures.value, [item.id]: `${postingFailures.value[item.id]} Select the reply text and copy it manually.` };
  }
}

async function toggleAlternatives(item) {
  const open = new Set(expandedAlternatives.value);
  if (open.has(item.id)) {
    open.delete(item.id);
    expandedAlternatives.value = open;
    return;
  }
  if (alternativesById.value[item.id]?.length) {
    open.add(item.id);
    expandedAlternatives.value = open;
    return;
  }
  alternativesLoadingId.value = item.id;
  alternativesErrors.value = { ...alternativesErrors.value, [item.id]: "" };
  try {
    const response = await fetch(`/api/growth/comment-candidates/${encodeURIComponent(item.id)}/alternatives`, { method: "POST" });
    const body = await response.json().catch(() => ({}));
    if (!response.ok || body.ok !== true) throw new Error(body.detail || "Unable to generate alternatives.");
    alternativesById.value = { ...alternativesById.value, [item.id]: body.alternatives ?? [] };
    open.add(item.id);
    expandedAlternatives.value = open;
  } catch (failure) {
    alternativesErrors.value = { ...alternativesErrors.value, [item.id]: failure.message || "Unable to generate alternatives." };
  } finally {
    alternativesLoadingId.value = null;
  }
}

async function reject(item) {
  actionLoadingId.value = item.id;
  error.value = "";
  try {
    await requestJson("/api/growth/reject", {
      recommendation_id: item.id,
      action: item.action,
      tweet_id: item.tweet_id,
      comment_text: item.draft,
      metadata: buildRecommendationMetadata(item),
    });
    recommendations.value = recommendations.value.filter((entry) => entry.id !== item.id);
    await loadHistory();
  } catch (failure) {
    error.value = failure.message;
  } finally {
    actionLoadingId.value = null;
  }
}

async function loadHistory() {
  const response = await fetch("/api/growth/history");
  const body = await response.json().catch(() => ({}));
  if (response.ok) history.value = body.history ?? [];
}

async function activateCandidates() {
  try {
    await Promise.all([loadPendingCandidates(), loadHistory()]);
  } catch (failure) {
    error.value = failure.message;
  }
  await discoverAndAnalyze({ automatic: true });
  refreshTimer = window.setInterval(() => discoverAndAnalyze({ automatic: true }), 60 * 60 * 1000);
}

function deactivateCandidates() {
  window.clearInterval(refreshTimer);
  refreshTimer = undefined;
}

onActivated(activateCandidates);
onDeactivated(deactivateCandidates);
</script>

<template>
  <main
    class="manuscript-layout growth-layout"
  >
    <aside class="manuscript-sidebar">
      <div class="mb-3 flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.08em] text-muted">
        <Sparkles :size="14" aria-hidden="true" />
        Comment Candidates
      </div>
      <div class="settings-fields grid gap-4">
        <label class="grid gap-1.5 text-sm">
            <span class="font-medium">Topic search</span>
          <textarea
            v-model="query"
            class="min-h-24 rounded-sm border border-rule-strong bg-paper px-3 py-2 leading-5"
            placeholder="Leave empty to rotate through your saved topic searches"
          ></textarea>
        </label>
        <label class="grid gap-1.5 text-sm">
          <span class="font-medium">Profile focus</span>
          <textarea
            v-model="profileFocus"
            class="min-h-20 rounded-sm border border-rule-strong bg-paper px-3 py-2 leading-5"
          ></textarea>
        </label>
        <label class="grid gap-1.5 text-sm">
          <span class="font-medium">Max candidates</span>
          <input
            v-model.number="maxResults"
            class="h-9 rounded-sm border border-rule-strong bg-paper px-3"
            max="30"
            min="1"
            type="number"
          />
        </label>
        <button
          class="inline-flex h-9 items-center justify-center gap-2 rounded-sm bg-ink px-4 text-sm font-semibold text-paper hover:bg-ink-hover disabled:cursor-not-allowed disabled:opacity-55"
          :disabled="loadingDiscover || Boolean(actionLoadingId)"
          type="button"
          @click="discoverAndAnalyze()"
        >
          <Search v-if="!loadingDiscover" :size="16" aria-hidden="true" />
          <Sparkles v-else :size="16" aria-hidden="true" />
          {{ loadingDiscover ? "Finding candidates…" : "Find candidates now" }}
        </button>
      </div>

      <div class="mt-6 rounded-sm border border-warning-rule bg-warning-wash p-3 text-sm text-warning">
        <div class="flex items-center gap-2 font-semibold">
          <ShieldCheck :size="16" aria-hidden="true" />
          Approval guardrail
        </div>
        <p class="mt-1 leading-5">
          Suggestions refresh when this section opens and every hour while it stays open. Replies are only sent after you approve them.
        </p>
      </div>
    </aside>

    <section class="manuscript-content">
      <h2 class="text-2xl font-bold">Comment candidates</h2>
      <p class="text-sm text-muted">Posts where you may have something useful to add, with editable AI reply suggestions.</p>
      <div class="grid gap-3">
        <div
          v-if="error"
          class="flex items-start gap-3 rounded-sm border border-danger-rule bg-danger-wash p-3 text-sm text-danger"
        >
          <AlertCircle class="mt-0.5 shrink-0" :size="18" aria-hidden="true" />
          <div>{{ error }}</div>
        </div>
        <p v-if="discoveryNotice" class="rounded-sm border border-warning-rule bg-warning-wash p-3 text-sm text-warning" role="status">
          {{ discoveryNotice }}
        </p>
        <div class="discovery-command">
          <div class="mb-2 text-xs font-semibold uppercase tracking-[0.08em] text-muted">
            Discovery command
          </div>
          <div class="overflow-x-auto rounded-sm command-sheet bg-paper-shade px-3 py-2 font-mono text-sm text-ink">
            {{ discoverCommand.length ? discoverCommand.join(" ") : "twitter search [rotating topic]" }}
          </div>
        </div>
        <div class="flex flex-wrap gap-2 text-sm text-muted">
          <span class="rounded-sm bg-paper-shade px-2 py-1">{{ candidates.length }} candidates</span>
          <span class="rounded-sm bg-paper-shade px-2 py-1">{{ recommendations.length }} waiting for review</span>
          <span v-if="lastRefresh" class="rounded-sm bg-paper-shade px-2 py-1">Updated {{ lastRefresh }}</span>
        </div>
      </div>

      <div class="results-region">
        <div v-if="loadingDiscover" class="grid gap-3">
          <div
            v-for="index in 4"
            :key="index"
            class="h-36 animate-pulse rounded-sm border border-rule bg-paper-shade"
          ></div>
        </div>

        <div v-else-if="enrichedRecommendations.length" class="grid gap-3">
          <article
            v-for="item in enrichedRecommendations"
            :key="item.id"
            class="rounded-sm border border-rule bg-paper p-4"
          >
            <p class="text-sm leading-6 text-ink-secondary">{{ item.reason }}</p>

            <div class="mt-4 border-t border-rule pt-4">
              <div class="flex flex-wrap items-center gap-x-2 gap-y-1">
                <strong class="text-sm">{{ item.tweet?.author?.name || "Unknown" }}</strong>
                <span class="text-sm text-muted">@{{ item.tweet?.author?.screenName }}</span>
                <span class="text-sm text-muted">{{ formatDate(item.tweet?.createdAtISO) }}</span>
              </div>
              <p class="mt-2 whitespace-pre-wrap text-sm leading-6">{{ item.tweet?.text || "Source post unavailable" }}</p>
              <div class="mt-3 flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted">
                <span>{{ formatMetric(item.tweet?.metrics?.likes) }} likes</span>
                <span>{{ formatMetric(item.tweet?.metrics?.replies) }} replies</span>
                <span>{{ formatMetric(item.tweet?.metrics?.retweets) }} reposts</span>
                <span>{{ formatMetric(item.tweet?.metrics?.views) }} views</span>
              </div>
              <a
                v-if="item.postUrl"
                class="mt-3 inline-flex h-8 items-center gap-2 rounded-sm border border-rule-strong bg-paper px-3 text-sm font-semibold hover:bg-paper-shade"
                :href="item.postUrl"
                rel="noreferrer"
                target="_blank"
              >
                <ExternalLink :size="15" aria-hidden="true" />
                Link to Post
              </a>
            </div>

            <div v-if="item.action === 'comment'" class="mt-4 grid gap-2 text-sm">
              <label class="grid gap-1.5">
                <span class="font-medium">Suggested reply</span>
                <textarea
                  v-model="item.draft"
                  class="min-h-20 rounded-sm border border-rule-strong bg-paper px-3 py-2 leading-5"
                ></textarea>
              </label>
              <button class="button justify-self-start" type="button" :disabled="alternativesLoadingId === item.id" @click="toggleAlternatives(item)">
                {{ alternativesLoadingId === item.id ? "Generating options…" : expandedAlternatives.has(item.id) ? "Hide options" : "Try two other angles" }}
              </button>
              <p v-if="alternativesErrors[item.id]" class="text-danger" role="alert">{{ alternativesErrors[item.id] }}</p>
              <div v-if="expandedAlternatives.has(item.id)" class="grid gap-2" role="radiogroup" aria-label="Alternative replies">
                <label
                  v-for="(draft, draftIndex) in (alternativesById[item.id] || item.draftOptions.slice(1))"
                  :key="`${item.id}-alternative-${draftIndex}`"
                  class="flex cursor-pointer gap-3 rounded-sm border border-rule p-3 hover:bg-paper-shade"
                >
                  <input v-model="item.draft" class="mt-1" :name="`comment-draft-${item.id}`" type="radio" :value="draft" />
                  <span class="leading-5">{{ draft }}</span>
                </label>
              </div>
            </div>

            <div class="mt-4 flex flex-wrap gap-2">
              <button
                class="inline-flex h-9 items-center gap-2 rounded-sm bg-ink px-3 text-sm font-semibold text-paper hover:bg-ink-hover disabled:cursor-not-allowed disabled:opacity-55"
                :disabled="Boolean(actionLoadingId)"
                type="button"
                @click="approve(item)"
              >
                <CheckCircle2 :size="16" aria-hidden="true" />
                Post this reply
              </button>
              <button
                class="inline-flex h-9 items-center gap-2 rounded-sm border border-rule-strong bg-paper px-3 text-sm font-semibold hover:bg-paper-shade disabled:cursor-not-allowed disabled:opacity-55"
                :disabled="Boolean(actionLoadingId)"
                type="button"
                @click="reject(item)"
              >
                <X :size="16" aria-hidden="true" />
                Dismiss
              </button>
            </div>
            <div v-if="postingFailures[item.id]" class="mt-3 rounded-sm border border-warning-rule bg-warning-wash p-3 text-sm text-warning" role="alert">
              <p>{{ postingFailures[item.id] }}</p>
              <p class="mt-1">Your reply draft is still here. You can copy it and post from X.</p>
              <div class="mt-2 flex flex-wrap gap-2">
                <button class="button" type="button" @click="copyReply(item)">
                  {{ copiedReplyId === item.id ? "Copied" : "Copy reply" }}
                </button>
                <a v-if="item.postUrl" class="button" :href="item.postUrl" rel="noreferrer" target="_blank">Open post on X</a>
              </div>
            </div>
          </article>
        </div>

        <div v-else-if="candidates.length" class="manuscript-empty">
          <div class="max-w-sm">
            <div class="font-semibold">{{ recommendations.length ? "No reply suggestions yet" : "No comment candidates yet" }}</div>
            <p class="mt-1 text-sm leading-6 text-muted">
              {{
                recommendations.length
                  ? "The posts found did not have a specific reply worth recommending. Try another topic or check again later."
                  : "Choose Find candidates now to search for conversations where you can add a useful reply."
              }}
            </p>
          </div>
        </div>

        <div v-else class="manuscript-empty">
          <div class="max-w-sm">
            <div class="font-semibold">Finding relevant conversations</div>
            <p class="mt-1 text-sm leading-6 text-muted">
              New candidate posts will appear here with an editable reply suggestion. You stay in control of every reply.
            </p>
          </div>
        </div>
      </div>
    </section>

    <aside class="manuscript-history" aria-label="Action history">
      <div class="history-heading flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.08em] text-muted">
        <History :size="14" aria-hidden="true" />
        Action history
      </div>
      <div v-if="history.length" class="history-list" tabindex="0" aria-label="Past actions">
        <div
          v-for="record in history"
          :key="record.id"
          class="history-record text-sm"
        >
          <div class="flex items-center justify-between gap-3">
            <span class="font-semibold">{{ growthActionLabel(record.action) }}</span>
            <span
              class="rounded-sm px-2 py-1 text-xs font-semibold"
              :class="record.status === 'approved' ? 'bg-success-wash text-success' : 'bg-paper-shade text-muted'"
            >
              {{ record.status }}
            </span>
          </div>
          <div class="mt-2 font-mono text-xs text-muted">{{ record.tweet_id }}</div>
          <p v-if="record.comment_text" class="mt-2 leading-5">{{ record.comment_text }}</p>
        </div>
      </div>
      <div v-else class="rounded-sm border border-dashed border-rule-strong p-4 text-sm text-muted">
        Approved and rejected recommendations will appear here.
      </div>
    </aside>
  </main>
</template>
