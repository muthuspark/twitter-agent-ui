<script setup>
import {
  AlertCircle,
  CheckCircle2,
  ExternalLink,
  Send,
  Sparkles,
  X,
} from "@lucide/vue";
import { computed, onActivated, ref, watch } from "vue";
import { formatDate } from "../lib/workbench";

const draftStorageKey = "twitter-workbench-post-ideas-essay-v1";
let saved = {};
try {
  const value = JSON.parse(localStorage.getItem(draftStorageKey) || "{}");
  if (value && Array.isArray(value.ideas)) saved = value;
} catch {
  /* Drafts still work when browser storage is unavailable. */
}
const direction = ref(null);
const ideaType = ref(
  ["mix", "project", "thought_leadership"].includes(saved.ideaType)
    ? saved.ideaType
    : "mix",
);
const count = ref(Math.max(1, Math.min(8, Number(saved.count) || 5)));
const ideas = ref(
  (saved.ideas ?? []).map(({ image, includeImage, ...idea }) => idea),
);
const loading = ref(false);
const actionLoadingIndex = ref(null);
const error = ref("");
const approved = ref(saved.approved ?? []);
const likedPostsUsed = ref(saved.likedPostsUsed ?? null);
const bookmarkedPostsUsed = ref(saved.bookmarkedPostsUsed ?? null);
const contextWarning = ref(saved.contextWarning ?? "");
const researchSources = ref(saved.researchSources ?? []);
const researchedAt = ref(saved.researchedAt ?? null);
const generatedMode = ref(saved.generatedMode ?? null);
const essayVersion = ref(saved.essayVersion ?? null);

onActivated(async () => {
  // Recheck the essay on return without replacing the user's draft.
  direction.value = null;
  try {
    const response = await fetch("/api/posts/editorial-direction");
    const body = await response.json();
    if (!response.ok) throw new Error(body.detail || "Could not load essay.md");
    direction.value = body.direction;
    if (ideas.value.length && essayVersion.value !== body.direction.version) {
      error.value =
        "Your essay has changed. Generate fresh drafts to use the current version.";
    }
  } catch (failure) {
    error.value = failure.message;
  }
});

watch(
  [
    ideas,
    approved,
    count,
    likedPostsUsed,
    bookmarkedPostsUsed,
    contextWarning,
    researchSources,
    researchedAt,
    generatedMode,
    ideaType,
    essayVersion,
  ],
  () => {
    try {
      localStorage.setItem(
        draftStorageKey,
        JSON.stringify({
          ideas: ideas.value,
          approved: approved.value,
          count: count.value,
          likedPostsUsed: likedPostsUsed.value,
          bookmarkedPostsUsed: bookmarkedPostsUsed.value,
          contextWarning: contextWarning.value,
          researchSources: researchSources.value,
          researchedAt: researchedAt.value,
          generatedMode: generatedMode.value,
          ideaType: ideaType.value,
          essayVersion: essayVersion.value,
        }),
      );
    } catch {
      /* Storage limits must not prevent editing or posting. */
    }
  },
  { deep: true },
);

const hasIdeas = computed(() => ideas.value.length > 0);

function postLength(text) {
  return String(text ?? "").length;
}

function postTone(idea) {
  if (postLength(idea.post_text) > 280) return "text-accent";
  return "text-muted";
}

async function requestJson(path, payload) {
  const response = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(body.detail || "Request failed");
  return body;
}

async function generateIdeas() {
  if (loading.value || actionLoadingIndex.value !== null || !direction.value)
    return;
  loading.value = true;
  error.value = "";
  approved.value = [];
  likedPostsUsed.value = null;
  bookmarkedPostsUsed.value = null;
  ideas.value = [];
  contextWarning.value = "";
  researchSources.value = [];
  researchedAt.value = null;
  generatedMode.value = null;
  try {
    const body = await requestJson("/api/posts/ideas", {
      source_mode: "trends",
      count: count.value,
      idea_type: ideaType.value,
    });
    ideas.value = body.ideas ?? [];
    likedPostsUsed.value = body.liked_posts_used ?? 0;
    bookmarkedPostsUsed.value = body.bookmarked_posts_used ?? 0;
    contextWarning.value = body.context_warning ?? body.likes_warning ?? "";
    researchSources.value = body.research_sources ?? [];
    researchedAt.value = body.researched_at ?? null;
    generatedMode.value = body.source_mode ?? "trends";
    essayVersion.value = body.editorial_direction?.version ?? null;
    direction.value = { ...direction.value, ...body.editorial_direction };
  } catch (failure) {
    error.value = failure.message;
  } finally {
    loading.value = false;
  }
}

async function approveIdea(idea, index) {
  if (!idea?.post_text || actionLoadingIndex.value !== null) return;
  actionLoadingIndex.value = index;
  error.value = "";
  try {
    await requestJson("/api/posts/approve", {
      post_text: idea.post_text,
      metadata: {
        post_idea: {
          title: idea.title ?? "",
          angle: idea.angle ?? "",
          audience: idea.audience ?? "",
          rationale: idea.rationale ?? "",
          cta: idea.cta ?? "",
          source_ids: idea.source_ids ?? [],
          sources: idea.sources ?? [],
          essay_connection: idea.essay_connection ?? "",
          essay_version: idea.essay_version ?? "",
          idea_type: idea.idea_type ?? "insight",
        },
      },
    });
    approved.value = [...approved.value, index];
  } catch (failure) {
    error.value = failure.message;
  } finally {
    actionLoadingIndex.value = null;
  }
}

