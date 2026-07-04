<script setup>
import {
  Activity,
  AlertCircle,
  Bookmark,
  Braces,
  CheckCircle2,
  Clipboard,
  ExternalLink,
  Heart,
  Home,
  Play,
  RefreshCw,
  Search,
  User,
} from "@lucide/vue";
import { computed, onMounted, ref, watch } from "vue";

import GrowthMode from "./components/GrowthMode.vue";
import {
  buildCommandPreview,
  buildTweetLikePayload,
  defaultOptionsForPreset,
  formatDate,
  formatMetric,
  loadWorkbenchCache,
  normalizeResult,
  saveWorkbenchCache,
  tweetUrl,
} from "./lib/workbench";

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
const likedTweetIds = ref(new Set());
const rawVisible = ref(false);
const lastRunMs = ref(null);
const copied = ref(false);
const activeTab = ref("workbench");
const cacheReady = ref(false);

const selectedPreset = computed(() =>
  presets.value.find((preset) => preset.id === selectedPresetId.value),
);

const commandPreview = computed(() =>
  buildCommandPreview(selectedPreset.value, options.value),
);

const normalized = computed(() => (result.value ? normalizeResult(result.value) : null));

const tweets = computed(() => (normalized.value?.kind === "tweets" ? normalized.value.items : []));

const rawJson = computed(() => JSON.stringify(result.value?.data ?? result.value, null, 2));

