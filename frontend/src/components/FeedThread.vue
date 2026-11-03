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
import { isEnglishFeedPost, mergeFeedPage, safeMediaUrl } from "../lib/feed";
import { formatDate, formatMetric, tweetUrl } from "../lib/workbench";

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
const blockMatcher = computed(() => createFeedBlockMatcher(props.blockedTerms));
const conversation = computed(() =>
  items.value.filter(
    (tweet) =>
      String(tweet.id) !== String(props.post.id) &&
      isEnglishFeedPost(tweet) &&
      !blockMatcher.value(tweet),
  ),
);
const displayedPosts = computed(() => [props.post, ...conversation.value]);

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
  if (window.matchMedia("(max-width: 1099px)").matches) {
    panel.value.style.removeProperty("max-height");
    return;
  }
  const top = Math.max(16, panel.value.getBoundingClientRect().top);
  panel.value.style.maxHeight = `${Math.max(160, window.innerHeight - top - 16)}px`;
}

function activate() {
  window.addEventListener("scroll", fitPanel, true);
  window.addEventListener("resize", fitPanel);
  nextTick(fitPanel);
  if (!items.value.length && !loading.value && !error.value) loadMore();
}

function deactivate() {
  stop();
  window.removeEventListener("scroll", fitPanel, true);
  window.removeEventListener("resize", fitPanel);
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
          Thread &amp; replies
        </h2>
        <p class="mt-1 text-sm text-muted">
          English only. Your block list applies here too.
        </p>
      </div>
      <button
        type="button"
        aria-label="Close thread"
        class="button min-w-11 shrink-0"
        @click="$emit('close')"
      >
        <X :size="18" aria-hidden="true" />
      </button>
    </header>

    <section aria-label="Post conversation" :aria-busy="loading">
      <article
        v-for="tweet in displayedPosts"
        :key="tweet.id"
        class="feed-post thread-post"
        :data-post-id="tweet.id"
      >
        <p
          v-if="String(tweet.id) === String(post.id)"
          class="mb-3 text-xs uppercase tracking-[0.1em] text-muted"
        >
          Selected post
        </p>
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
        <div class="mt-3 flex flex-wrap gap-x-4 gap-y-1 text-sm text-muted">
          <span>{{ formatMetric(tweet.metrics?.likes) }} likes</span
          ><span>{{ formatMetric(tweet.metrics?.retweets) }} reposts</span
          ><span>{{ formatMetric(tweet.metrics?.replies) }} replies</span>
        </div>
        <div class="mt-3 flex flex-wrap items-center gap-2">
          <button
            type="button"
            class="button"
            :disabled="
              Boolean(pendingActions[tweet.id]) ||
              likedIds.has(String(tweet.id))
            "
            :aria-pressed="likedIds.has(String(tweet.id))"
            @click="$emit('action', tweet, 'like')"
          >
            <Heart :size="14" aria-hidden="true" />
            {{
              likedIds.has(String(tweet.id))
                ? "Liked"
                : pendingActions[tweet.id] === "like"
                  ? "Liking…"
                  : "Like"
            }}
          </button>
          <button
            type="button"
            class="button"
            :disabled="
              Boolean(pendingActions[tweet.id]) ||
              bookmarkedIds.has(String(tweet.id))
            "
            :aria-pressed="bookmarkedIds.has(String(tweet.id))"
            @click="$emit('action', tweet, 'bookmark')"
          >
            <Bookmark :size="14" aria-hidden="true" />
            {{
              bookmarkedIds.has(String(tweet.id))
                ? "Bookmarked"
                : pendingActions[tweet.id] === "bookmark"
                  ? "Saving…"
                  : "Bookmark"
            }}
          </button>
          <a
            :href="tweetUrl(tweet)"
            target="_blank"
            rel="noreferrer"
            class="button"
            >Open on X <ExternalLink :size="13" aria-hidden="true"
          /></a>
        </div>
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
