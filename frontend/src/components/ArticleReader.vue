<script setup>
import {
  computed,
  onActivated,
  onDeactivated,
  onMounted,
  onUnmounted,
  ref,
} from "vue";
import { ExternalLink, Printer } from "@lucide/vue";
import {
  articleDate,
  renderArticleMarkdown,
  waitForArticleImages,
} from "../lib/article";

const emit = defineEmits(["ready", "loaded"]);
const props = defineProps({ initialUrl: { type: String, default: "" } });
const url = ref(props.initialUrl);
const article = ref(null);
const loading = ref(false);
const error = ref("");
const articleDocument = ref(null);
const preparingPrint = ref(false);
let controller;
let requestId = 0;
let active = true;
const previousTitle = document.title;
const html = computed(() => renderArticleMarkdown(article.value?.markdown));
const published = computed(() => articleDate(article.value?.published_at));

async function load() {
  const id = ++requestId;
  controller?.abort();
  controller = new AbortController();
  loading.value = true;
  error.value = "";
  article.value = null;
  if (active) document.title = previousTitle;
  emit("ready", false);
  try {
    const response = await fetch("/api/articles/read", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url: url.value.trim() }),
      signal: controller.signal,
    });
    const body = await response.json().catch(() => ({}));
    if (!response.ok)
      throw new Error(
        typeof body.detail === "string"
          ? body.detail
          : "Could not load this article. Check the link and try again.",
      );
    if (
      !body.title ||
      typeof body.markdown !== "string" ||
      !body.markdown.trim()
    )
      throw new Error("The full article text was not returned. Please retry.");
    if (id !== requestId) return;
    article.value = body;
    if (active) document.title = body.title;
    emit("ready", true);
    emit("loaded", body.source_url);
  } catch (failure) {
    if (failure.name !== "AbortError" && id === requestId)
      error.value = failure.message;
  } finally {
    if (id === requestId) loading.value = false;
  }
}

async function printArticle() {
  if (!article.value || loading.value || preparingPrint.value) return;
  const id = requestId;
  preparingPrint.value = true;
  error.value = "";
  try {
    const failed = await waitForArticleImages(articleDocument.value);
    if (id !== requestId || !active) return;
    if (failed) {
      error.value = `${failed} article image${failed === 1 ? "" : "s"} could not load. Reload the article and try printing again.`;
      return;
    }
    window.print();
  } finally {
    preparingPrint.value = false;
  }
}
onMounted(() => {
  if (props.initialUrl) load();
});
onActivated(() => {
  active = true;
  if (article.value) {
    document.title = article.value.title;
    emit("loaded", article.value.source_url);
  }
});
onDeactivated(() => {
  active = false;
  document.title = previousTitle;
});
onUnmounted(() => {
  ++requestId;
  controller?.abort();
  if (active) document.title = previousTitle;
});
</script>

