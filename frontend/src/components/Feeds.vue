<script setup>
import { AlertCircle, ArrowUp, ExternalLink, RefreshCw, Repeat2 } from "@lucide/vue";
import { nextTick, onActivated, onBeforeUnmount, onDeactivated, ref } from "vue";
import { formatDate, formatMetric, tweetUrl } from "../lib/workbench";
import { mergeFeedPage, safeMediaUrl } from "../lib/feed";

const tweets = ref([]);
const cursor = ref(null);
const hasMore = ref(true);
const loading = ref(false);
const error = ref("");
const autoPaused = ref(false);
const retryRefresh = ref(false);
const sentinel = ref(null);
let visitedCursors = new Set();
let emptyPages = 0;
let active = false;
let observer;
let controller;

async function observeEnd() {
  await nextTick();
  observer?.disconnect();
  if (active && hasMore.value && !error.value && !autoPaused.value && sentinel.value) {
    observer?.observe(sentinel.value);
  }
}

async function loadMore({ refresh = false, manual = false } = {}) {
  if (!active || loading.value || (!refresh && !hasMore.value)) return;
  if (manual || refresh) {
    autoPaused.value = false;
    emptyPages = 0;
  }
  loading.value = true;
  error.value = "";
  retryRefresh.value = refresh;
  observer?.disconnect();
  controller = new AbortController();
  const requestedCursor = refresh ? null : cursor.value;
  try {
    const params = new URLSearchParams({ limit: "20" });
    if (requestedCursor) params.set("cursor", requestedCursor);
    const response = await fetch(`/api/feed?${params}`, { signal: controller.signal });
    const body = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(body.detail || "Unable to load your Twitter feed.");
    if (!Array.isArray(body.tweets)) throw new Error("Twitter returned an invalid feed page.");
    const visited = refresh ? new Set() : visitedCursors;
    const merged = mergeFeedPage(refresh ? [] : tweets.value, body, requestedCursor, visited);
    visited.add(requestedCursor);
    visitedCursors = visited;
    tweets.value = merged.tweets;
    cursor.value = merged.nextCursor;
    hasMore.value = merged.hasMore;
    emptyPages = merged.added ? 0 : emptyPages + 1;
    autoPaused.value = emptyPages >= 3;
  } catch (failure) {
    if (failure.name !== "AbortError") error.value = failure.message;
  } finally {
    loading.value = false;
    await observeEnd();
  }
}

onActivated(() => {
  active = true;
  if ("IntersectionObserver" in window) {
    observer = new IntersectionObserver((entries) => {
      if (active && !error.value && !autoPaused.value && entries.some((entry) => entry.isIntersecting) && !loading.value) loadMore();
    }, { rootMargin: "600px 0px" });
  }
  if (!tweets.value.length && !loading.value && !error.value) loadMore();
  else observeEnd();
});

function stop() {
  active = false;
  observer?.disconnect();
  controller?.abort();
}
onDeactivated(stop);
onBeforeUnmount(stop);
</script>

