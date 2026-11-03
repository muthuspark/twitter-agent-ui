<script setup>
import {
  AlertCircle,
  Ban,
  Bookmark,
  ExternalLink,
  Heart,
  RefreshCw,
  Repeat2,
  X,
} from "@lucide/vue";
import {
  computed,
  nextTick,
  onActivated,
  onBeforeUnmount,
  onDeactivated,
  ref,
  watch,
} from "vue";
import { formatDate, formatMetric } from "../lib/format";
import { tweetUrl } from "../lib/social";
import {
  isEnglishFeedPost,
  mediaAltText,
  mergeFeedPage,
  safeMediaUrl,
  submitFeedAction,
} from "../lib/feed";
import {
  addBlockedTerm,
  createFeedBlockMatcher,
  loadBlockedTerms,
  normalizeBlockedTerm,
  saveBlockedTerms,
} from "../lib/blocklist";
import FeedThread from "./FeedThread.vue";

const blockListOpen = ref(false);

async function toggleBlockList() {
  if (!blockListOpen.value) await closeThread();
  blockListOpen.value = !blockListOpen.value;
}

async function editBlockList() {
  blockListOpen.value = true;
  await nextTick();
  document.getElementById("new-blocked-term")?.focus();
}

const tweets = ref([]);
const cursor = ref(null);
const hasMore = ref(true);
const loading = ref(false);
const error = ref("");
const autoPaused = ref(false);
const retryRefresh = ref(false);
const sentinel = ref(null);
const likedIds = ref(new Set());
const bookmarkedIds = ref(new Set());
const pendingActions = ref({});
const actionErrors = ref({});
const selectedPost = ref(null);
let savedFeedScroll = 0;
let threadOpenTimer;
let storage;
try {
  storage = window.localStorage;
} catch {
  storage = null;
}
const blockedTerms = ref(loadBlockedTerms(storage));
const blockMatcher = computed(() => createFeedBlockMatcher(blockedTerms.value));
const englishTweets = computed(() => tweets.value.filter(isEnglishFeedPost));
const visibleTweets = computed(() =>
  englishTweets.value.filter((tweet) => !blockMatcher.value(tweet)),
);
const hiddenCount = computed(
  () => englishTweets.value.length - visibleTweets.value.length,
);
const newBlockedTerm = ref("");
const blockNotice = ref("");
const blockError = ref("");
const selectedText = ref(null);
const contextMenu = ref(null);
const menuElement = ref(null);
const menuButton = ref(null);
let menuOrigin;
let visitedCursors = new Set();
let emptyPages = 0;
let active = false;
let observer;
let controller;

async function openThread(tweet) {
  if (
    !isEnglishFeedPost(tweet) ||
    blockMatcher.value(tweet) ||
    String(selectedPost.value?.id) === String(tweet.id)
  )
    return;
  savedFeedScroll = window.scrollY;
  selectedPost.value = tweet;
  closeContextMenu();
  await nextTick();
  if (window.matchMedia("(max-width: 899px)").matches) {
    const top =
      document.getElementById("feed-top").getBoundingClientRect().top +
      window.scrollY;
    window.scrollTo({ top, behavior: "instant" });
  }
  document
    .getElementById("feed-thread-heading")
    ?.focus({ preventScroll: true });
}

function handlePostClick(tweet, event) {
  window.clearTimeout(threadOpenTimer);
  if (
    event.button !== 0 ||
    event.detail > 1 ||
    event.target.closest("button, a, input, textarea") ||
    window.getSelection()?.toString().trim()
  )
    return;
  // Let a double-click or drag finish selecting text before opening a column.
  threadOpenTimer = window.setTimeout(() => {
    if (!window.getSelection()?.toString().trim()) openThread(tweet);
  }, 230);
}

async function closeThread() {
  if (!selectedPost.value) return;
  const id = selectedPost.value?.id;
  selectedPost.value = null;
  await nextTick();
  window.scrollTo({ top: savedFeedScroll, behavior: "instant" });
  const trigger = document
    .querySelector(
      `[data-post-id="${CSS.escape(String(id))}"] [data-thread-toggle]`,
    );
  (trigger || document.getElementById("feed-block-list-toggle"))
    ?.focus({ preventScroll: true });
}