<template>
  <main
    class="article-reader"
    :class="{ 'has-article': article }"
    aria-labelledby="reader-page-title"
  >
    <section class="reader-controls" aria-label="Article reader controls">
      <h2 id="reader-page-title" class="sr-only">Articles</h2>
      <div class="reader-toolbar">
        <form class="reader-form" @submit.prevent="load">
          <label for="article-url" class="sr-only">X article post link</label>
          <input
            id="article-url"
            v-model="url"
            type="url"
            inputmode="url"
            required
            placeholder="https://x.com/username/status/123"
            autocomplete="off"
            :aria-describedby="error ? 'article-error' : undefined"
          />
          <button
            class="button button-primary"
            type="submit"
            :disabled="loading"
          >
            {{ loading ? "Opening…" : "Open" }}
          </button>
        </form>
        <button
          type="button"
          class="button"
          :disabled="!article || loading || preparingPrint"
          @click="printArticle"
        >
          <Printer :size="16" aria-hidden="true" />{{
            preparingPrint ? "Preparing images…" : "Print / Save PDF"
          }}
        </button>
      </div>
      <p v-if="error" id="article-error" role="alert" class="reader-error">
        {{ error }}
      </p>
      <p class="sr-only" role="status" aria-live="polite">
        {{
          loading
            ? "Fetching the full article from X."
            : article
              ? `Article ready: ${article.title}`
              : ""
        }}
      </p>
      <p v-if="loading" class="reader-status">
        Fetching the full article from X…
      </p>
    </section>
    <p v-if="!article && !loading && !error" class="reader-empty">
      No article open
    </p>
    <article
      v-if="article"
      ref="articleDocument"
      class="article-document"
      aria-labelledby="article-title"
    >
      <header class="article-masthead">
        <h1 id="article-title">{{ article.title }}</h1>
        <p class="article-byline">
          <span v-if="article.author_name">{{ article.author_name }}</span
          ><a
            v-if="article.author_handle"
            :href="`https://x.com/${article.author_handle}`"
            target="_blank"
            rel="noopener noreferrer"
            >@{{ article.author_handle
            }}<span class="sr-only"> (opens in a new tab)</span></a
          ><span v-if="published">{{ published }}</span
          ><span>{{ article.reading_minutes }} min read</span>
        </p>
        <p class="print-source">
          Source: <a :href="article.source_url">{{ article.source_url }}</a>
        </p>
      </header>
      <div class="article-prose" v-html="html"></div>
      <footer class="article-source">
        <a :href="article.source_url" target="_blank" rel="noopener noreferrer"
          >{{ article.source_url }}
          <ExternalLink
            :size="13"
            class="inline source-icon"
            aria-hidden="true"
          /><span class="sr-only"> (opens in a new tab)</span></a
        >
      </footer>
    </article>
  </main>
</template>

