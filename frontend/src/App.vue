<script setup>
import { computed, defineAsyncComponent, ref, watch } from "vue";
import { ArrowUp, Plus, Sparkles, X } from "@lucide/vue";

// Each screen owns its data and lifecycle. Load it on first visit and retain its state.
const views = [
  {
    id: "feeds",
    label: "Feed",
    component: defineAsyncComponent(() => import("./components/Feeds.vue")),
  },
  {
    id: "savedPosts",
    label: "Saved posts",
    component: defineAsyncComponent(() => import("./components/SavedPosts.vue")),
  },
  {
    id: "postIdeas",
    label: "Post ideas",
    component: defineAsyncComponent(() => import("./components/PostIdeas.vue")),
  },
  {
    id: "commentCandidates",
    label: "Comment candidates",
    component: defineAsyncComponent(() => import("./components/GrowthMode.vue")),
  },
  {
    id: "analytics",
    label: "Analytics",
    component: defineAsyncComponent(
      () => import("./components/AnalyticsDashboard.vue"),
    ),
  },
  {
    id: "customers",
    label: "Customers",
    component: defineAsyncComponent(
      () => import("./components/PotentialCustomers.vue"),
    ),
  },
  {
    id: "articleReader",
    label: "Articles",
    component: defineAsyncComponent(
      () => import("./components/ArticleReader.vue"),
    ),
  },
];
const initialArticleUrl =
  new URL(window.location.href).searchParams.get("article") || "";
const activeTab = ref(initialArticleUrl ? "articleReader" : "feeds");
const activeView = computed(() =>
  views.find((view) => view.id === activeTab.value),
);
const articleReady = ref(false);
const composerOpen = ref(false);
const postText = ref("");
const composeError = ref("");
const refining = ref(false);
const posting = ref(false);

async function refinePost() {
  if (!postText.value.trim() || refining.value) return;
  refining.value = true;
  composeError.value = "";
  try {
    const response = await fetch("/api/posts/refine", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ post_text: postText.value }),
    });
    const body = await response.json().catch(() => ({}));
    if (!response.ok || body.ok !== true) throw new Error(body.detail || "Unable to refine this post.");
    postText.value = body.post_text;
  } catch (error) {
    composeError.value = error.message || "Unable to refine this post.";
  } finally {
    refining.value = false;
  }
}

async function publishPost() {
  if (!postText.value.trim() || posting.value) return;
  posting.value = true;
  composeError.value = "";
  try {
    const response = await fetch("/api/posts/approve", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ post_text: postText.value }),
    });
    const body = await response.json().catch(() => ({}));
    if (!response.ok || body.ok !== true) throw new Error(body.detail || "Unable to post to X.");
    composerOpen.value = false;
    postText.value = "";
  } catch (error) {
    composeError.value = error.message || "Unable to post to X.";
  } finally {
    posting.value = false;
  }
}

function backToTop() {
  const behavior = window.matchMedia("(prefers-reduced-motion: reduce)").matches
    ? "instant"
    : "smooth";
  window.scrollTo({ top: 0, behavior });
  document.getElementById("feed-thread")?.scrollTo({ top: 0, behavior });
}

function rememberArticle(url) {
  if (activeTab.value !== "articleReader") return;
  const location = new URL(window.location.href);
  location.searchParams.set("article", url);
  window.history.replaceState(window.history.state, "", location);
}

const readerBindings = {
  initialUrl: initialArticleUrl,
  onReady: (ready) => {
    articleReady.value = ready;
  },
  onLoaded: rememberArticle,
};

watch(activeTab, (tab) => {
  if (tab !== "articleReader") {
    const location = new URL(window.location.href);
    location.searchParams.delete("article");
    window.history.replaceState(window.history.state, "", location);
  }
});
</script>

<template>
  <div
    class="manuscript-app"
    :class="{
      'article-print-view': activeTab === 'articleReader' && articleReady,
    }"
  >
    <div class="manuscript-shell">
      <header class="manuscript-header">
        <h1 class="sr-only">Twitter Agent</h1>
        <nav aria-label="Main navigation" class="manuscript-nav">
          <button
            v-for="view in views"
            :key="view.id"
            type="button"
            class="manuscript-tab"
            :class="{ 'is-active': activeTab === view.id }"
            :aria-current="activeTab === view.id ? 'page' : undefined"
            @click="activeTab = view.id"
          >
            {{ view.label }}
          </button>
        </nav>
        <button class="button button-primary compose-trigger" type="button" @click="composerOpen = true">
          <Plus :size="17" aria-hidden="true" /> Create post
        </button>
        <div
          v-show="activeTab === 'feeds'"
          id="feed-nav-actions"
          class="feed-nav-actions"
          role="group"
          aria-label="Feed controls"
        ></div>
      </header>
      <KeepAlive>
        <component
          :is="activeView.component"
          :key="activeTab"
          v-bind="activeTab === 'articleReader' ? readerBindings : {}"
        />
      </KeepAlive>
    </div>
    <div v-if="composerOpen" class="compose-backdrop" @click.self="composerOpen = false">
      <section class="compose-dialog" role="dialog" aria-modal="true" aria-labelledby="compose-title">
        <header class="compose-dialog-header">
          <h2 id="compose-title">Create a post</h2>
          <button class="button button-icon" type="button" aria-label="Close composer" @click="composerOpen = false"><X :size="18" aria-hidden="true" /></button>
        </header>
        <label class="sr-only" for="compose-text">Post text</label>
        <textarea id="compose-text" v-model="postText" autofocus maxlength="280" placeholder="What do you want to share?" :disabled="posting" class="compose-textarea"></textarea>
        <div class="compose-meta">
          <span :class="postText.length > 280 ? 'compose-count-over' : ''">{{ postText.length }}/280</span>
          <button class="button compose-refine" type="button" :disabled="!postText.trim() || refining || posting || postText.length > 280" @click="refinePost">
            <Sparkles :size="15" aria-hidden="true" /> {{ refining ? "Refining…" : "Refine" }}
          </button>
        </div>
        <p v-if="composeError" class="compose-error" role="alert">{{ composeError }}</p>
        <footer class="compose-footer">
          <button class="button button-primary" type="button" :disabled="!postText.trim() || posting || postText.length > 280" @click="publishPost">{{ posting ? "Posting…" : "Post" }}</button>
        </footer>
      </section>
    </div>
    <button
      type="button"
      class="button button-icon back-to-top"
      aria-label="Back to top"
      title="Back to top"
      @click="backToTop"
    >
      <ArrowUp :size="20" aria-hidden="true" />
    </button>
  </div>
</template>