function persistBlockList(terms) {
  blockedTerms.value = terms;
  blockError.value = saveBlockedTerms(storage, terms)
    ? ""
    : "Changes apply for this session, but browser storage is unavailable. They may be lost on refresh.";
}

function blockText(value) {
  try {
    const fromSelection = Boolean(contextMenu.value || selectedText.value);
    const terms = addBlockedTerm(blockedTerms.value, value);
    const term = normalizeBlockedTerm(value);
    const alreadyBlocked = terms.length === blockedTerms.value.length;
    persistBlockList(terms);
    blockNotice.value = alreadyBlocked
      ? `“${term}” is already blocked.`
      : `“${term}” added to your block list.`;
    newBlockedTerm.value = "";
    closeContextMenu();
    window.getSelection()?.removeAllRanges();
    selectedText.value = null;
    nextTick(() => {
      const target = fromSelection
        ? document.getElementById("feed-thread-heading") ||
          document.getElementById("feed-block-list-toggle")
        : document.getElementById("new-blocked-term");
      target?.focus({ preventScroll: true });
    });
  } catch (failure) {
    blockError.value = failure.message;
  }
}

async function unblockText(term) {
  const index = blockedTerms.value.indexOf(term);
  persistBlockList(blockedTerms.value.filter((item) => item !== term));
  blockNotice.value = `“${term}” removed from your block list.`;
  await nextTick();
  const buttons = document.querySelectorAll("[data-unblock-term]");
  (buttons[Math.min(index, buttons.length - 1)] ||
    document.getElementById("new-blocked-term"))?.focus({ preventScroll: true });
}

function getSelectedFeedText() {
  const selection = window.getSelection();
  if (!selection?.rangeCount || selection.isCollapsed) return null;
  const anchor =
    selection.anchorNode?.nodeType === Node.ELEMENT_NODE
      ? selection.anchorNode
      : selection.anchorNode?.parentElement;
  const root = anchor?.closest("[data-feed-text]");
  if (!root?.closest("#feed-top") || !root.contains(selection.focusNode))
    return null;
  const text = normalizeBlockedTerm(selection.toString());
  if (!text || text.length > 200) return null;
  return {
    text,
    root,
    postId: root.closest(".feed-post")?.dataset.postId,
    rect: selection.getRangeAt(0).getBoundingClientRect(),
  };
}

function updateSelection() {
  const info = getSelectedFeedText();
  selectedText.value = info ? { text: info.text, postId: info.postId } : null;
}

async function showSelectionMenu(info, x, y) {
  menuOrigin = info.root;
  contextMenu.value = { text: info.text, x, y };
  await nextTick();
  if (!contextMenu.value || !menuElement.value) return;
  const rect = menuElement.value.getBoundingClientRect();
  contextMenu.value = {
    text: info.text,
    x: Math.max(
      8,
      Math.min(x, document.documentElement.clientWidth - rect.width - 8),
    ),
    y: Math.max(
      8,
      Math.min(y, document.documentElement.clientHeight - rect.height - 8),
    ),
  };
  menuButton.value?.focus({ preventScroll: true });
}

function openSelectionMenu(event) {
  window.clearTimeout(threadOpenTimer);
  const info = getSelectedFeedText();
  if (!info || !info.root.contains(event.target)) return;
  event.preventDefault();
  showSelectionMenu(
    info,
    event.clientX || info.rect.left,
    event.clientY || info.rect.bottom,
  );
}

function closeContextMenu() {
  contextMenu.value = null;
}
function dismissOnPointer(event) {
  if (contextMenu.value && !menuElement.value?.contains(event.target))
    closeContextMenu();
}
function handleMenuKey(event) {
  if (contextMenu.value && ["Escape", "Tab"].includes(event.key)) {
    closeContextMenu();
    if (event.key === "Escape") {
      event.preventDefault();
      menuOrigin?.focus({ preventScroll: true });
    }
    return;
  }
  if (event.key === "Escape" && selectedPost.value) {
    event.preventDefault();
    closeThread();
    return;
  }
  if (event.key === "ContextMenu" || (event.shiftKey && event.key === "F10")) {
    const info = getSelectedFeedText();
    if (!info || event.target.closest?.("input, textarea")) return;
    event.preventDefault();
    showSelectionMenu(info, info.rect.left, info.rect.bottom);
  }
}