<style scoped>
@page x-article {
  margin: 18mm;
}
.article-reader {
  padding-block: 1.5rem 3rem;
  font-family: var(--font-interface);
}
.reader-controls {
  margin-bottom: 2.5rem;
}
.reader-toolbar {
  display: flex;
  align-items: start;
  gap: 0.75rem;
}
.reader-form {
  flex: 1;
  display: flex;
  gap: 0.5rem;
  min-width: 0;
}
.reader-form input {
  min-height: 44px;
  padding: 0.6rem 0.8rem;
  border: 1px solid var(--rule-strong);
  background: var(--paper);
  font-size: 1rem;
}
.reader-error {
  color: var(--danger);
  margin-top: 1rem;
  padding: 0.8rem 1rem;
  border: 1px solid var(--danger-rule);
  background: var(--danger-wash);
  font-size: 0.9375rem;
}
.reader-status {
  margin-top: 1rem;
  color: var(--muted);
}
.reader-empty {
  padding-block: 4rem;
  text-align: center;
  color: var(--muted);
}
.article-document {
  max-width: 72ch;
  margin-inline: auto;
  color: var(--ink);
  font-family: var(--font-interface);
  font-size: 1.125rem;
  line-height: 1.75;
  overflow-wrap: anywhere;
}
.article-masthead {
  margin-bottom: 2rem;
  padding-bottom: 1.4rem;
  border-bottom: 1px solid var(--rule);
}
.article-masthead h1 {
  font-family: var(--font-interface);
  font-size: 2.15rem;
  font-weight: 650;
  line-height: 1.2;
  margin-bottom: 1rem;
  text-wrap: balance;
}
.article-byline {
  display: flex;
  flex-wrap: wrap;
  gap: 0.25rem 1rem;
  font-family: var(--font-interface);
  font-size: 0.875rem;
  color: var(--muted);
}
.article-byline a,
.article-source a {
  text-decoration: underline;
  text-underline-offset: 3px;
}
.print-source {
  display: none;
}
.article-source {
  border-top: 1px solid var(--rule);
  margin-top: 2.5rem;
  padding-top: 1rem;
  font-size: 0.875rem;
  font-family: var(--font-interface);
}
.article-prose :deep(p) {
  margin-block: 0 1.1em;
  orphans: 3;
  widows: 3;
}
.article-prose :deep(h2),
.article-prose :deep(h3),
.article-prose :deep(h4),
.article-prose :deep(h5),
.article-prose :deep(h6) {
  font-family: var(--font-interface);
  font-weight: 650;
  line-height: 1.3;
  margin-block: 1.8em 0.7em;
  break-after: avoid;
}
.article-prose :deep(h2) {
  font-size: 1.5rem;
}
.article-prose :deep(h3) {
  font-size: 1.25rem;
}
.article-prose :deep(h4),
.article-prose :deep(h5),
.article-prose :deep(h6) {
  font-size: 1.125rem;
}
.article-prose :deep(ul),
.article-prose :deep(ol) {
  padding-left: 1.5em;
  margin-bottom: 1.1em;
}
.article-prose :deep(ul) {
  list-style: disc;
}
.article-prose :deep(ol) {
  list-style: decimal;
}
.article-prose :deep(li) {
  margin-block: 0.25em;
}
.article-prose :deep(blockquote) {
  padding: 0.75em 1em;
  margin-block: 1em;
  background: var(--paper-shade);
  font-style: italic;
}
.article-prose :deep(blockquote > :last-child) {
  margin-bottom: 0;
}
.article-prose :deep(a) {
  color: var(--accent);
  text-decoration: underline;
  text-underline-offset: 3px;
  overflow-wrap: anywhere;
}
.article-prose :deep(img) {
  max-width: 100%;
  height: auto;
  margin-block: 1.2em;
  break-inside: avoid;
}
.article-prose :deep(pre) {
  max-width: 100%;
  overflow-x: auto;
  white-space: pre-wrap;
  padding: 1em;
  margin-block: 1em;
  background: var(--paper-shade);
  font-size: 0.875rem;
  break-inside: auto;
}
.article-prose :deep(code) {
  font-family: ui-monospace, monospace;
  font-size: 0.9em;
}
.article-prose :deep(table) {
  width: 100%;
  margin-block: 1em;
  border-collapse: collapse;
  table-layout: fixed;
  font-size: 0.9em;
}
.article-prose :deep(th),
.article-prose :deep(td) {
  border: 1px solid var(--rule);
  padding: 0.5em;
  text-align: start;
  overflow-wrap: anywhere;
}
.article-prose :deep(hr) {
  border-top: 1px solid var(--rule);
  margin-block: 1.8em;
}
@media (max-width: 639px) {
  .reader-toolbar {
    flex-wrap: wrap;
  }
  .reader-form {
    flex-basis: 100%;
  }
  .reader-controls {
    margin-bottom: 1.5rem;
  }
  .article-masthead h1 {
    font-size: 1.75rem;
  }
  .article-document {
    font-size: 1.0625rem;
    line-height: 1.7;
  }
}
@media print {
  .reader-controls,
  .reader-empty {
    display: none !important;
  }
  .article-reader {
    padding: 0;
  }
  .article-document {
    page: x-article;
    max-width: none;
    margin: 0;
    font-size: 11pt;
    line-height: 1.45;
  }
  .article-masthead {
    margin-bottom: 1.2em;
    padding-bottom: 1em;
  }
  .article-masthead h1 {
    font-size: 23pt;
  }
  .article-byline,
  .article-source {
    font-size: 9pt;
  }
  .source-icon {
    display: none;
  }
  .print-source {
    display: block;
    margin-top: 0.4em;
    font-size: 8pt;
    line-height: 1.4;
  }
  .article-source {
    display: none;
  }
  .article-prose :deep(h2) {
    font-size: 16pt;
  }
  .article-prose :deep(h3) {
    font-size: 13pt;
  }
  .article-prose :deep(p) {
    margin-bottom: 0.5em;
  }
  .article-prose :deep(h2),
  .article-prose :deep(h3) {
    margin-block: 1.3em 0.5em;
  }
  .article-prose :deep(blockquote) {
    padding: 0.25em 0.8em;
    margin-block: 0.8em;
  }
  .article-prose :deep(ol:has(> li:only-child)) {
    break-after: avoid;
  }
  .article-prose :deep(img) {
    max-height: 220mm;
    object-fit: contain;
  }
  .article-prose :deep(pre) {
    overflow: visible;
  }
  .article-prose :deep(thead) {
    display: table-header-group;
  }
  .article-prose :deep(tr) {
    break-inside: avoid;
  }
  .article-source {
    break-inside: avoid;
  }
}
</style>
