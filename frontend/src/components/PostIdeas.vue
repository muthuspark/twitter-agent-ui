<script setup>
import {
  AlertCircle,
  CheckCircle2,
  FileText,
  ExternalLink,
  Send,
  Sparkles,
  X,
} from "@lucide/vue";
import { computed, onMounted, ref, watch } from "vue";
import { formatDate } from "../lib/workbench";

const draftStorageKey = "twitter-workbench-post-ideas-essay-v1";
let saved = {};
try {
  const value = JSON.parse(localStorage.getItem(draftStorageKey) || "{}");
  if (value && Array.isArray(value.ideas)) saved = value;
} catch { /* Drafts still work when browser storage is unavailable. */ }
const direction = ref(null);
const ideaType = ref(["mix", "project", "thought_leadership"].includes(saved.ideaType) ? saved.ideaType : "mix");
const count = ref(Math.max(1, Math.min(8, Number(saved.count) || 5)));
const ideas = ref((saved.ideas ?? []).map(({ image, includeImage, ...idea }) => idea));
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

onMounted(async () => {
  try {
    const response = await fetch('/api/posts/editorial-direction');
    const body = await response.json();
    if (!response.ok) throw new Error(body.detail || 'Could not load essay.md');
    direction.value = body.direction;
    if (ideas.value.length && essayVersion.value !== body.direction.version) {
      error.value = 'Your essay has changed. Generate fresh drafts to use the current version.';
    }
  } catch (failure) { error.value = failure.message; }
});

watch([ideas, approved, count,
  likedPostsUsed, bookmarkedPostsUsed, contextWarning, researchSources, researchedAt, generatedMode, ideaType, essayVersion], () => {
  try {
    localStorage.setItem(draftStorageKey, JSON.stringify({
      ideas: ideas.value, approved: approved.value, count: count.value,
      likedPostsUsed: likedPostsUsed.value,
      bookmarkedPostsUsed: bookmarkedPostsUsed.value, contextWarning: contextWarning.value,
      researchSources: researchSources.value, researchedAt: researchedAt.value, generatedMode: generatedMode.value,
      ideaType: ideaType.value, essayVersion: essayVersion.value,
    }));
  } catch { /* Storage limits must not prevent editing or posting. */ }
}, { deep: true });

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
    .map((approvedIndex) => (approvedIndex > index ? approvedIndex - 1 : approvedIndex));
}
</script>