<template>
  <main id="feed-top" class="feeds-view">
    <header class="feeds-heading">
      <div>
        <p class="mb-2 text-xs uppercase tracking-[0.12em] text-muted">For you</p>
        <h2 class="text-2xl font-bold">Feeds</h2>
        <p class="mt-2 text-sm text-muted">Your home timeline. Keep scrolling to read more.</p>
      </div>
      <button
        type="button"
        class="inline-flex min-h-11 items-center gap-2 border border-rule-strong px-3 text-sm hover:bg-paper-shade disabled:opacity-55"
        :disabled="loading"
        @click="loadMore({ refresh: true })"
      >
        <RefreshCw :size="15" :class="{ 'animate-spin': loading }" aria-hidden="true" />
        Latest posts
      </button>
    </header>

    <div v-if="error" class="my-6 flex items-start gap-3 border border-danger-rule bg-danger-wash p-4 text-sm text-danger" role="alert">
      <AlertCircle :size="18" class="shrink-0" aria-hidden="true" />
      <div>
        <p>{{ error }}</p>
        <button class="mt-2 min-h-11 underline underline-offset-4" type="button" @click="loadMore({ manual: true, refresh: retryRefresh })">Try again</button>
      </div>
    </div>

    <section aria-label="Home timeline" :aria-busy="loading">
      <article v-for="tweet in tweets" :key="tweet.id" class="feed-post">
        <p v-if="tweet.isRetweet && tweet.retweetedBy" class="mb-3 flex items-center gap-2 text-xs text-muted">
          <Repeat2 :size="14" aria-hidden="true" /> {{ tweet.retweetedBy }} reposted
        </p>
        <header class="flex flex-wrap items-baseline gap-x-3 gap-y-1">
          <strong>{{ tweet.author?.name || tweet.author?.screenName || 'Unknown author' }}</strong>
          <span v-if="tweet.author?.screenName" class="text-sm text-muted">@{{ tweet.author.screenName }}</span>
          <time :datetime="tweet.createdAtISO || undefined" class="text-xs text-muted">{{ formatDate(tweet.createdAtISO || tweet.createdAtLocal) }}</time>
        </header>
        <p class="mt-3 whitespace-pre-wrap text-sm leading-6">{{ tweet.text }}</p>

        <blockquote v-if="tweet.quotedTweet" class="mt-4 border border-rule p-4 text-sm">
          <strong>{{ tweet.quotedTweet.author?.name || tweet.quotedTweet.author?.screenName }}</strong>
          <p class="mt-2 whitespace-pre-wrap leading-6">{{ tweet.quotedTweet.text }}</p>
        </blockquote>

        <div v-if="tweet.media?.length" class="feed-media mt-4">
          <template v-for="(media, index) in tweet.media" :key="`${tweet.id}-${index}`">
            <img
              v-if="media.type === 'photo' && safeMediaUrl(media.url)"
              :src="safeMediaUrl(media.url)"
              :width="media.width || undefined"
              :height="media.height || undefined"
              alt="Photo attached to the post"
              loading="lazy"
              decoding="async"
              referrerpolicy="no-referrer"
            />
            <a v-else :href="tweetUrl(tweet)" target="_blank" rel="noreferrer" class="inline-flex min-h-11 items-center gap-2 text-sm underline underline-offset-4">
              View {{ media.type === 'video' ? 'video' : 'media' }} on X <ExternalLink :size="14" aria-hidden="true" />
            </a>
          </template>
        </div>

        <footer class="mt-4 flex flex-wrap items-center gap-x-5 gap-y-2 text-xs text-muted">
          <span>{{ formatMetric(tweet.metrics?.likes) }} likes</span>
          <span>{{ formatMetric(tweet.metrics?.retweets) }} reposts</span>
          <span>{{ formatMetric(tweet.metrics?.replies) }} replies</span>
          <a :href="tweetUrl(tweet)" target="_blank" rel="noreferrer" class="ml-auto inline-flex min-h-11 items-center gap-2 text-ink underline underline-offset-4">
            Open on X <ExternalLink :size="14" aria-hidden="true" />
          </a>
        </footer>
      </article>
    </section>

    <div v-if="loading" class="grid gap-6 py-6" role="status" aria-label="Loading posts">
      <span class="text-sm text-muted">Loading your timeline…</span>
      <div v-if="!tweets.length" v-for="index in 3" :key="index" class="h-36 animate-pulse border-b border-rule bg-paper-shade"></div>
    </div>
    <div v-else-if="!tweets.length && !error" class="manuscript-empty">
      <div><strong>No posts returned yet</strong><p class="mt-2 text-sm text-muted">Try Latest posts to check your home timeline again.</p></div>
    </div>

    <div ref="sentinel" class="feed-sentinel" aria-hidden="true"></div>
    <div class="feed-end">
      <button v-if="hasMore && !error && !loading" type="button" class="min-h-11 border border-rule-strong px-4 text-sm hover:bg-paper-shade" @click="loadMore({ manual: true })">Load more posts</button>
      <p v-if="autoPaused && !error" class="mt-3 text-sm text-muted">No new posts in the last few pages. Load more to keep checking.</p>
      <p v-if="!hasMore && tweets.length" class="text-sm text-muted">You have reached the end of this timeline. Latest posts starts a fresh feed.</p>
      <a v-if="tweets.length" href="#feed-top" class="mt-4 inline-flex min-h-11 items-center gap-2 text-xs text-muted underline underline-offset-4"><ArrowUp :size="14" aria-hidden="true" /> Back to top</a>
    </div>
  </main>
</template>