watch(
  blockedTerms,
  (terms) => {
    emptyPages = 0;
    autoPaused.value = false;
    if (selectedPost.value && blockMatcher.value(selectedPost.value))
      closeThread();
    observeEnd();
  },
  { immediate: true },
);

async function actOnPost(tweet, action) {
  const id = String(tweet.id);
  const completed = action === "like" ? likedIds : bookmarkedIds;
  if (pendingActions.value[id] || completed.value.has(id)) return;
  pendingActions.value[id] = action;
  delete actionErrors.value[id];
  try {
    await submitFeedAction(tweet, action);
    completed.value = new Set([...completed.value, id]);
  } catch (failure) {
    actionErrors.value[id] = failure.message;
  } finally {
    delete pendingActions.value[id];
  }
}

async function observeEnd() {
  await nextTick();
  observer?.disconnect();
  if (
    active &&
    hasMore.value &&
    !error.value &&
    !autoPaused.value &&
    sentinel.value
  ) {
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
    const response = await fetch(`/api/feed?${params}`, {
      signal: controller.signal,
    });
    const body = await response.json().catch(() => ({}));
    if (!response.ok)
      throw new Error(body.detail || "Unable to load your Twitter feed.");
    if (!Array.isArray(body.tweets))
      throw new Error("Twitter returned an invalid feed page.");
    const visited = refresh ? new Set() : visitedCursors;
    const merged = mergeFeedPage(
      refresh ? [] : tweets.value,
      body,
      requestedCursor,
      visited,
    );
    visited.add(requestedCursor);
    visitedCursors = visited;
    tweets.value = merged.tweets;
    cursor.value = merged.nextCursor;
    hasMore.value = merged.hasMore;
    const visibleAdded = merged.added
      ? merged.tweets
          .slice(-merged.added)
          .filter(
            (tweet) => isEnglishFeedPost(tweet) && !blockMatcher.value(tweet),
          ).length
      : 0;
    emptyPages = visibleAdded ? 0 : emptyPages + 1;
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
  document.addEventListener("selectionchange", updateSelection);
  document.addEventListener("pointerdown", dismissOnPointer);
  document.addEventListener("keydown", handleMenuKey);
  window.addEventListener("scroll", closeContextMenu, true);
  window.addEventListener("resize", closeContextMenu);
  if ("IntersectionObserver" in window) {
    observer = new IntersectionObserver(
      (entries) => {
        if (
          active &&
          !error.value &&
          !autoPaused.value &&
          entries.some((entry) => entry.isIntersecting) &&
          !loading.value
        )
          loadMore();
      },
      { rootMargin: "600px 0px" },
    );
  }
  if (!tweets.value.length && !loading.value && !error.value) loadMore();
  else observeEnd();
});

function stop() {
  active = false;
  window.clearTimeout(threadOpenTimer);
  closeContextMenu();
  selectedText.value = null;
  document.removeEventListener("selectionchange", updateSelection);
  document.removeEventListener("pointerdown", dismissOnPointer);
  document.removeEventListener("keydown", handleMenuKey);
  window.removeEventListener("scroll", closeContextMenu, true);
  window.removeEventListener("resize", closeContextMenu);
  observer?.disconnect();
  controller?.abort();
}
onDeactivated(stop);
onBeforeUnmount(stop);
</script>

