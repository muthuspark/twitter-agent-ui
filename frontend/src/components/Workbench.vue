<script setup>
import {
  Activity,
  AlertCircle,
  Bookmark,
  Braces,
  Clipboard,
  ExternalLink,
  Heart,
  Home,
  Play,
  Search,
  User,
} from "@lucide/vue";
import { computed, onMounted, ref, watch } from "vue";

import {
  buildCommandPreview,
  buildTweetActionPayload,
  defaultOptionsForPreset,
  formatDate,
  formatMetric,
  getTweetsUnderLikeThreshold,
  loadWorkbenchCache,
  normalizeResult,
  saveWorkbenchCache,
  tweetUrl,
} from "../lib/workbench";

const iconMap = {
  feed: Home,
  search: Search,
  bookmarks: Bookmark,
  status: Activity,
  whoami: User,
};

const presets = ref([]);
const selectedPresetId = ref("feed");
const options = ref({});
const loading = ref(false);
const bootLoading = ref(true);
const error = ref("");
const result = ref(null);
const selectedTweetId = ref(null);
const tweetActionLoadingId = ref(null);
const tweetAction = ref(null);
const bookmarkedTweetIds = ref(new Set());
const bulkLikeLoading = ref(false);
const bulkLikeCompleted = ref(0);
const bulkLikeTotal = ref(0);
const likedTweetIds = ref(new Set());
const rawVisible = ref(false);
const lastRunMs = ref(null);
const copied = ref(false);
const cacheReady = ref(false);

const selectedPreset = computed(() =>
  presets.value.find((preset) => preset.id === selectedPresetId.value),
);

const commandPreview = computed(() =>
  buildCommandPreview(selectedPreset.value, options.value),
);

const normalized = computed(() =>
  result.value ? normalizeResult(result.value) : null,
);

const tweets = computed(() =>
  normalized.value?.kind === "tweets" ? normalized.value.items : [],
);

const lowLikeTweets = computed(() =>
  getTweetsUnderLikeThreshold(tweets.value, likedTweetIds.value, 20),
);

const bulkLikeLabel = computed(() => {
  if (bulkLikeLoading.value)
    return `Liking ${bulkLikeCompleted.value}/${bulkLikeTotal.value}`;
  return `Like <20 (${lowLikeTweets.value.length})`;
});

const rawJson = computed(() =>
  JSON.stringify(result.value?.data ?? result.value, null, 2),
);

watch(
  [
    selectedPresetId,
    options,
    result,
    selectedTweetId,
    rawVisible,
    lastRunMs,
    likedTweetIds,
    bookmarkedTweetIds,
  ],
  () => {
    if (cacheReady.value) persistWorkbenchCache();
  },
  { deep: true },
);

async function loadPresets() {
  bootLoading.value = true;
  try {
    const response = await fetch("/api/presets");
    if (!response.ok) throw new Error("Unable to load command presets");
    const body = await response.json();
    presets.value = body.presets;
    selectedPresetId.value = body.presets[0]?.id ?? "feed";
    options.value = defaultOptionsForPreset(body.presets[0]);
  } catch (failure) {
    error.value = failure.message;
  } finally {
    bootLoading.value = false;
  }
}

function selectPreset(presetId) {
  selectedPresetId.value = presetId;
  const preset = presets.value.find((entry) => entry.id === presetId);
  options.value = defaultOptionsForPreset(preset);
  error.value = "";
}

async function runCommand() {
  if (!selectedPreset.value || loading.value) return;
  loading.value = true;
  error.value = "";
  copied.value = false;
  const startedAt = performance.now();

  try {
    const response = await fetch("/api/run", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        preset: selectedPreset.value.id,
        options: options.value,
      }),
    });
    const body = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(body.detail || "Command failed");
    }
    result.value = body;
    const normalizedBody = normalizeResult(body);
    selectedTweetId.value =
      normalizedBody.kind === "tweets" ? normalizedBody.items[0]?.id : null;
    lastRunMs.value = Math.round(performance.now() - startedAt);
    persistWorkbenchCache();
  } catch (failure) {
    error.value = failure.message;
  } finally {
    loading.value = false;
  }
}

