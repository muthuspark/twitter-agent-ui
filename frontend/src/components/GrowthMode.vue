<script setup>
import {
  AlertCircle,
  Bookmark,
  CheckCircle2,
  ExternalLink,
  Heart,
  History,
  Search,
  ShieldCheck,
  Sparkles,
  X,
} from "@lucide/vue";
import { computed, onMounted, ref } from "vue";

import { formatDate, formatMetric } from "../lib/format";
import { buildGrowthActionPayload, buildRecommendationMetadata, combinedGrowthButtonState, growthActionLabel, normalizeRecommendations } from "../lib/social";

const defaultQuery = "";
const profileFocus = ref("Jovis.ai target customers: founders, RevOps, sales ops, support ops, and business teams trying to get answers from live business data without waiting on SQL, dashboards, or data teams");
const query = ref(defaultQuery);
const maxResults = ref(12);
const candidates = ref([]);
const recommendations = ref([]);
const history = ref([]);
const loadingDiscover = ref(false);
const loadingAnalyze = ref(false);
const actionLoadingId = ref(null);
const bookmarkedTweetIds = ref(new Set());
const error = ref("");
const discoverCommand = ref([]);

const enrichedRecommendations = computed(() =>
  normalizeRecommendations(recommendations.value, candidates.value),
);

const primaryButtonState = computed(() =>
  combinedGrowthButtonState({
    loadingDiscover: loadingDiscover.value,
    loadingAnalyze: loadingAnalyze.value,
  }),
);

function actionTone(action) {
  if (action === "comment") return "bg-accent-wash text-accent";
  if (action === "like") return "bg-success-wash text-success";
  return "bg-paper-shade text-muted";
}

function recommendationCommand(item) {
  if (item.action === "like") return `twitter like ${item.tweet_id} --json`;
  if (item.action === "comment") {
    return `twitter reply ${item.tweet_id} "${item.draft || ""}" --json`;
  }
  return "No write command";
}

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

async function discover() {
  loadingDiscover.value = true;
  error.value = "";
  recommendations.value = [];
  try {
    const body = await requestJson("/api/growth/discover", {
      query: query.value,
      max: maxResults.value,
    });
    candidates.value = body.candidates;
    discoverCommand.value = body.command;
  } catch (failure) {
    error.value = failure.message;
  } finally {
    loadingDiscover.value = false;
  }
}

async function analyze(candidateList = candidates.value) {
  if (!candidateList.length) return;
  loadingAnalyze.value = true;
  error.value = "";
  try {
    const body = await requestJson("/api/growth/analyze", {
      profile_focus: profileFocus.value,
      candidates: candidateList,
    });
    recommendations.value = body.recommendations;
  } catch (failure) {
    error.value = failure.message;
  } finally {
    loadingAnalyze.value = false;
  }
}

async function discoverAndAnalyze() {
  if (loadingDiscover.value || loadingAnalyze.value) return;
  loadingDiscover.value = true;
  error.value = "";
  recommendations.value = [];
  try {
    const discoverBody = await requestJson("/api/growth/discover", {
      query: query.value,
      max: maxResults.value,
    });
    candidates.value = discoverBody.candidates;
    discoverCommand.value = discoverBody.command;
  } catch (failure) {
    error.value = failure.message;
    loadingDiscover.value = false;
    return;
  }
  loadingDiscover.value = false;
  await analyze(candidates.value);
}