watch(
  [selectedPresetId, options, result, selectedTweetId, rawVisible, lastRunMs, likedTweetIds],
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
    selectedTweetId.value = normalizedBody.kind === "tweets" ? normalizedBody.items[0]?.id : null;
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

async function likeTweet(tweet) {
  if (!tweet?.id || tweetActionLoadingId.value) return;
  tweetActionLoadingId.value = tweet.id;
  error.value = "";
  try {
    const response = await fetch("/api/growth/approve", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(buildTweetLikePayload(tweet)),
    });
    const body = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(body.detail || "Unable to like post");
    likedTweetIds.value = new Set([...likedTweetIds.value, tweet.id]);
    persistWorkbenchCache();
  } catch (failure) {
    error.value = failure.message;
  } finally {
    tweetActionLoadingId.value = null;
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
  <div class="min-h-screen px-4 py-4 text-[oklch(24%_0.018_245)] sm:px-6 lg:px-8">
    <div class="mx-auto flex max-w-[1540px] flex-col gap-4">
      <header
        class="flex flex-col gap-3 border-b border-[oklch(86%_0.012_245)] pb-4 lg:flex-row lg:items-center lg:justify-between"
      >
        <div>
          <div class="flex items-center gap-3">
            <div
              class="grid h-9 w-9 place-items-center rounded-md bg-[oklch(23%_0.016_245)] text-[oklch(96%_0.006_245)]"
            >
              <Braces :size="18" aria-hidden="true" />
            </div>
            <div>
              <h1 class="text-xl font-semibold tracking-normal">Twitter CLI Workbench</h1>
              <p class="text-sm text-[oklch(48%_0.024_245)]">
                Run local <span class="font-mono">twitter</span> commands and inspect live structured output.
              </p>
            </div>
          </div>
        </div>
        <div class="flex flex-wrap items-center gap-2">
          <div class="mr-1 flex rounded-md border border-[oklch(82%_0.014_245)] bg-[oklch(99%_0.004_245)] p-1">
            <button
              class="h-7 rounded px-3 text-sm font-medium"
              :class="activeTab === 'workbench' ? 'bg-[oklch(90%_0.038_245)] text-[oklch(30%_0.08_245)]' : 'text-[oklch(48%_0.024_245)] hover:bg-[oklch(94%_0.007_245)]'"
              type="button"
              @click="activeTab = 'workbench'"
            >
              Workbench
            </button>
            <button
              class="h-7 rounded px-3 text-sm font-medium"
              :class="activeTab === 'growth' ? 'bg-[oklch(90%_0.038_245)] text-[oklch(30%_0.08_245)]' : 'text-[oklch(48%_0.024_245)] hover:bg-[oklch(94%_0.007_245)]'"
              type="button"
              @click="activeTab = 'growth'"
            >
              Growth Mode
            </button>
          </div>
          <span
            class="inline-flex h-8 items-center gap-2 rounded-md border border-[oklch(82%_0.026_155)] bg-[oklch(94%_0.034_155)] px-3 text-sm font-medium text-[oklch(34%_0.08_155)]"
          >
            <CheckCircle2 :size="15" aria-hidden="true" />
            Local CLI
          </span>
          <button
            class="inline-flex h-8 items-center gap-2 rounded-md border border-[oklch(82%_0.014_245)] bg-[oklch(98%_0.004_245)] px-3 text-sm font-medium hover:bg-[oklch(94%_0.007_245)] disabled:cursor-not-allowed disabled:opacity-55"
            :disabled="loading || bootLoading"
            type="button"
            @click="runCommand"
          >
            <RefreshCw :class="{ 'animate-spin': loading }" :size="15" aria-hidden="true" />
            Refresh
          </button>
        </div>
      </header>

      <main
        v-if="activeTab === 'workbench'"
        class="grid min-h-[calc(100vh-112px)] overflow-hidden rounded-lg border border-[oklch(85%_0.012_245)] bg-[oklch(98%_0.004_245)] shadow-sm lg:grid-cols-[260px_minmax(0,1fr)]"
      >
        <aside class="border-b border-[oklch(87%_0.011_245)] bg-[oklch(94%_0.007_245)] p-4 lg:border-b-0 lg:border-r">
          <div class="mb-3 text-xs font-semibold uppercase tracking-[0.08em] text-[oklch(47%_0.024_245)]">
            Presets
          </div>
          <div class="grid gap-2">
            <button
              v-for="preset in presets"
              :key="preset.id"
              class="flex min-h-12 items-center gap-3 rounded-md border px-3 text-left transition hover:bg-[oklch(98%_0.004_245)]"
              :class="
                preset.id === selectedPresetId
                  ? 'border-[oklch(74%_0.07_245)] bg-[oklch(90%_0.038_245)] text-[oklch(30%_0.08_245)]'
                  : 'border-transparent bg-transparent text-[oklch(35%_0.02_245)]'
              "
              type="button"
              @click="selectPreset(preset.id)"
            >
              <component :is="iconMap[preset.id] || Braces" :size="17" aria-hidden="true" />
              <span>
                <span class="block text-sm font-semibold">{{ preset.label }}</span>
                <span class="block text-xs text-[oklch(49%_0.024_245)]">{{ preset.description }}</span>
              </span>
            </button>
          </div>

          <div class="mt-6 text-xs font-semibold uppercase tracking-[0.08em] text-[oklch(47%_0.024_245)]">
            Options
          </div>
          <div class="mt-3 grid gap-3">
            <label v-for="field in selectedPreset?.fields" :key="field.name" class="grid gap-1.5 text-sm">
              <span class="font-medium">{{ field.label }}</span>
              <input
                v-if="field.type === 'number'"
                v-model.number="options[field.name]"
                class="h-9 rounded-md border border-[oklch(82%_0.014_245)] bg-[oklch(99%_0.004_245)] px-3"
                :max="field.max"
                :min="field.min"
                type="number"
              />
              <input
                v-else
                v-model="options[field.name]"
                class="h-9 rounded-md border border-[oklch(82%_0.014_245)] bg-[oklch(99%_0.004_245)] px-3"
                :placeholder="field.required ? 'Required' : ''"
                type="text"
              />
            </label>
            <p v-if="!selectedPreset?.fields?.length" class="text-sm text-[oklch(48%_0.024_245)]">
              No options required for this command.
            </p>
          </div>
        </aside>

        <section class="grid min-h-[560px] grid-rows-[auto_auto_1fr] gap-4 overflow-hidden p-4">
          <div class="rounded-md border border-[oklch(84%_0.014_245)] bg-[oklch(99%_0.004_245)] p-3">
            <div class="mb-2 text-xs font-semibold uppercase tracking-[0.08em] text-[oklch(47%_0.024_245)]">
              Command
            </div>
            <div
              class="overflow-x-auto rounded-md bg-[oklch(21%_0.015_245)] px-3 py-2 font-mono text-sm text-[oklch(91%_0.01_245)]"
            >
              {{ commandPreview }}
            </div>
          </div>

          <div class="flex flex-wrap items-center gap-2">
            <button
              class="inline-flex h-9 items-center gap-2 rounded-md bg-[oklch(58%_0.13_245)] px-4 text-sm font-semibold text-[oklch(98%_0.004_245)] hover:bg-[oklch(52%_0.14_245)] disabled:cursor-not-allowed disabled:opacity-55"
              :disabled="loading || bootLoading"
              type="button"
              @click="runCommand"
            >
              <Play :size="16" aria-hidden="true" />
              {{ loading ? "Running" : "Run" }}
            </button>
            <button
              class="inline-flex h-9 items-center gap-2 rounded-md border border-[oklch(82%_0.014_245)] bg-[oklch(99%_0.004_245)] px-3 text-sm font-medium hover:bg-[oklch(94%_0.007_245)]"
              type="button"
              @click="rawVisible = !rawVisible"
            >
              <Braces :size="16" aria-hidden="true" />
              {{ rawVisible ? "Cards" : "JSON" }}
            </button>
            <button
              class="inline-flex h-9 items-center gap-2 rounded-md border border-[oklch(82%_0.014_245)] bg-[oklch(99%_0.004_245)] px-3 text-sm font-medium hover:bg-[oklch(94%_0.007_245)]"
              type="button"
              @click="copyCommand"
            >
              <Clipboard :size="16" aria-hidden="true" />
              {{ copied ? "Copied" : "Copy command" }}
            </button>
            <span class="ml-auto text-sm text-[oklch(48%_0.024_245)]" v-if="lastRunMs">
              Last run {{ (lastRunMs / 1000).toFixed(1) }}s
            </span>
          </div>

          <div class="min-h-0 overflow-auto pr-1">
            <div
              v-if="error"
              class="flex items-start gap-3 rounded-md border border-[oklch(79%_0.052_30)] bg-[oklch(96%_0.025_30)] p-4 text-sm text-[oklch(36%_0.075_30)]"
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
                class="h-28 animate-pulse rounded-md border border-[oklch(87%_0.012_245)] bg-[oklch(95%_0.007_245)]"
              ></div>
            </div>

            <pre
              v-else-if="rawVisible && result"
              class="min-h-full overflow-auto rounded-md bg-[oklch(21%_0.015_245)] p-4 font-mono text-xs leading-5 text-[oklch(91%_0.01_245)]"
              >{{ rawJson }}</pre
            >

            <div v-else-if="tweets.length" class="grid gap-3">
              <article
                v-for="tweet in tweets"
                :key="tweet.id"
                class="cursor-pointer rounded-md border bg-[oklch(99%_0.004_245)] p-4 transition hover:border-[oklch(74%_0.07_245)]"
                :class="
                  selectedTweetId === tweet.id
                    ? 'border-[oklch(66%_0.1_245)]'
                    : 'border-[oklch(86%_0.012_245)]'
                "
                @click="selectedTweetId = tweet.id"
              >
                <div class="flex items-start gap-3">
                  <img
                    v-if="tweet.author?.profileImageUrl"
                    class="h-10 w-10 rounded-md"
                    :src="tweet.author.profileImageUrl"
                    alt=""
                  />
                  <div
                    v-else
                    class="grid h-10 w-10 shrink-0 place-items-center rounded-md bg-[oklch(90%_0.038_245)] font-semibold"
                  >
                    {{ tweet.author?.name?.slice(0, 1) || "T" }}
                  </div>
                  <div class="min-w-0 flex-1">
                    <div class="flex flex-wrap items-center gap-x-2 gap-y-1">
                      <strong class="text-sm">{{ tweet.author?.name || "Unknown" }}</strong>
                      <span class="text-sm text-[oklch(48%_0.024_245)]">@{{ tweet.author?.screenName }}</span>
                      <span class="text-sm text-[oklch(58%_0.02_245)]">{{ formatDate(tweet.createdAtISO || tweet.createdAtLocal) }}</span>
                      <span
                        v-if="tweet.author?.verified"
                        class="rounded bg-[oklch(91%_0.045_245)] px-1.5 py-0.5 text-xs font-medium text-[oklch(34%_0.08_245)]"
                      >
                        verified
                      </span>
                    </div>
                    <p class="mt-2 whitespace-pre-wrap text-sm leading-6">{{ tweet.text }}</p>
                    <div class="mt-3 flex flex-wrap gap-x-4 gap-y-1 text-xs text-[oklch(47%_0.024_245)]">
                      <span>{{ formatMetric(tweet.metrics?.likes) }} likes</span>
                      <span>{{ formatMetric(tweet.metrics?.retweets) }} reposts</span>
                      <span>{{ formatMetric(tweet.metrics?.replies) }} replies</span>
                      <span>{{ formatMetric(tweet.metrics?.views) }} views</span>
                      <span v-if="tweet.media?.length">{{ tweet.media.length }} media</span>
                    </div>
                    <div class="mt-3 flex flex-wrap gap-2">
                      <button
                        class="inline-flex h-8 items-center gap-2 rounded-md border border-[oklch(82%_0.014_245)] bg-[oklch(99%_0.004_245)] px-3 text-sm font-semibold hover:bg-[oklch(94%_0.007_245)] disabled:cursor-not-allowed disabled:opacity-55"
                        :disabled="tweetActionLoadingId === tweet.id || likedTweetIds.has(tweet.id)"
                        type="button"
                        @click.stop="likeTweet(tweet)"
                      >
                        <Heart :size="15" aria-hidden="true" />
                        {{
                          likedTweetIds.has(tweet.id)
                            ? "Liked"
                            : tweetActionLoadingId === tweet.id
                              ? "Liking"
                              : "Like Post"
                        }}
                      </button>
                      <a
                        v-if="tweetUrl(tweet)"
                        class="inline-flex h-8 items-center gap-2 rounded-md border border-[oklch(82%_0.014_245)] bg-[oklch(99%_0.004_245)] px-3 text-sm font-semibold hover:bg-[oklch(94%_0.007_245)]"
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
              class="rounded-md border border-[oklch(86%_0.012_245)] bg-[oklch(99%_0.004_245)] p-4"
            >
              <pre class="overflow-auto font-mono text-xs leading-5">{{ JSON.stringify(normalized.value, null, 2) }}</pre>
            </div>

            <div
              v-else
              class="grid min-h-64 place-items-center rounded-md border border-dashed border-[oklch(82%_0.014_245)] text-center"
            >
              <div>
                <div class="font-semibold">No output yet</div>
                <p class="mt-1 text-sm text-[oklch(48%_0.024_245)]">Run a preset to fetch live CLI data.</p>
              </div>
            </div>
          </div>
        </section>
      </main>
      <GrowthMode v-else />
    </div>
  </div>
</template>
