<script setup>
import {
  AlertCircle,
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

import {
  buildGrowthActionPayload,
  buildRecommendationMetadata,
  combinedGrowthButtonState,
  formatDate,
  formatMetric,
  growthActionLabel,
  normalizeRecommendations,
} from "../lib/workbench";

const defaultQuery = "AI agents startups software engineering founder";
const profileFocus = ref("AI, startups, software engineering, and personal brand");
const query = ref(defaultQuery);
const maxResults = ref(12);
const candidates = ref([]);
const recommendations = ref([]);
const history = ref([]);
const loadingDiscover = ref(false);
const loadingAnalyze = ref(false);
const actionLoadingId = ref(null);
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
  if (action === "comment") return "bg-[oklch(92%_0.045_245)] text-[oklch(34%_0.08_245)]";
  if (action === "like") return "bg-[oklch(94%_0.034_155)] text-[oklch(34%_0.08_155)]";
  return "bg-[oklch(94%_0.01_245)] text-[oklch(45%_0.024_245)]";
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

async function approve(item) {
  actionLoadingId.value = item.id;
  error.value = "";
  try {
    await requestJson("/api/growth/approve", buildGrowthActionPayload(item));
    recommendations.value = recommendations.value.filter((entry) => entry.id !== item.id);
    await loadHistory();
  } catch (failure) {
    error.value = failure.message;
  } finally {
    actionLoadingId.value = null;
  }
}

async function likePost(item) {
  actionLoadingId.value = item.id;
  error.value = "";
  try {
    await requestJson("/api/growth/approve", buildGrowthActionPayload(item, "like"));
    recommendations.value = recommendations.value.filter((entry) => entry.id !== item.id);
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
    class="grid min-h-[calc(100vh-112px)] overflow-hidden rounded-lg border border-[oklch(85%_0.012_245)] bg-[oklch(98%_0.004_245)] shadow-sm xl:grid-cols-[320px_minmax(0,1fr)_340px]"
  >
    <aside class="border-b border-[oklch(87%_0.011_245)] bg-[oklch(94%_0.007_245)] p-4 xl:border-b-0 xl:border-r">
      <div class="mb-3 flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.08em] text-[oklch(47%_0.024_245)]">
        <Sparkles :size="14" aria-hidden="true" />
        Growth Mode
      </div>
      <div class="grid gap-4">
        <label class="grid gap-1.5 text-sm">
          <span class="font-medium">Search query</span>
          <textarea
            v-model="query"
            class="min-h-24 rounded-md border border-[oklch(82%_0.014_245)] bg-[oklch(99%_0.004_245)] px-3 py-2 leading-5"
          ></textarea>
        </label>
        <label class="grid gap-1.5 text-sm">
          <span class="font-medium">Profile focus</span>
          <textarea
            v-model="profileFocus"
            class="min-h-20 rounded-md border border-[oklch(82%_0.014_245)] bg-[oklch(99%_0.004_245)] px-3 py-2 leading-5"
          ></textarea>
        </label>
        <label class="grid gap-1.5 text-sm">
          <span class="font-medium">Max candidates</span>
          <input
            v-model.number="maxResults"
            class="h-9 rounded-md border border-[oklch(82%_0.014_245)] bg-[oklch(99%_0.004_245)] px-3"
            max="30"
            min="1"
            type="number"
          />
        </label>
        <button
          class="inline-flex h-9 items-center justify-center gap-2 rounded-md bg-[oklch(58%_0.13_245)] px-4 text-sm font-semibold text-[oklch(98%_0.004_245)] hover:bg-[oklch(52%_0.14_245)] disabled:cursor-not-allowed disabled:opacity-55"
          :disabled="primaryButtonState.disabled"
          type="button"
          @click="discoverAndAnalyze"
        >
          <Search v-if="!loadingAnalyze" :size="16" aria-hidden="true" />
          <Sparkles v-else :size="16" aria-hidden="true" />
          {{ primaryButtonState.label }}
        </button>
      </div>

      <div class="mt-6 rounded-md border border-[oklch(83%_0.02_80)] bg-[oklch(96%_0.022_80)] p-3 text-sm text-[oklch(38%_0.055_80)]">
        <div class="flex items-center gap-2 font-semibold">
          <ShieldCheck :size="16" aria-hidden="true" />
          Approval guardrail
        </div>
        <p class="mt-1 leading-5">
          Likes and comments are never executed automatically. Approve one recommendation at a time.
        </p>
      </div>
    </aside>

    <section class="grid min-h-[620px] grid-rows-[auto_1fr] gap-4 overflow-hidden p-4">
      <div class="grid gap-3">
        <div
          v-if="error"
          class="flex items-start gap-3 rounded-md border border-[oklch(79%_0.052_30)] bg-[oklch(96%_0.025_30)] p-3 text-sm text-[oklch(36%_0.075_30)]"
        >
          <AlertCircle class="mt-0.5 shrink-0" :size="18" aria-hidden="true" />
          <div>{{ error }}</div>
        </div>
        <div class="rounded-md border border-[oklch(84%_0.014_245)] bg-[oklch(99%_0.004_245)] p-3">
          <div class="mb-2 text-xs font-semibold uppercase tracking-[0.08em] text-[oklch(47%_0.024_245)]">
            Discovery command
          </div>
          <div class="overflow-x-auto rounded-md bg-[oklch(21%_0.015_245)] px-3 py-2 font-mono text-sm text-[oklch(91%_0.01_245)]">
            {{ discoverCommand.length ? discoverCommand.join(" ") : "twitter search ..." }}
          </div>
        </div>
        <div class="flex flex-wrap gap-2 text-sm text-[oklch(48%_0.024_245)]">
          <span class="rounded-md bg-[oklch(94%_0.007_245)] px-2 py-1">{{ candidates.length }} candidates</span>
          <span class="rounded-md bg-[oklch(94%_0.007_245)] px-2 py-1">{{ recommendations.length }} pending recommendations</span>
        </div>
      </div>

      <div class="min-h-0 overflow-auto pr-1">
        <div v-if="loadingDiscover || loadingAnalyze" class="grid gap-3">
          <div
            v-for="index in 4"
            :key="index"
            class="h-36 animate-pulse rounded-md border border-[oklch(87%_0.012_245)] bg-[oklch(95%_0.007_245)]"
          ></div>
        </div>

        <div v-else-if="enrichedRecommendations.length" class="grid gap-3">
          <article
            v-for="item in enrichedRecommendations"
            :key="item.id"
            class="rounded-md border border-[oklch(86%_0.012_245)] bg-[oklch(99%_0.004_245)] p-4"
          >
            <div class="flex flex-wrap items-center gap-2">
              <span
                class="inline-flex h-7 items-center rounded-md px-2 text-xs font-semibold"
                :class="actionTone(item.action)"
              >
                {{ item.actionLabel }}
              </span>
              <span class="text-sm font-semibold">{{ item.confidence }}% confidence</span>
              <span class="text-sm text-[oklch(48%_0.024_245)]">risk: {{ item.risk }}</span>
            </div>
            <p class="mt-3 text-sm leading-6 text-[oklch(34%_0.02_245)]">{{ item.reason }}</p>

            <div class="mt-4 border-t border-[oklch(88%_0.011_245)] pt-4">
              <div class="flex flex-wrap items-center gap-x-2 gap-y-1">
                <strong class="text-sm">{{ item.tweet?.author?.name || "Unknown" }}</strong>
                <span class="text-sm text-[oklch(48%_0.024_245)]">@{{ item.tweet?.author?.screenName }}</span>
                <span class="text-sm text-[oklch(58%_0.02_245)]">{{ formatDate(item.tweet?.createdAtISO) }}</span>
              </div>
              <p class="mt-2 whitespace-pre-wrap text-sm leading-6">{{ item.tweet?.text || "Source post unavailable" }}</p>
              <div class="mt-3 flex flex-wrap gap-x-4 gap-y-1 text-xs text-[oklch(47%_0.024_245)]">
                <span>{{ formatMetric(item.tweet?.metrics?.likes) }} likes</span>
                <span>{{ formatMetric(item.tweet?.metrics?.replies) }} replies</span>
                <span>{{ formatMetric(item.tweet?.metrics?.retweets) }} reposts</span>
                <span>{{ formatMetric(item.tweet?.metrics?.views) }} views</span>
              </div>
              <a
                v-if="item.postUrl"
                class="mt-3 inline-flex h-8 items-center gap-2 rounded-md border border-[oklch(82%_0.014_245)] bg-[oklch(99%_0.004_245)] px-3 text-sm font-semibold hover:bg-[oklch(94%_0.007_245)]"
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
                    class="flex cursor-pointer gap-3 rounded-md border border-[oklch(84%_0.014_245)] bg-[oklch(99%_0.004_245)] p-3 hover:bg-[oklch(96%_0.006_245)]"
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
                class="min-h-20 rounded-md border border-[oklch(82%_0.014_245)] bg-[oklch(99%_0.004_245)] px-3 py-2 leading-5"
              ></textarea>
              </label>
            </div>

            <div class="mt-4 rounded-md bg-[oklch(94%_0.007_245)] px-3 py-2 font-mono text-xs text-[oklch(38%_0.02_245)]">
              {{ recommendationCommand(item) }}
            </div>

            <div class="mt-4 flex flex-wrap gap-2">
              <button
                v-if="item.action === 'like'"
                class="inline-flex h-9 items-center gap-2 rounded-md bg-[oklch(58%_0.13_245)] px-3 text-sm font-semibold text-[oklch(98%_0.004_245)] hover:bg-[oklch(52%_0.14_245)] disabled:cursor-not-allowed disabled:opacity-55"
                :disabled="actionLoadingId === item.id"
                type="button"
                @click="approve(item)"
              >
                <Heart :size="16" aria-hidden="true" />
                Like Post
              </button>
              <button
                v-else
                class="inline-flex h-9 items-center gap-2 rounded-md border border-[oklch(82%_0.014_245)] bg-[oklch(99%_0.004_245)] px-3 text-sm font-semibold hover:bg-[oklch(94%_0.007_245)] disabled:cursor-not-allowed disabled:opacity-55"
                :disabled="actionLoadingId === item.id"
                type="button"
                @click="likePost(item)"
              >
                <Heart :size="16" aria-hidden="true" />
                Like Post
              </button>
              <button
                v-if="item.action !== 'like'"
                class="inline-flex h-9 items-center gap-2 rounded-md bg-[oklch(58%_0.13_245)] px-3 text-sm font-semibold text-[oklch(98%_0.004_245)] hover:bg-[oklch(52%_0.14_245)] disabled:cursor-not-allowed disabled:opacity-55"
                :disabled="actionLoadingId === item.id"
                type="button"
                @click="approve(item)"
              >
                <CheckCircle2 :size="16" aria-hidden="true" />
                Approve {{ growthActionLabel(item.action) }}
              </button>
              <button
                class="inline-flex h-9 items-center gap-2 rounded-md border border-[oklch(82%_0.014_245)] bg-[oklch(99%_0.004_245)] px-3 text-sm font-semibold hover:bg-[oklch(94%_0.007_245)] disabled:cursor-not-allowed disabled:opacity-55"
                :disabled="actionLoadingId === item.id"
                type="button"
                @click="reject(item)"
              >
                <X :size="16" aria-hidden="true" />
                Reject
              </button>
            </div>
          </article>
        </div>

        <div v-else-if="candidates.length" class="grid min-h-72 place-items-center rounded-md border border-dashed border-[oklch(82%_0.014_245)] text-center">
          <div class="max-w-sm">
            <div class="font-semibold">{{ recommendations.length ? "Only skip suggestions found" : "Candidates loaded" }}</div>
            <p class="mt-1 text-sm leading-6 text-[oklch(48%_0.024_245)]">
              {{
                recommendations.length
                  ? "DeepSeek did not find any like or comment actions worth showing. Adjust the search query or try again later."
                  : "Run discovery and analysis to turn these posts into like or comment recommendations."
              }}
            </p>
          </div>
        </div>

        <div v-else class="grid min-h-72 place-items-center rounded-md border border-dashed border-[oklch(82%_0.014_245)] text-center">
          <div class="max-w-sm">
            <div class="font-semibold">Discover posts to start</div>
            <p class="mt-1 text-sm leading-6 text-[oklch(48%_0.024_245)]">
              Search for AI, startup, software engineering, and founder conversations, then ask DeepSeek to rank them.
            </p>
          </div>
        </div>
      </div>
    </section>

    <aside class="border-t border-[oklch(87%_0.011_245)] bg-[oklch(96%_0.006_245)] p-4 xl:border-l xl:border-t-0">
      <div class="mb-3 flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.08em] text-[oklch(47%_0.024_245)]">
        <History :size="14" aria-hidden="true" />
        Action history
      </div>
      <div v-if="history.length" class="grid gap-3">
        <div
          v-for="record in history"
          :key="record.id"
          class="rounded-md border border-[oklch(84%_0.014_245)] bg-[oklch(99%_0.004_245)] p-3 text-sm"
        >
          <div class="flex items-center justify-between gap-3">
            <span class="font-semibold">{{ growthActionLabel(record.action) }}</span>
            <span
              class="rounded-md px-2 py-1 text-xs font-semibold"
              :class="record.status === 'approved' ? 'bg-[oklch(94%_0.034_155)] text-[oklch(34%_0.08_155)]' : 'bg-[oklch(94%_0.01_245)] text-[oklch(45%_0.024_245)]'"
            >
              {{ record.status }}
            </span>
          </div>
          <div class="mt-2 font-mono text-xs text-[oklch(48%_0.024_245)]">{{ record.tweet_id }}</div>
          <p v-if="record.comment_text" class="mt-2 leading-5">{{ record.comment_text }}</p>
        </div>
      </div>
      <div v-else class="rounded-md border border-dashed border-[oklch(82%_0.014_245)] p-4 text-sm text-[oklch(48%_0.024_245)]">
        Approved and rejected recommendations will appear here.
      </div>
    </aside>
  </main>
</template>