async function approve(item, action = item.action) {
  if (actionLoadingId.value) return;
  actionLoadingId.value = item.id;
  error.value = "";
  try {
    await requestJson("/api/growth/approve", buildGrowthActionPayload(item, action));
    if (action === "bookmark") {
      bookmarkedTweetIds.value = new Set([...bookmarkedTweetIds.value, item.tweet_id]);
    } else {
      recommendations.value = recommendations.value.filter((entry) => entry.id !== item.id);
    }
    await loadHistory();
  } catch (failure) {
    error.value = failure.message;
  } finally {
    actionLoadingId.value = null;
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

onMounted(loadHistory);
</script>

<template>
  <main
    class="manuscript-layout growth-layout"
  >
    <aside class="manuscript-sidebar">
      <div class="mb-3 flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.08em] text-muted">
        <Sparkles :size="14" aria-hidden="true" />
        Growth Mode
      </div>
      <div class="settings-fields grid gap-4">
        <label class="grid gap-1.5 text-sm">
          <span class="font-medium">Search query</span>
          <textarea
            v-model="query"
            class="min-h-24 rounded-sm border border-rule-strong bg-paper px-3 py-2 leading-5"
            placeholder="Leave empty to rotate through Jovis target-customer searches"
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
          :disabled="primaryButtonState.disabled"
          type="button"
          @click="discoverAndAnalyze"
        >
          <Search v-if="!loadingAnalyze" :size="16" aria-hidden="true" />
          <Sparkles v-else :size="16" aria-hidden="true" />
          {{ primaryButtonState.label }}
        </button>
      </div>

      <div class="mt-6 rounded-sm border border-warning-rule bg-warning-wash p-3 text-sm text-warning">
        <div class="flex items-center gap-2 font-semibold">
          <ShieldCheck :size="16" aria-hidden="true" />
          Approval guardrail
        </div>
        <p class="mt-1 leading-5">
          Likes and comments are never executed automatically. Approve one recommendation at a time.
        </p>
      </div>
    </aside>

    <section class="manuscript-content">
      <h2 class="text-2xl font-bold">Recommendations</h2>
      <div class="grid gap-3">
        <div
          v-if="error"
          class="flex items-start gap-3 rounded-sm border border-danger-rule bg-danger-wash p-3 text-sm text-danger"
        >
          <AlertCircle class="mt-0.5 shrink-0" :size="18" aria-hidden="true" />
          <div>{{ error }}</div>
        </div>
        <div class="discovery-command">
          <div class="mb-2 text-xs font-semibold uppercase tracking-[0.08em] text-muted">
            Discovery command
          </div>
          <div class="overflow-x-auto rounded-sm command-sheet bg-paper-shade px-3 py-2 font-mono text-sm text-ink">
            {{ discoverCommand.length ? discoverCommand.join(" ") : "twitter search ..." }}
          </div>
        </div>
        <div class="flex flex-wrap gap-2 text-sm text-muted">
          <span class="rounded-sm bg-paper-shade px-2 py-1">{{ candidates.length }} candidates</span>
          <span class="rounded-sm bg-paper-shade px-2 py-1">{{ recommendations.length }} pending recommendations</span>
        </div>
      </div>

      <div class="results-region">
        <div v-if="loadingDiscover || loadingAnalyze" class="grid gap-3">
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
            <div class="flex flex-wrap items-center gap-2">
              <span
                class="inline-flex h-7 items-center rounded-sm px-2 text-xs font-semibold"
                :class="actionTone(item.action)"
              >
                {{ item.actionLabel }}
              </span>
              <span class="text-sm font-semibold">{{ item.confidence }}% confidence</span>
              <span class="text-sm text-muted">risk: {{ item.risk }}</span>
            </div>
            <p class="mt-3 text-sm leading-6 text-ink-secondary">{{ item.reason }}</p>

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

            <div v-if="item.action === 'comment'" class="mt-4 grid gap-3 text-sm">
              <div>
                <span class="font-medium">Choose a comment draft</span>
                <div class="mt-2 grid gap-2">
                  <label
                    v-for="(draft, draftIndex) in item.draftOptions"
                    :key="`${item.id}-${draftIndex}`"
                    class="flex cursor-pointer gap-3 rounded-sm border border-rule bg-paper p-3 hover:bg-paper"
                  >
                    <input
                      v-model="item.draft"
                      class="mt-1"
                      :name="`comment-draft-${item.id}`"
                      type="radio"
                      :value="draft"
                    />
                    <span class="leading-5">{{ draft }}</span>
                  </label>
                </div>
              </div>
              <label class="grid gap-1.5">
                <span class="font-medium">Editable final comment</span>
              <textarea
                v-model="item.draft"
                class="min-h-20 rounded-sm border border-rule-strong bg-paper px-3 py-2 leading-5"
              ></textarea>
              </label>
            </div>

            <div class="mt-4 rounded-sm bg-paper-shade px-3 py-2 font-mono text-xs text-ink-secondary">
              {{ recommendationCommand(item) }}
            </div>

            <div class="mt-4 flex flex-wrap gap-2">
              <button
                v-if="item.action === 'like'"
                class="inline-flex h-9 items-center gap-2 rounded-sm bg-ink px-3 text-sm font-semibold text-paper hover:bg-ink-hover disabled:cursor-not-allowed disabled:opacity-55"
                :disabled="Boolean(actionLoadingId)"
                type="button"
                @click="approve(item)"
              >
                <Heart :size="16" aria-hidden="true" />
                Like Post
              </button>
              <button
                v-else
                class="inline-flex h-9 items-center gap-2 rounded-sm border border-rule-strong bg-paper px-3 text-sm font-semibold hover:bg-paper-shade disabled:cursor-not-allowed disabled:opacity-55"
                :disabled="Boolean(actionLoadingId)"
                type="button"
                @click="approve(item, 'like')"
              >
                <Heart :size="16" aria-hidden="true" />
                Like Post
              </button>
              <button
                class="inline-flex h-9 items-center gap-2 rounded-sm border border-rule-strong bg-paper px-3 text-sm font-semibold hover:bg-paper-shade disabled:cursor-not-allowed disabled:opacity-55"
                :disabled="Boolean(actionLoadingId) || bookmarkedTweetIds.has(item.tweet_id)"
                type="button"
                @click="approve(item, 'bookmark')"
              >
                <Bookmark :size="16" aria-hidden="true" />
                {{ bookmarkedTweetIds.has(item.tweet_id) ? "Bookmarked" : actionLoadingId === item.id ? "Working…" : "Bookmark" }}
              </button>
              <button
                v-if="item.action !== 'like'"
                class="inline-flex h-9 items-center gap-2 rounded-sm bg-ink px-3 text-sm font-semibold text-paper hover:bg-ink-hover disabled:cursor-not-allowed disabled:opacity-55"
                :disabled="Boolean(actionLoadingId)"
                type="button"
                @click="approve(item)"
              >
                <CheckCircle2 :size="16" aria-hidden="true" />
                Approve {{ growthActionLabel(item.action) }}
              </button>
              <button
                class="inline-flex h-9 items-center gap-2 rounded-sm border border-rule-strong bg-paper px-3 text-sm font-semibold hover:bg-paper-shade disabled:cursor-not-allowed disabled:opacity-55"
                :disabled="Boolean(actionLoadingId)"
                type="button"
                @click="reject(item)"
              >
                <X :size="16" aria-hidden="true" />
                Reject
              </button>
            </div>
          </article>
        </div>

        <div v-else-if="candidates.length" class="manuscript-empty">
          <div class="max-w-sm">
            <div class="font-semibold">{{ recommendations.length ? "Only skip suggestions found" : "Candidates loaded" }}</div>
            <p class="mt-1 text-sm leading-6 text-muted">
              {{
                recommendations.length
                  ? "Codex CLI did not find any like or comment actions worth showing. Adjust the search query or try again later."
                  : "Run discovery and analysis to turn these posts into like or comment recommendations."
              }}
            </p>
          </div>
        </div>

        <div v-else class="manuscript-empty">
          <div class="max-w-sm">
            <div class="font-semibold">Discover posts to start</div>
            <p class="mt-1 text-sm leading-6 text-muted">
              Search for AI, startup, software engineering, and founder conversations, then ask Codex CLI to rank them.
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
