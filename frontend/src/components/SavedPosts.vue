<script setup>
import { Bookmark, ExternalLink, Heart, RefreshCw } from "@lucide/vue";
import { onActivated, onDeactivated, ref } from "vue";
import { formatDate, formatMetric } from "../lib/format";
import { tweetUrl } from "../lib/social";

const kind = ref("likes");
const posts = ref([]);
const loading = ref(false);
const error = ref("");
let requestVersion = 0;

async function loadPosts(nextKind = kind.value) {
  if (nextKind !== kind.value) posts.value = [];
  kind.value = nextKind;
  const version = ++requestVersion;
  loading.value = true;
  error.value = "";
  try {
    const response = await fetch(`/api/posts/saved?kind=${encodeURIComponent(kind.value)}`);
    const body = await response.json().catch(() => ({}));
    if (!response.ok || body.ok !== true) throw new Error(body.detail || `Unable to load ${kind.value}.`);
    if (version === requestVersion) posts.value = Array.isArray(body.posts) ? body.posts : [];
  } catch (failure) {
    if (version === requestVersion) {
      posts.value = [];
      error.value = failure.message || `Unable to load ${kind.value}.`;
    }
  } finally {
    if (version === requestVersion) loading.value = false;
  }
}

function deactivate() {
  requestVersion += 1;
  loading.value = false;
}

onActivated(() => loadPosts());
onDeactivated(deactivate);
</script>

<template>
  <main class="saved-posts-view" aria-labelledby="saved-posts-title">
    <header class="saved-posts-heading">
      <div>
        <p class="saved-posts-eyebrow">Your library</p>
        <h2 id="saved-posts-title">Likes &amp; bookmarks</h2>
        <p class="saved-posts-description">Posts you’ve saved on X, collected in one place.</p>
      </div>
      <button class="button" type="button" :disabled="loading" @click="loadPosts()">
        <RefreshCw :size="16" :class="{ 'animate-spin': loading }" aria-hidden="true" />
        Refresh
      </button>
    </header>

    <div class="saved-posts-toolbar" role="group" aria-label="Choose saved posts">
      <button class="button" :class="{ 'button-primary': kind === 'likes' }" type="button" :aria-pressed="kind === 'likes'" @click="loadPosts('likes')">
        <Heart :size="16" aria-hidden="true" /> Likes
      </button>
      <button class="button" :class="{ 'button-primary': kind === 'bookmarks' }" type="button" :aria-pressed="kind === 'bookmarks'" @click="loadPosts('bookmarks')">
        <Bookmark :size="16" aria-hidden="true" /> Bookmarks
      </button>
      <span class="saved-posts-count" aria-live="polite">{{ loading ? "Loading…" : `${posts.length} ${kind}` }}</span>
    </div>

    <div v-if="error" class="saved-posts-error" role="alert">{{ error }}</div>

    <div v-else-if="loading && !posts.length" class="saved-posts-skeleton" aria-label="Loading saved posts">
      <div v-for="index in 4" :key="index" class="saved-post-skeleton-row"></div>
    </div>

    <section v-else-if="posts.length" class="saved-posts-list" :aria-label="kind">
      <article v-for="post in posts" :key="post.id" class="saved-post-item">
        <header class="saved-post-item-header">
          <div class="saved-post-author">
            <strong>{{ post.author?.name || post.author?.screenName || "Post" }}</strong>
            <span v-if="post.author?.screenName">@{{ post.author.screenName }}</span>
          </div>
          <time v-if="post.createdAtISO || post.createdAtLocal" class="saved-post-date" :datetime="post.createdAtISO || undefined">
            {{ formatDate(post.createdAtISO || post.createdAtLocal) }}
          </time>
        </header>
        <p class="saved-post-text">{{ post.text }}</p>
        <footer class="saved-post-item-footer">
          <span>{{ formatMetric(post.metrics?.likes) }} likes</span>
          <span>{{ formatMetric(post.metrics?.replies) }} replies</span>
          <span>{{ formatMetric(post.metrics?.retweets) }} reposts</span>
          <a :href="tweetUrl(post)" target="_blank" rel="noreferrer">
            Open on X <ExternalLink :size="14" aria-hidden="true" />
          </a>
        </footer>
      </article>
    </section>

    <section v-else class="saved-posts-empty" aria-live="polite">
      <div class="saved-posts-empty-icon" aria-hidden="true">{{ kind === "likes" ? "♡" : "▱" }}</div>
      <h3>No {{ kind }} to show</h3>
      <p>Your recent {{ kind }} from X will appear here.</p>
      <button class="button" type="button" :disabled="loading" @click="loadPosts()">Try again</button>
    </section>
  </main>
</template>
