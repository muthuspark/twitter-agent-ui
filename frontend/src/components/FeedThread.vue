<script setup>
import { Bookmark, ExternalLink, Heart, X } from "@lucide/vue";
import {
  computed,
  nextTick,
  onActivated,
  onBeforeUnmount,
  onDeactivated,
  onMounted,
  ref,
  watch,
} from "vue";
import { createFeedBlockMatcher } from "../lib/blocklist";
import { isEnglishFeedPost, mediaAltText, mergeFeedPage, safeMediaUrl } from "../lib/feed";
import { formatDate, formatMetric } from "../lib/format";
import { tweetUrl } from "../lib/social";
import ImageLightbox from "./ImageLightbox.vue";

const props = defineProps({
  post: { type: Object, required: true },
  blockedTerms: { type: Array, default: () => [] },
  likedIds: { type: Set, required: true },
  bookmarkedIds: { type: Set, required: true },
  pendingActions: { type: Object, required: true },
  actionErrors: { type: Object, required: true },
});
defineEmits(["close", "action"]);

const panel = ref(null);
const items = ref([]);
const cursor = ref(null);
const hasMore = ref(true);
const loading = ref(false);
const error = ref("");
let visited = new Set();
let controller;
let requestVersion = 0;
let fitFrame = null;
const blockMatcher = computed(() => createFeedBlockMatcher(props.blockedTerms));
const conversation = computed(() =>
  items.value.filter(
    (tweet) =>
      String(tweet.id) !== String(props.post.id) &&
      isEnglishFeedPost(tweet) &&
      !blockMatcher.value(tweet),
  ),
);

async function loadMore() {
  if (loading.value || !hasMore.value) return;
  const version = ++requestVersion;
  const postId = String(props.post.id);
  const requestedCursor = cursor.value;
  controller = new AbortController();
  loading.value = true;
  error.value = "";
  try {
    const params = new URLSearchParams({ limit: "20" });
    if (requestedCursor) params.set("cursor", requestedCursor);
    const response = await fetch(
      `/api/feed/thread/${encodeURIComponent(postId)}?${params}`,
      { signal: controller.signal },
    );
    const body = await response.json().catch(() => ({}));
    if (!response.ok)
      throw new Error(body.detail || "Unable to load this conversation.");
    if (!Array.isArray(body.tweets))
      throw new Error("Twitter returned an invalid conversation.");
    if (version !== requestVersion) return;
    const merged = mergeFeedPage(items.value, body, requestedCursor, visited);
    visited.add(requestedCursor);
    items.value = merged.tweets;
    cursor.value = merged.nextCursor;
    hasMore.value = merged.hasMore;
  } catch (failure) {
    if (version === requestVersion && failure.name !== "AbortError")
      error.value = failure.message;
  } finally {
    if (version === requestVersion) loading.value = false;
  }
}

function stop() {
  ++requestVersion;
  controller?.abort();
  loading.value = false;
}

function fitPanel() {
  if (!panel.value) return;
  if (window.matchMedia("(max-width: 899px)").matches) {
    panel.value.style.removeProperty("max-height");
    return;
  }
  const top = Math.max(16, panel.value.getBoundingClientRect().top);
  const height = `${Math.max(160, window.innerHeight - top - 16)}px`;
  if (panel.value.style.maxHeight !== height) panel.value.style.maxHeight = height;
}

function scheduleFit() {
  if (fitFrame !== null) return;
  fitFrame = window.requestAnimationFrame(() => {
    fitFrame = null;
    fitPanel();
  });
}

function activate() {
  window.addEventListener("scroll", scheduleFit, { capture: true, passive: true });
  window.addEventListener("resize", scheduleFit);
  nextTick(scheduleFit);
  if (!items.value.length && !loading.value && !error.value) loadMore();
}

function deactivate() {
  stop();
  window.removeEventListener("scroll", scheduleFit, true);
  window.removeEventListener("resize", scheduleFit);
  window.cancelAnimationFrame(fitFrame);
  fitFrame = null;
}

watch(
  () => props.post.id,
  () => {
    stop();
    items.value = [];
    cursor.value = null;
    hasMore.value = true;
    error.value = "";
    visited = new Set();
    nextTick(() => panel.value?.scrollTo({ top: 0 }));
    loadMore();
  },
  { immediate: true },
);

onMounted(activate);
onActivated(activate);
onDeactivated(deactivate);
onBeforeUnmount(deactivate);
</script>