<template>
  <Teleport to="#feed-nav-actions">
    <button
      id="feed-block-list-toggle"
      class="button button-quiet"
      type="button"
      :aria-expanded="blockListOpen"
      aria-controls="feed-block-list"
      @click="toggleBlockList"
    >
      Block list<span v-if="blockedTerms.length">({{ blockedTerms.length }})</span>
    </button>
    <button
      type="button"
      class="button button-quiet button-icon"
      aria-label="Refresh feed"
      title="Refresh feed"
      :disabled="loading"
      @click="loadMore({ refresh: true })"
    >
      <RefreshCw
        :size="17"
        :class="{ 'animate-spin': loading }"
        aria-hidden="true"
      />
    </button>
  </Teleport>
  <main
    id="feed-top"
    class="feeds-view"
    aria-label="Feed"
    :class="{ 'has-thread': selectedPost }"
    @contextmenu="openSelectionMenu"
  >
    <div class="feed-columns">
      <div class="feed-timeline-column">
        <section
          v-if="blockListOpen"
          id="feed-block-list"
          class="feed-block-list"
          aria-labelledby="feed-block-heading"
        >
          <h3 id="feed-block-heading" class="font-bold">
            Blocked words and phrases
          </h3>
          <form
            class="mt-4 flex flex-wrap items-end gap-3"
            @submit.prevent="blockText(newBlockedTerm)"
          >
            <label
              class="grid min-w-0 flex-1 gap-2 text-sm"
              for="new-blocked-term"
            >
              Word or phrase
              <input
                id="new-blocked-term"
                v-model="newBlockedTerm"
                maxlength="200"
                class="min-h-11 border border-rule-strong bg-paper px-3"
              />
            </label>
            <button
              type="submit"
              class="button button-primary"
              :disabled="!newBlockedTerm.trim()"
            >
              Block
            </button>
          </form>
          <ul
            v-if="blockedTerms.length"
            class="mt-4 flex flex-wrap gap-2"
            aria-label="Blocked text"
          >
            <li
              v-for="term in blockedTerms"
              :key="term"
              class="inline-flex max-w-full items-center gap-3 border border-rule px-3 text-sm"
            >
              <span class="min-w-0 break-words">{{ term }}</span>
              <button
                data-unblock-term
                type="button"
                class="inline-flex min-h-11 shrink-0 items-center gap-1 text-muted hover:text-ink"
                :aria-label="`Unblock ${term}`"
                @click="unblockText(term)"
              >
                <X :size="14" aria-hidden="true" /> Remove
              </button>
            </li>
          </ul>
          <p v-else class="mt-4 text-sm text-muted">No blocked phrases</p>
        </section>
        <p v-if="blockError" class="mt-4 text-sm text-danger" role="alert">
          {{ blockError }}
        </p>
        <p v-if="blockNotice" class="mt-4 text-sm" role="status">
          {{ blockNotice }}
        </p>
        <p v-if="blockedTerms.length" class="my-4 text-xs text-muted">
          {{ hiddenCount }} loaded
          {{ hiddenCount === 1 ? "post" : "posts" }} hidden by your block list.
        </p>

        <div
          v-if="error"
          class="my-6 flex items-start gap-3 border border-danger-rule bg-danger-wash p-4 text-sm text-danger"
          role="alert"
        >
          <AlertCircle :size="18" class="shrink-0" aria-hidden="true" />
          <div>
            <p>{{ error }}</p>
            <button
              class="mt-2 min-h-11 underline underline-offset-4"
              type="button"
              @click="loadMore({ manual: true, refresh: retryRefresh })"
            >
              Try again
            </button>
          </div>
        </div>

        <section aria-label="Home timeline" :aria-busy="loading">
          <article
            v-for="tweet in visibleTweets"
            :key="tweet.id"
            class="feed-post feed-clickable-post"
            :class="{
              'is-thread-selected':
                String(selectedPost?.id) === String(tweet.id),
            }"
            :data-post-id="tweet.id"
            @click="handlePostClick(tweet, $event)"
          >
            <p
              v-if="tweet.isRetweet && tweet.retweetedBy"
              class="mb-3 flex items-center gap-2 text-xs text-muted"
            >
              <Repeat2 :size="14" aria-hidden="true" />
              {{ tweet.retweetedBy }} reposted
            </p>
            <header class="flex flex-wrap items-baseline gap-x-3 gap-y-1">
              <a
                data-thread-toggle
                :href="tweetUrl(tweet)"
                class="font-semibold hover:underline underline-offset-4"
                :aria-label="`Open thread by ${tweet.author?.name || tweet.author?.screenName || 'Unknown author'}`"
                :aria-expanded="String(selectedPost?.id) === String(tweet.id)"
                aria-controls="feed-thread"
                @click.stop.prevent="openThread(tweet)"
              >{{
                tweet.author?.name ||
                tweet.author?.screenName ||
                "Unknown author"
              }}</a>
              <span v-if="tweet.author?.screenName" class="text-sm text-muted"
                >@{{ tweet.author.screenName }}</span
              >
              <time
                :datetime="tweet.createdAtISO || undefined"
                class="text-sm text-muted"
                >{{
                  formatDate(tweet.createdAtISO || tweet.createdAtLocal)
                }}</time
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
              class="mt-4 border border-rule p-4 text-base"
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

            <div v-if="tweet.media?.length" class="feed-media mt-4">
              <template
                v-for="(media, index) in tweet.media"
                :key="`${tweet.id}-${index}`"
              >
                <img
                  v-if="media.type === 'photo' && safeMediaUrl(media.url)"
                  :src="safeMediaUrl(media.url)"
                  :width="media.width || undefined"
                  :height="media.height || undefined"
                  :alt="mediaAltText(media, index)"
                  loading="lazy"
                  decoding="async"
                  referrerpolicy="no-referrer"
                />
                <a
                  v-else
                  :href="tweetUrl(tweet)"
                  target="_blank"
                  rel="noreferrer"
                  class="inline-flex min-h-11 items-center gap-2 text-sm underline underline-offset-4"
                >
                  View {{ media.type === "video" ? "video" : "media" }} on X
                  <ExternalLink :size="14" aria-hidden="true" />
                </a>
              </template>
            </div>

            <footer
              class="feed-post-footer mt-3"
            >
              <div class="feed-post-metrics">
              <span>{{ formatMetric(tweet.metrics?.likes) }} likes</span>
              <span>{{ formatMetric(tweet.metrics?.retweets) }} reposts</span>
              <span>{{ formatMetric(tweet.metrics?.replies) }} replies</span>
              </div>
            <div class="feed-post-actions flex items-center">
              <button
                type="button"
                class="button button-quiet button-icon button-icon-compact"
                :aria-label="likedIds.has(String(tweet.id)) ? 'Liked' : pendingActions[tweet.id] === 'like' ? 'Liking…' : 'Like'"
                :title="likedIds.has(String(tweet.id)) ? 'Liked' : 'Like'"
                :class="{ 'text-accent': likedIds.has(String(tweet.id)) }"
                :disabled="
                  Boolean(pendingActions[tweet.id]) ||
                  likedIds.has(String(tweet.id))
                "
                :aria-pressed="likedIds.has(String(tweet.id))"
                @click="actOnPost(tweet, 'like')"
              >
                <Heart
                  :size="18"
                  :fill="
                    likedIds.has(String(tweet.id)) ? 'currentColor' : 'none'
                  "
                  aria-hidden="true"
                />
              </button>
              <button
                type="button"
                class="button button-quiet button-icon button-icon-compact"
                :aria-label="bookmarkedIds.has(String(tweet.id)) ? 'Bookmarked' : pendingActions[tweet.id] === 'bookmark' ? 'Saving…' : 'Bookmark'"
                :title="bookmarkedIds.has(String(tweet.id)) ? 'Bookmarked' : 'Bookmark'"
                :class="{ 'text-accent': bookmarkedIds.has(String(tweet.id)) }"
                :disabled="
                  Boolean(pendingActions[tweet.id]) ||
                  bookmarkedIds.has(String(tweet.id))
                "
                :aria-pressed="bookmarkedIds.has(String(tweet.id))"
                @click="actOnPost(tweet, 'bookmark')"
              >
                <Bookmark
                  :size="18"
                  :fill="
                    bookmarkedIds.has(String(tweet.id))
                      ? 'currentColor'
                      : 'none'
                  "
                  aria-hidden="true"
                />
              </button>
              <a
                :href="tweetUrl(tweet)"
                target="_blank"
                rel="noreferrer"
                class="button button-quiet button-icon button-icon-compact"
                aria-label="Open on X"
                title="Open on X"
              >
                <ExternalLink :size="18" aria-hidden="true" />
              </a>
            </div>
            </footer>
              <button
                v-if="selectedText?.postId === String(tweet.id)"
                type="button"
                class="button mt-2"
                @pointerdown.prevent
                @click="blockText(selectedText.text)"
              >
                <Ban :size="15" class="shrink-0" aria-hidden="true" /><span
                  class="truncate"
                  >Block “{{ selectedText.text }}”</span
                >
              </button>
            <p
              v-if="actionErrors[tweet.id]"
              class="mt-3 text-sm text-danger"
              role="alert"
            >
              {{ actionErrors[tweet.id] }}
            </p>
          </article>
        </section>

        <div
          v-if="loading"
          class="grid gap-6 py-6"
          role="status"
          aria-label="Loading posts"
        >
          <span class="text-sm text-muted">Loading your timeline…</span>
          <div v-if="!tweets.length" aria-hidden="true">
            <div v-for="index in 3" :key="index" class="feed-skeleton">
              <div class="feed-skeleton-author"></div>
              <div class="feed-skeleton-line"></div>
              <div class="feed-skeleton-line"></div>
              <div class="feed-skeleton-line feed-skeleton-short"></div>
              <div class="feed-skeleton-actions"></div>
            </div>
          </div>
        </div>
        <div
          v-else-if="!visibleTweets.length && !error"
          class="manuscript-empty"
        >
          <div>
            <strong>{{
              tweets.length ? "No matching posts" : "No posts yet"
            }}</strong>
            <p class="mt-2 text-sm text-muted">
              {{ tweets.length
                ? "Only English posts are shown. Your block list may also hide posts."
                : "Your home timeline is empty. Refresh to check for new posts." }}
            </p>
            <button
              v-if="blockedTerms.length"
              class="button mt-4"
              type="button"
              @click="editBlockList"
            >
              Edit block list
            </button>
          </div>
        </div>

        <div ref="sentinel" class="feed-sentinel" aria-hidden="true"></div>
        <div class="feed-end">
          <button
            v-if="hasMore && !error && !loading"
            type="button"
            class="button"
            @click="loadMore({ manual: true })"
          >
            Load more posts
          </button>
          <p v-if="autoPaused && !error" class="mt-3 text-sm text-muted">
            No new visible posts in the last few pages. Adjust your block list
            or load more to keep checking.
          </p>
          <p v-if="!hasMore && tweets.length" class="text-sm text-muted">
            End of feed
          </p>
        </div>
      </div>
      <FeedThread
        v-if="selectedPost"
        :post="selectedPost"
        :blocked-terms="blockedTerms"
        :liked-ids="likedIds"
        :bookmarked-ids="bookmarkedIds"
        :pending-actions="pendingActions"
        :action-errors="actionErrors"
        @close="closeThread"
        @action="actOnPost"
      />
    </div>
  </main>
  <Teleport to="body">
    <div
      v-if="contextMenu"
      ref="menuElement"
      class="feed-selection-menu"
      role="menu"
      aria-label="Selected feed text"
      :style="{ left: `${contextMenu.x}px`, top: `${contextMenu.y}px` }"
      @keydown.down.prevent
      @keydown.up.prevent
    >
      <button
        ref="menuButton"
        type="button"
        role="menuitem"
        class="flex min-h-11 w-full items-start gap-3 px-4 py-3 text-left text-sm hover:bg-paper-shade"
        @pointerdown.prevent
        @click="blockText(contextMenu.text)"
      >
        <Ban :size="16" class="mt-0.5 shrink-0" aria-hidden="true" /><span
          class="min-w-0 break-words"
          >Block “{{ contextMenu.text }}”</span
        >
      </button>
      <p class="border-t border-rule px-4 py-2 text-xs text-muted">
        Hide matching posts. Case insensitive.
      </p>
    </div>
  </Teleport>
</template>