function rejectIdea(index) {
  ideas.value = ideas.value.filter((_, ideaIndex) => ideaIndex !== index);
  approved.value = approved.value
    .filter((approvedIndex) => approvedIndex !== index)
    .map((approvedIndex) =>
      approvedIndex > index ? approvedIndex - 1 : approvedIndex,
    );
}
</script>

<template>
  <main class="ideas-view">
    <header class="ideas-heading">
      <h2 class="text-2xl font-bold">Post ideas</h2>
      <form class="ideas-controls" @submit.prevent="generateIdeas">
        <label class="sr-only" for="idea-type">Post type</label>
        <select
          id="idea-type"
          v-model="ideaType"
          :disabled="loading"
          class="min-h-11 border border-rule-strong bg-paper px-3 text-sm"
        >
          <option value="mix">All types</option>
          <option value="project">Projects</option>
          <option value="thought_leadership">Thought leadership</option>
        </select>
        <label class="sr-only" for="idea-count">Number of ideas</label>
        <input
          id="idea-count"
          v-model.number="count"
          :disabled="loading"
          class="min-h-11 border border-rule-strong bg-paper px-3 text-sm"
          aria-label="Number of ideas"
          max="8"
          min="1"
          type="number"
        />
        <button
          class="button button-primary"
          :disabled="loading || actionLoadingIndex !== null || !direction"
          type="submit"
        >
          <Sparkles
            :class="{ 'animate-spin': loading }"
            :size="16"
            aria-hidden="true"
          />{{ loading ? "Drafting…" : "Generate drafts" }}
        </button>
      </form>
    </header>
    <details v-if="direction" class="writing-direction">
      <summary>Writing direction</summary>
      <h3 class="mt-2 font-semibold">{{ direction.title }}</h3>
      <a
        href="/api/posts/essay"
        target="_blank"
        rel="noreferrer"
        class="inline-flex min-h-11 items-center text-sm underline underline-offset-4"
        >Open essay</a
      >
    </details>
    <section class="ideas-content" aria-label="Post drafts">
      <div
        v-if="contextWarning || error || researchSources.length"
        class="grid gap-3"
      >
        <p v-if="contextWarning" role="status" class="text-sm text-warning">
          {{ contextWarning }}
        </p>
        <div
          v-if="error"
          class="flex items-start gap-3 rounded-sm border border-danger-rule bg-danger-wash p-3 text-sm text-danger"
        >
          <AlertCircle class="mt-0.5 shrink-0" :size="18" aria-hidden="true" />
          <div>{{ error }}</div>
        </div>
        <details
          v-if="researchSources.length"
          class="border-b border-rule pb-3 text-sm"
        >
          <summary class="min-h-11 cursor-pointer py-3">
            Research ({{ researchSources.length }})
          </summary>
          <p v-if="researchedAt" class="mb-3 text-xs text-muted">
            {{ formatDate(researchedAt) }}
          </p>
          <ul class="grid gap-4 pb-2">
            <li
              v-for="source in researchSources"
              :key="source.id"
              class="min-w-0"
            >
              <a
                :href="source.url"
                target="_blank"
                rel="noreferrer"
                class="break-words font-bold underline underline-offset-4"
                >{{ source.title }}</a
              >
              <p class="mt-1 text-xs leading-5 text-muted">
                {{ source.source }} · {{ source.date_basis }}
                {{ formatDate(source.published_at) }} · {{ source.traction }}
              </p>
              <p v-if="source.essay_connection" class="mt-1 text-xs leading-5">
                {{ source.evidence_type }}: {{ source.essay_connection }}
              </p>
            </li>
          </ul>
        </details>
      </div>

      <div class="results-region">
        <div v-if="loading" class="grid gap-3">
          <div
            v-for="index in 5"
            :key="index"
            class="h-44 animate-pulse rounded-sm border border-rule bg-paper-shade"
          ></div>
        </div>

        <div v-else-if="hasIdeas" class="grid gap-3">
          <article
            v-for="(idea, index) in ideas"
            :key="`${idea.title}-${index}`"
            class="idea-draft"
          >
            <div class="flex flex-wrap items-start justify-between gap-3">
              <div class="min-w-0">
                <h3 class="text-base font-semibold">
                  {{ idea.title || "Post idea" }}
                </h3>
              </div>
              <span
                v-if="approved.includes(index)"
                class="inline-flex h-7 items-center gap-1 rounded-sm bg-success-wash px-2 text-xs font-semibold text-success"
              >
                <CheckCircle2 :size="14" aria-hidden="true" />
                Posted
              </span>
            </div>

            <label class="mt-4 grid gap-1.5 text-sm">
              <span class="sr-only"
                >Post text for {{ idea.title || "this draft" }}</span
              >
              <textarea
                v-model="idea.post_text"
                :disabled="
                  approved.includes(index) || actionLoadingIndex !== null
                "
                class="min-h-28 rounded-sm border border-rule-strong bg-paper px-3 py-2 leading-5"
              ></textarea>
            </label>
            <div class="mt-2 text-xs" :class="postTone(idea)">
              {{ postLength(idea.post_text) }}/280 characters
            </div>

            <details class="draft-context">
              <summary>Sources &amp; reasoning</summary>
              <p v-if="idea.angle" class="text-sm">{{ idea.angle }}</p>
              <div class="mt-3 grid gap-2 text-sm">
                <p v-if="idea.essay_connection" class="leading-6">
                  <span class="font-bold">Essay:</span>
                  {{ idea.essay_connection }}
                </p>
                <div v-if="idea.audience" class="text-muted">
                  <span class="font-medium text-ink-secondary">Audience:</span>
                  {{ idea.audience }}
                </div>
                <div v-if="idea.rationale" class="text-muted">
                  <span class="font-medium text-ink-secondary">Why:</span>
                  {{ idea.rationale }}
                </div>
              </div>

              <div
                v-if="idea.sources?.length"
                class="mt-4 border-t border-rule pt-3"
              >
                <p
                  class="text-xs font-bold uppercase tracking-[0.08em] text-muted"
                >
                  Sources
                </p>
                <ul class="mt-2 grid gap-3">
                  <li
                    v-for="source in idea.sources"
                    :key="source.id"
                    class="min-w-0 text-sm"
                  >
                    <a
                      :href="source.url"
                      target="_blank"
                      rel="noreferrer"
                      class="break-words underline underline-offset-4"
                      >{{ source.title }}
                      <ExternalLink
                        class="inline"
                        :size="13"
                        aria-hidden="true"
                    /></a>
                    <p class="mt-1 text-xs leading-5 text-muted">
                      {{ source.source }} · {{ source.date_basis }}
                      {{ formatDate(source.published_at) }} ·
                      {{ source.traction }}
                    </p>
                    <a
                      v-if="source.discussion_url"
                      :href="source.discussion_url"
                      target="_blank"
                      rel="noreferrer"
                      class="inline-flex min-h-8 items-center text-xs underline underline-offset-4"
                      >View discussion</a
                    >
                  </li>
                </ul>
              </div>

              <p v-if="idea.cta" class="mt-3 text-sm">{{ idea.cta }}</p>
            </details>
            <div class="mt-4 flex flex-wrap gap-2">
              <button
                class="button button-primary"
                :disabled="
                  actionLoadingIndex !== null ||
                  approved.includes(index) ||
                  !idea.post_text?.trim() ||
                  postLength(idea.post_text) > 280 ||
                  idea.essay_version !== direction?.version
                "
                type="button"
                @click="approveIdea(idea, index)"
              >
                <Send :size="16" aria-hidden="true" />
                {{
                  approved.includes(index)
                    ? "Posted"
                    : actionLoadingIndex === index
                      ? "Posting…"
                      : "Post to X"
                }}
              </button>
              <button
                class="button"
                :disabled="actionLoadingIndex !== null"
                type="button"
                @click="rejectIdea(index)"
              >
                <X :size="16" aria-hidden="true" />
                Remove
              </button>
            </div>
          </article>
        </div>

        <div v-else class="manuscript-empty">
          <div class="max-w-sm">
            <div class="font-semibold">No drafts yet</div>
          </div>
        </div>
      </div>
    </section>
  </main>