<template>
  <aside
    id="feed-thread"
    ref="panel"
    class="feed-thread"
    aria-labelledby="feed-thread-heading"
  >
    <header class="thread-heading">
      <div>
        <h2 id="feed-thread-heading" tabindex="-1" class="text-xl font-bold">
          Thread<span v-if="conversation.length">, {{ conversation.length }} {{ conversation.length === 1 ? "reply" : "replies" }}</span>
        </h2>

      </div>
      <button
        type="button"
        aria-label="Close thread"
        title="Close thread"
        class="button button-quiet button-icon button-icon-compact shrink-0"
        @click="$emit('close')"
      >
        <X :size="18" aria-hidden="true" />
      </button>
    </header>

    <section aria-label="Post conversation" :aria-busy="loading">
      <article
        v-for="tweet in conversation"
        :key="tweet.id"
        class="feed-post thread-post"
        :data-post-id="tweet.id"
      >
        <header class="flex flex-wrap items-baseline gap-x-2 gap-y-1">
          <strong class="text-base">{{
            tweet.author?.name || tweet.author?.screenName || "Unknown author"
          }}</strong>
          <span v-if="tweet.author?.screenName" class="text-sm text-muted"
            >@{{ tweet.author.screenName }}</span
          >
          <time
            class="text-sm text-muted"
            :datetime="tweet.createdAtISO || undefined"
            >{{ formatDate(tweet.createdAtISO || tweet.createdAtLocal) }}</time
          >
        </header>
        <p
          data-feed-text
          tabindex="-1"
          class="mt-3 whitespace-pre-wrap text-base leading-6"
        >
          {{ tweet.text }}
        </p>
        <blockquote
          v-if="tweet.quotedTweet"
          class="mt-4 border border-rule p-3 text-base"
        >
          <strong>{{
            tweet.quotedTweet.author?.name ||
            tweet.quotedTweet.author?.screenName
          }}</strong>
          <p
            data-feed-text
            tabindex="-1"
            class="mt-2 whitespace-pre-wrap leading-6"
          >
            {{ tweet.quotedTweet.text }}
          </p>
        </blockquote>
        <div v-if="tweet.media?.length" class="feed-media mt-3">
          <template v-for="(media, index) in tweet.media" :key="index">
            <ImageLightbox
              v-if="media.type === 'photo' && safeMediaUrl(media.url)"
              :src="safeMediaUrl(media.url)"
              :alt="mediaAltText(media, index)"
            />
            <a
              v-else
              :href="tweetUrl(tweet)"
              target="_blank"
              rel="noreferrer"
              class="inline-flex min-h-11 items-center gap-2 text-xs underline underline-offset-4"
              >View media on X <ExternalLink :size="13" aria-hidden="true"
            /></a>
          </template>
        </div>
        <footer class="feed-post-footer mt-3">
        <div class="feed-post-metrics">
          <span>{{ formatMetric(tweet.metrics?.likes) }} likes</span
          ><span>{{ formatMetric(tweet.metrics?.retweets) }} reposts</span
          ><span>{{ formatMetric(tweet.metrics?.replies) }} replies</span>
        </div>
        <div class="feed-post-actions flex items-center">
          <button
            type="button"
            class="button button-quiet button-icon button-icon-compact"
            :aria-label="likedIds.has(String(tweet.id)) ? 'Liked' : pendingActions[tweet.id] === 'like' ? 'Liking…' : 'Like'"
            :title="likedIds.has(String(tweet.id)) ? 'Liked' : 'Like'"
            :disabled="
              Boolean(pendingActions[tweet.id]) ||
              likedIds.has(String(tweet.id))
            "
            :aria-pressed="likedIds.has(String(tweet.id))"
            @click="$emit('action', tweet, 'like')"
          >
            <Heart :size="18" :fill="likedIds.has(String(tweet.id)) ? 'currentColor' : 'none'" aria-hidden="true" />
          </button>
          <button
            type="button"
            class="button button-quiet button-icon button-icon-compact"
            :aria-label="bookmarkedIds.has(String(tweet.id)) ? 'Bookmarked' : pendingActions[tweet.id] === 'bookmark' ? 'Saving…' : 'Bookmark'"
            :title="bookmarkedIds.has(String(tweet.id)) ? 'Bookmarked' : 'Bookmark'"
            :disabled="
              Boolean(pendingActions[tweet.id]) ||
              bookmarkedIds.has(String(tweet.id))
            "
            :aria-pressed="bookmarkedIds.has(String(tweet.id))"
            @click="$emit('action', tweet, 'bookmark')"
          >
            <Bookmark :size="18" :fill="bookmarkedIds.has(String(tweet.id)) ? 'currentColor' : 'none'" aria-hidden="true" />
          </button>
          <a
            :href="tweetUrl(tweet)"
            target="_blank"
            rel="noreferrer"
            class="button button-quiet button-icon button-icon-compact"
            aria-label="Open on X"
            title="Open on X"
            ><ExternalLink :size="18" aria-hidden="true"
          /></a>
        </div>
        </footer>
        <p
          v-if="actionErrors[tweet.id]"
          class="mt-3 text-sm text-danger"
          role="alert"
        >
          {{ actionErrors[tweet.id] }}
        </p>
      </article>
    </section>

    <p v-if="loading" class="py-6 text-sm text-muted" role="status">
      Loading the conversation…
    </p>
    <div
      v-else-if="error"
      class="my-4 border border-danger-rule bg-danger-wash p-3 text-sm text-danger"
      role="alert"
    >
      <p>{{ error }}</p>
      <button
        type="button"
        class="mt-2 min-h-11 underline underline-offset-4"
        @click="loadMore"
      >
        Try again
      </button>
    </div>
    <p v-else-if="!conversation.length" class="py-6 text-sm text-muted">
      No additional English posts to show. Some replies may be hidden by your
      filters or unavailable.
    </p>
    <button
      v-if="hasMore && !loading && !error"
      type="button"
      class="button"
      @click="loadMore"
    >
      Load more replies
    </button>
  </aside>
</template>