async function copyCommand() {
  await navigator.clipboard.writeText(commandPreview.value);
  copied.value = true;
  window.setTimeout(() => {
    copied.value = false;
  }, 1600);
}

async function runTweetAction(tweet, action) {
  if (!tweet?.id || tweetActionLoadingId.value) return;
  tweetActionLoadingId.value = tweet.id;
  tweetAction.value = action;
  error.value = "";
  try {
    const response = await fetch("/api/growth/approve", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(buildTweetActionPayload(tweet, action)),
    });
    const body = await response.json().catch(() => ({}));
    if (!response.ok)
      throw new Error(body.detail || `Unable to ${action} post`);
    const completedIds =
      action === "bookmark" ? bookmarkedTweetIds : likedTweetIds;
    completedIds.value = new Set([...completedIds.value, tweet.id]);
    persistWorkbenchCache();
  } catch (failure) {
    error.value = failure.message;
  } finally {
    tweetActionLoadingId.value = null;
    tweetAction.value = null;
  }
}

async function likeLoadedLowLikeTweets() {
  if (
    bulkLikeLoading.value ||
    tweetActionLoadingId.value ||
    !lowLikeTweets.value.length
  )
    return;
  bulkLikeLoading.value = true;
  bulkLikeCompleted.value = 0;
  error.value = "";
  const likedIds = new Set(likedTweetIds.value);
  const queue = [...lowLikeTweets.value];
  bulkLikeTotal.value = queue.length;

  try {
    for (const tweet of queue) {
      tweetActionLoadingId.value = tweet.id;
      tweetAction.value = "like";
      const response = await fetch("/api/growth/approve", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(buildTweetActionPayload(tweet)),
      });
      const body = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(body.detail || "Unable to like post");
      likedIds.add(tweet.id);
      likedTweetIds.value = new Set(likedIds);
      bulkLikeCompleted.value += 1;
      persistWorkbenchCache();
    }
  } catch (failure) {
    error.value = failure.message;
  } finally {
    tweetActionLoadingId.value = null;
    tweetAction.value = null;
    bulkLikeLoading.value = false;
  }
}

function currentWorkbenchCacheState() {
  return {
    selectedPresetId: selectedPresetId.value,
    options: options.value,
    result: result.value,
    selectedTweetId: selectedTweetId.value,
    rawVisible: rawVisible.value,
    lastRunMs: lastRunMs.value,
    likedTweetIds: [...likedTweetIds.value],
    bookmarkedTweetIds: [...bookmarkedTweetIds.value],
  };
}

function persistWorkbenchCache() {
  saveWorkbenchCache(window.localStorage, currentWorkbenchCacheState());
}

function restoreWorkbenchCache() {
  const cached = loadWorkbenchCache(window.localStorage);
  if (!cached) return false;
  selectedPresetId.value = cached.selectedPresetId;
  options.value = cached.options;
  result.value = cached.result;
  selectedTweetId.value = cached.selectedTweetId;
  rawVisible.value = cached.rawVisible;
  lastRunMs.value = cached.lastRunMs;
  likedTweetIds.value = new Set(cached.likedTweetIds);
  bookmarkedTweetIds.value = new Set(cached.bookmarkedTweetIds);
  return true;
}

onMounted(async () => {
  await loadPresets();
  const restored = restoreWorkbenchCache();
  cacheReady.value = true;
  if (!error.value && !restored) {
    await runCommand();
  }
});
</script>