</template>

<style scoped>
.ideas-view {
  max-width: 64rem;
  padding-block: 1.5rem 3rem;
}
.ideas-heading,
.ideas-controls {
  display: flex;
  align-items: center;
  gap: 0.75rem;
}
.ideas-heading {
  justify-content: space-between;
  flex-wrap: wrap;
  margin-bottom: 1rem;
}
.ideas-controls select {
  width: auto;
}
.ideas-controls input {
  width: 4.5rem;
}
.writing-direction {
  border-bottom: 1px solid var(--rule);
  padding-bottom: 1rem;
  margin-bottom: 1rem;
  font-size: 0.875rem;
}
summary {
  padding-block: 0.65rem;
  min-height: 44px;
}
.ideas-content {
  display: grid;
  gap: 1rem;
}
.idea-draft {
  border-top: 1px solid var(--rule);
  padding-block: 1.5rem;
}
.idea-draft:first-child {
  border-top: 0;
  padding-top: 0;
}
.draft-context {
  margin-top: 0.5rem;
  font-size: 0.875rem;
  color: var(--muted);
}
.idea-draft textarea {
  min-height: 9rem;
  font-size: 1rem;
  line-height: 1.7;
}
@media (max-width: 639px) {
  .ideas-controls {
    width: 100%;
    flex-wrap: wrap;
  }
  .ideas-controls select {
    flex: 1;
    min-width: 0;
  }
  .ideas-controls .button {
    width: 100%;
  }
}
</style>
