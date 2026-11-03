<script setup>
import { computed, defineAsyncComponent, ref, watch } from "vue";
import { ArrowUp } from "@lucide/vue";

// Each screen owns its data and lifecycle. Load it on first visit and retain its state.
const views = [
  {
    id: "feeds",
    label: "Feed",
    component: defineAsyncComponent(() => import("./components/Feeds.vue")),
  },
  {
    id: "postIdeas",
    label: "Post ideas",
    component: defineAsyncComponent(() => import("./components/PostIdeas.vue")),
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