<template>
  <main
    class="manuscript-layout ideas-layout"
  >
    <aside class="manuscript-sidebar">
      <div class="mb-3 flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.08em] text-muted">
        <FileText :size="14" aria-hidden="true" />
        Post Ideas
      </div>
      <div v-if="direction" class="mb-5 border-b border-rule pb-4">
        <p class="text-xs uppercase tracking-[0.08em] text-muted">Editorial foundation</p>
        <h2 class="mt-2 text-base font-bold leading-6">{{ direction.title }}</h2>
        <p class="mt-2 text-xs leading-5 text-muted">One focus, explored deeply. Every draft builds on your essay.</p>
        <a href="/api/posts/essay" target="_blank" rel="noreferrer" class="inline-flex min-h-9 items-center text-sm underline underline-offset-4">Read essay.md</a>
      </div>
      <div class="settings-fields grid gap-4">
        <p class="text-xs leading-5 text-muted">Searches the web for recent news, Hacker News discussions, viral posts, projects and research papers through the lens of your essay.</p>
        <label class="grid gap-1.5 text-sm">
          <span class="font-medium">Post type</span>
          <select v-model="ideaType" :disabled="loading" class="min-h-11 border border-rule-strong bg-paper px-3">
            <option value="mix">Both post types</option>
            <option value="project">Latest projects</option>
            <option value="thought_leadership">Thought leadership</option>
          </select>
        </label>
        <label class="grid gap-1.5 text-sm">
          <span class="font-medium">Ideas</span>
          <input
            v-model.number="count"
            :disabled="loading"
            class="min-h-11 rounded-sm border border-rule-strong bg-paper px-3"
            max="8"
            min="1"
            type="number"
          />
        </label>
        <button
          class="inline-flex min-h-11 items-center justify-center gap-2 rounded-sm bg-ink px-4 text-sm font-semibold text-paper hover:bg-ink-hover disabled:cursor-not-allowed disabled:opacity-55"
          :disabled="loading || actionLoadingIndex !== null || !direction"
          type="button"
          @click="generateIdeas"
        >
          <Sparkles :class="{ 'animate-spin': loading }" :size="16" aria-hidden="true" />
          {{ loading ? "Researching & drafting" : "Research & draft" }}
        </button>

      </div>

      <div class="mt-6 rounded-sm border border-warning-rule bg-warning-wash p-3 text-sm text-warning">
        <div class="flex items-center gap-2 font-semibold">
          <CheckCircle2 :size="16" aria-hidden="true" />
          Approval required
        </div>
        <p class="mt-1 leading-5">
          Drafts are never posted automatically. Edit the final text, then approve one post.
        </p>
      </div>
    </aside>

    <section class="manuscript-content">
      <h2 class="text-2xl font-bold">Post drafts</h2>
      <div class="grid gap-3">
        <p v-if="contextWarning" role="status" class="text-sm text-warning">{{ contextWarning }}</p>
        <div
          v-if="error"
          class="flex items-start gap-3 rounded-sm border border-danger-rule bg-danger-wash p-3 text-sm text-danger"
        >
          <AlertCircle class="mt-0.5 shrink-0" :size="18" aria-hidden="true" />
          <div>{{ error }}</div>
        </div>
        <div class="flex flex-wrap gap-2 text-sm text-muted">
          <span class="rounded-sm bg-paper-shade px-2 py-1">{{ ideas.length }} {{ ideas.length === 1 ? 'idea' : 'ideas' }}</span>
          <span class="rounded-sm bg-paper-shade px-2 py-1">{{ approved.length }} approved</span>
          <span v-if="generatedMode === 'interests' && likedPostsUsed !== null" class="rounded-sm bg-paper-shade px-2 py-1">{{ likedPostsUsed }} likes used</span>
          <span v-if="generatedMode === 'interests' && bookmarkedPostsUsed !== null" class="rounded-sm bg-paper-shade px-2 py-1">{{ bookmarkedPostsUsed }} bookmarks used</span>
          <span v-if="researchSources.length" class="rounded-sm bg-paper-shade px-2 py-1">{{ researchSources.length }} essay-related research sources</span>
        </div>
        <p v-if="researchedAt" class="text-xs text-muted">Researched {{ formatDate(researchedAt) }}. Engagement counts are snapshots; publisher updates have no popularity measurement.</p>
        <details v-if="researchSources.length" class="border-b border-rule pb-3 text-sm">
          <summary class="min-h-11 cursor-pointer py-3">Research gathered ({{ researchSources.length }})</summary>
          <ul class="grid gap-4 pb-2">
            <li v-for="source in researchSources" :key="source.id" class="min-w-0">
              <a :href="source.url" target="_blank" rel="noreferrer" class="break-words font-bold underline underline-offset-4">{{ source.title }}</a>
              <p class="mt-1 text-xs leading-5 text-muted">{{ source.source }} · {{ source.date_basis }} {{ formatDate(source.published_at) }} · {{ source.traction }}</p>
              <p v-if="source.essay_connection" class="mt-1 text-xs leading-5">{{ source.evidence_type }}: {{ source.essay_connection }}</p>
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
            class="rounded-sm border border-rule bg-paper p-4"
          >
            <div class="flex flex-wrap items-start justify-between gap-3">
              <div class="min-w-0">
                <h2 class="text-base font-semibold">{{ idea.title || "Post idea" }}</h2>
                <span v-if="idea.idea_type" class="mt-1 inline-block text-xs uppercase tracking-[0.08em] text-muted">{{ idea.idea_type === 'thought_leadership' ? 'Thought leadership' : idea.idea_type === 'project' ? 'Project' : idea.idea_type }}</span>
                <p class="mt-1 text-sm leading-5 text-muted">{{ idea.angle }}</p>
              </div>
              <span
                v-if="approved.includes(index)"
                class="inline-flex h-7 items-center gap-1 rounded-sm bg-success-wash px-2 text-xs font-semibold text-success"
              >
                <CheckCircle2 :size="14" aria-hidden="true" />
                Posted
              </span>
            </div>

            <div class="mt-3 grid gap-2 text-sm">
              <p v-if="idea.essay_connection" class="leading-6"><span class="font-bold">Connection to your essay:</span> {{ idea.essay_connection }}</p>
              <div v-if="idea.audience" class="text-muted">
                <span class="font-medium text-ink-secondary">Audience:</span>
                {{ idea.audience }}
              </div>
              <div v-if="idea.rationale" class="text-muted">
                <span class="font-medium text-ink-secondary">Why:</span>
                {{ idea.rationale }}
              </div>
            </div>

            <div v-if="idea.sources?.length" class="mt-4 border-t border-rule pt-3">
              <p class="text-xs font-bold uppercase tracking-[0.08em] text-muted">Research behind this draft</p>
              <ul class="mt-2 grid gap-3">
                <li v-for="source in idea.sources" :key="source.id" class="min-w-0 text-sm">
                  <a :href="source.url" target="_blank" rel="noreferrer" class="break-words underline underline-offset-4">{{ source.title }} <ExternalLink class="inline" :size="13" aria-hidden="true" /></a>
                  <p class="mt-1 text-xs leading-5 text-muted">{{ source.source }} · {{ source.date_basis }} {{ formatDate(source.published_at) }} · {{ source.traction }}</p>
                  <a v-if="source.discussion_url" :href="source.discussion_url" target="_blank" rel="noreferrer" class="inline-flex min-h-8 items-center text-xs underline underline-offset-4">View discussion</a>
                </li>
              </ul>
            </div>

            <label class="mt-4 grid gap-1.5 text-sm">
              <span class="font-medium">Editable final post</span>
              <textarea
                v-model="idea.post_text"
                :disabled="approved.includes(index) || actionLoadingIndex !== null"
                class="min-h-28 rounded-sm border border-rule-strong bg-paper px-3 py-2 leading-5"
              ></textarea>
            </label>
            <div class="mt-2 text-xs" :class="postTone(idea)">
              {{ postLength(idea.post_text) }}/280 characters
            </div>

            <div v-if="idea.cta" class="mt-3 rounded-sm bg-paper-shade px-3 py-2 text-sm text-ink-secondary">
              CTA: {{ idea.cta }}
            </div>

            <div class="mt-4 flex flex-wrap gap-2">
              <button
                class="inline-flex h-9 items-center gap-2 rounded-sm bg-ink px-3 text-sm font-semibold text-paper hover:bg-ink-hover disabled:cursor-not-allowed disabled:opacity-55"
                :disabled="actionLoadingIndex !== null || approved.includes(index) || !idea.post_text?.trim() || postLength(idea.post_text) > 280 || idea.essay_version !== direction?.version"
                type="button"
                @click="approveIdea(idea, index)"
              >
                <Send :size="16" aria-hidden="true" />
                {{ actionLoadingIndex === index ? "Posting" : "Approve and post" }}
              </button>
              <button
                class="inline-flex h-9 items-center gap-2 rounded-sm border border-rule-strong bg-paper px-3 text-sm font-semibold hover:bg-paper-shade disabled:cursor-not-allowed disabled:opacity-55"
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
            <div class="font-semibold">Build around one idea</div>
            <p class="mt-1 text-sm leading-6 text-muted">Discover current projects and develop informed points of view on software factories, automation and independent work, grounded in essay.md.</p>
          </div>
        </div>
      </div>
    </section>
  </main>
</template>