<template>
  <main class="manuscript-layout workbench-layout">
    <aside class="manuscript-sidebar">
      <nav class="preset-list" aria-label="Workbench commands">
        <button
          v-for="preset in presets"
          :key="preset.id"
          class="flex min-h-12 items-center gap-3 rounded-sm border px-3 text-left transition hover:bg-paper"
          :class="
            preset.id === selectedPresetId
              ? 'border-transparent bg-paper-shade text-ink'
              : 'border-transparent bg-transparent text-ink-secondary'
          "
          type="button"
          :aria-pressed="preset.id === selectedPresetId"
          @click="selectPreset(preset.id)"
        >
          <component
            :is="iconMap[preset.id] || Braces"
            :size="17"
            aria-hidden="true"
          />
          <span>
            <span class="block text-sm font-semibold">{{ preset.label }}</span>
          </span>
        </button>
      </nav>

      <div class="preset-options mt-6 grid gap-3">
        <label
          v-for="field in selectedPreset?.fields"
          :key="field.name"
          class="grid gap-1.5 text-sm"
        >
          <span class="font-medium">{{ field.label }}</span>
          <input
            v-if="field.type === 'number'"
            v-model.number="options[field.name]"
            class="h-9 rounded-sm border border-rule-strong bg-paper px-3"
            :max="field.max"
            :min="field.min"
            type="number"
          />
          <input
            v-else
            v-model="options[field.name]"
            class="h-9 rounded-sm border border-rule-strong bg-paper px-3"
            :placeholder="field.required ? 'Required' : ''"
            type="text"
          />
        </label>
      </div>
    </aside>

    <section class="manuscript-content">
      <div class="workbench-command">
        <h2 class="mb-5 text-2xl font-bold">
          {{ selectedPreset?.label || "Workbench" }}
        </h2>
        <div
          class="overflow-x-auto rounded-sm command-sheet bg-paper-shade px-3 py-2 font-mono text-sm text-ink"
        >
          {{ commandPreview }}
        </div>
      </div>

      <div class="workbench-toolbar flex flex-wrap items-center gap-2">
        <button
          class="button button-primary"
          :disabled="loading || bootLoading"
          type="button"
          @click="runCommand"
        >
          <Play :size="16" aria-hidden="true" />
          {{ loading ? "Running" : "Run" }}
        </button>
        <button class="button" type="button" @click="rawVisible = !rawVisible">
          <Braces :size="16" aria-hidden="true" />
          {{ rawVisible ? "Results" : "Raw JSON" }}
        </button>
        <button class="button" type="button" @click="copyCommand">
          <Clipboard :size="16" aria-hidden="true" />
          {{ copied ? "Copied" : "Copy command" }}
        </button>
        <button
          class="button"
          :disabled="
            loading ||
            bootLoading ||
            bulkLikeLoading ||
            tweetActionLoadingId ||
            !lowLikeTweets.length
          "
          type="button"
          @click="likeLoadedLowLikeTweets"
        >
          <Heart :size="16" aria-hidden="true" />
          {{ bulkLikeLabel }}
        </button>
        <span class="run-timing ml-auto text-xs text-muted" v-if="lastRunMs">
          {{ (lastRunMs / 1000).toFixed(1) }}s
        </span>
      </div>

      <div class="results-region">
        <div
          v-if="error"
          class="flex items-start gap-3 rounded-sm border border-danger-rule bg-danger-wash p-4 text-sm text-danger"
        >
          <AlertCircle class="mt-0.5 shrink-0" :size="18" aria-hidden="true" />
          <div>
            <div class="font-semibold">Command failed</div>
            <div>{{ error }}</div>
          </div>
        </div>

        <div v-else-if="bootLoading || loading" class="grid gap-3">
          <div
            v-for="index in 4"
            :key="index"
            class="h-28 animate-pulse rounded-sm border border-rule bg-paper-shade"
          ></div>
        </div>

        <pre
          v-else-if="rawVisible && result"
          class="min-h-full overflow-auto rounded-sm command-sheet bg-paper-shade p-4 font-mono text-xs leading-5 text-ink"
          >{{ rawJson }}</pre
        >

        <div v-else-if="tweets.length" class="manuscript-posts">
          <article
            v-for="tweet in tweets"
            :key="tweet.id"
            class="manuscript-post cursor-pointer border-b bg-paper py-6 transition hover:bg-paper-shade"
            :class="
              selectedTweetId === tweet.id
                ? 'border-rule bg-paper-shade'
                : 'border-rule'
            "
            @click="selectedTweetId = tweet.id"
          >
            <div class="flex items-start gap-3">
              <div class="min-w-0 flex-1">
                <div class="flex flex-wrap items-center gap-x-2 gap-y-1">
                  <strong class="text-sm">{{
                    tweet.author?.name || "Unknown"
                  }}</strong>
                  <span class="text-sm text-muted"
                    >@{{ tweet.author?.screenName }}</span
                  >
                  <span class="text-sm text-muted">{{
                    formatDate(tweet.createdAtISO || tweet.createdAtLocal)
                  }}</span>
                  <span
                    v-if="tweet.author?.verified"
                    class="rounded bg-accent-wash px-1.5 py-0.5 text-xs font-medium text-accent"
                  >
                    verified
                  </span>
                </div>
                <p class="mt-2 whitespace-pre-wrap text-sm leading-6">
                  {{ tweet.text }}
                </p>
                <div
                  class="mt-3 flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted"
                >
                  <span>{{ formatMetric(tweet.metrics?.likes) }} likes</span>
                  <span
                    >{{ formatMetric(tweet.metrics?.retweets) }} reposts</span
                  >
                  <span
                    >{{ formatMetric(tweet.metrics?.replies) }} replies</span
                  >
                  <span>{{ formatMetric(tweet.metrics?.views) }} views</span>
                  <span v-if="tweet.media?.length"
                    >{{ tweet.media.length }} media</span
                  >
                </div>
                <div class="mt-3 flex flex-wrap gap-2">
                  <button
                    class="button"
                    :disabled="
                      Boolean(tweetActionLoadingId) ||
                      likedTweetIds.has(tweet.id)
                    "
                    type="button"
                    @click.stop="runTweetAction(tweet, 'like')"
                  >
                    <Heart :size="15" aria-hidden="true" />
                    {{
                      likedTweetIds.has(tweet.id)
                        ? "Liked"
                        : tweetActionLoadingId === tweet.id &&
                            tweetAction === "like"
                          ? "Liking"
                          : "Like"
                    }}
                  </button>
                  <button
                    class="button"
                    :disabled="
                      Boolean(tweetActionLoadingId) ||
                      bookmarkedTweetIds.has(tweet.id)
                    "
                    type="button"
                    @click.stop="runTweetAction(tweet, 'bookmark')"
                  >
                    <Bookmark :size="15" aria-hidden="true" />
                    {{
                      bookmarkedTweetIds.has(tweet.id)
                        ? "Bookmarked"
                        : tweetActionLoadingId === tweet.id &&
                            tweetAction === "bookmark"
                          ? "Bookmarking"
                          : "Bookmark"
                    }}
                  </button>
                  <a
                    v-if="tweetUrl(tweet)"
                    class="button"
                    :href="tweetUrl(tweet)"
                    rel="noreferrer"
                    target="_blank"
                    @click.stop
                  >
                    <ExternalLink :size="15" aria-hidden="true" />
                    Link
                  </a>
                </div>
              </div>
            </div>
          </article>
        </div>

        <div
          v-else-if="normalized?.kind === 'json'"
          class="rounded-sm border border-rule bg-paper p-4"
        >
          <pre class="overflow-auto font-mono text-xs leading-5">{{
            JSON.stringify(normalized.value, null, 2)
          }}</pre>
        </div>

        <div v-else class="manuscript-empty">
          <div>
            <div class="font-semibold">No results</div>
          </div>
        </div>
      </div>
    </section>
  </main>
</template>
