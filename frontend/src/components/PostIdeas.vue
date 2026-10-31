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
import { computed, ref, watch } from "vue";
import { formatDate } from "../lib/workbench";
import PostIdeaImage from "./PostIdeaImage.vue";

const draftStorageKey = "twitter-workbench-post-ideas-v1";
let saved = {};
try {
  const value = JSON.parse(localStorage.getItem(draftStorageKey) || "{}");
  if (value && Array.isArray(value.ideas)) saved = value;
} catch { /* Drafts still work when browser storage is unavailable. */ }
const profileFocus = ref(saved.profileFocus ?? "Technology and AI");
const sourceMode = ref(saved.sourceMode ?? "trends");
const themes = ref(saved.themes ?? "");
const count = ref(saved.count ?? 5);
const generateImages = ref(saved.generateImages ?? false);
const ideas = ref(saved.ideas ?? []);
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

watch([ideas, approved, profileFocus, sourceMode, themes, count, generateImages,
  likedPostsUsed, bookmarkedPostsUsed, contextWarning, researchSources, researchedAt, generatedMode], () => {
  try {
    localStorage.setItem(draftStorageKey, JSON.stringify({
      ideas: ideas.value, approved: approved.value, profileFocus: profileFocus.value,
      sourceMode: sourceMode.value, themes: themes.value, count: count.value,
      generateImages: generateImages.value, likedPostsUsed: likedPostsUsed.value,
      bookmarkedPostsUsed: bookmarkedPostsUsed.value, contextWarning: contextWarning.value,
      researchSources: researchSources.value, researchedAt: researchedAt.value, generatedMode: generatedMode.value,
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
      source_mode: sourceMode.value,
      profile_focus: profileFocus.value,
      themes: themes.value,
      count: count.value,
    });
    ideas.value = (body.ideas ?? []).map((idea) => ({ ...idea, includeImage: generateImages.value, image: null }));
    likedPostsUsed.value = body.liked_posts_used ?? 0;
    bookmarkedPostsUsed.value = body.bookmarked_posts_used ?? 0;
    contextWarning.value = body.context_warning ?? body.likes_warning ?? "";
    researchSources.value = body.research_sources ?? [];
    researchedAt.value = body.researched_at ?? null;
    generatedMode.value = body.source_mode ?? sourceMode.value;
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
      image_id: idea.includeImage ? idea.image?.id : null,
      metadata: {
        post_idea: {
          title: idea.title ?? "",
          angle: idea.angle ?? "",
          audience: idea.audience ?? "",
          rationale: idea.rationale ?? "",
          cta: idea.cta ?? "",
          source_ids: idea.source_ids ?? [],
          sources: idea.sources ?? [],
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
      <div class="settings-fields grid gap-4">
        <label class="grid gap-1.5 text-sm">
          <span class="font-medium">Research from</span>
          <select v-model="sourceMode" :disabled="loading" class="min-h-11 border border-rule-strong bg-paper px-3">
            <option value="trends">Trending AI &amp; technology</option>
            <option value="interests">My likes &amp; bookmarks</option>
          </select>
        </label>
        <label class="grid gap-1.5 text-sm">
          <span class="font-medium">Profile focus (optional)</span>
          <textarea
            v-model="profileFocus"
            :disabled="loading"
            placeholder="AI builders, developer tools, software and emerging technology"
            class="min-h-28 rounded-sm border border-rule-strong bg-paper px-3 py-2 leading-5"
          ></textarea>
        </label>
        <label class="grid gap-1.5 text-sm">
          <span class="font-medium">Themes (optional)</span>
          <textarea
            v-model="themes"
            :disabled="loading"
            placeholder="Any topics to emphasize, such as agents or coding tools"
            class="min-h-24 rounded-sm border border-rule-strong bg-paper px-3 py-2 leading-5"
          ></textarea>
        </label>
        <label class="grid gap-1.5 text-sm">
          <span class="font-medium">Ideas</span>
          <input
            v-model.number="count"
            :disabled="loading"
            class="h-9 rounded-sm border border-rule-strong bg-paper px-3"
            max="8"
            min="1"
            type="number"
          />
        </label>
        <button
          class="inline-flex h-9 items-center justify-center gap-2 rounded-sm bg-ink px-4 text-sm font-semibold text-paper hover:bg-ink-hover disabled:cursor-not-allowed disabled:opacity-55"
          :disabled="loading || actionLoadingIndex !== null"
          type="button"
          @click="generateIdeas"
        >
          <Sparkles :class="{ 'animate-spin': loading }" :size="16" aria-hidden="true" />
          {{ loading ? (sourceMode === 'trends' ? "Researching & drafting" : "Generating ideas") : (sourceMode === 'trends' ? "Research & draft" : "Generate ideas") }}
        </button>
        <label class="flex min-h-11 items-center gap-2 text-sm">
          <input v-model="generateImages" type="checkbox" :disabled="loading" class="accent-ink" />
          Generate images with drafts
        </label>
        <p class="text-xs leading-5 text-muted">Images use your signed-in Codex CLI and appear as they finish.</p>
        <p v-if="sourceMode === 'trends'" class="text-xs leading-5 text-muted">
          Researches the past seven days across Hacker News, GitHub and AI publisher feeds. Uses available engagement signals and fresh announcements, with sources attached to each draft.
        </p>
        <p v-else class="text-xs leading-5 text-muted">
          Uses your likes and bookmarks with a 48-hour activity window. Add a focus or themes to steer the angle.
        </p>
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
          <span v-if="researchSources.length" class="rounded-sm bg-paper-shade px-2 py-1">{{ researchSources.length }} research sources · past 7 days</span>
        </div>
        <p v-if="researchedAt" class="text-xs text-muted">Researched {{ formatDate(researchedAt) }}. Engagement counts are snapshots; publisher updates have no popularity measurement.</p>
        <details v-if="researchSources.length" class="border-b border-rule pb-3 text-sm">
          <summary class="min-h-11 cursor-pointer py-3">Research gathered ({{ researchSources.length }})</summary>
          <ul class="grid gap-4 pb-2">
            <li v-for="source in researchSources" :key="source.id" class="min-w-0">
              <a :href="source.url" target="_blank" rel="noreferrer" class="break-words font-bold underline underline-offset-4">{{ source.title }}</a>
              <p class="mt-1 text-xs leading-5 text-muted">{{ source.source }} · {{ source.date_basis }} {{ formatDate(source.published_at) }} · {{ source.traction }}</p>
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

            <label class="mt-3 flex min-h-11 items-center gap-2 text-sm">
              <input v-model="idea.includeImage" type="checkbox" :disabled="approved.includes(index) || actionLoadingIndex !== null" class="accent-ink" />
              Include image
            </label>
            <PostIdeaImage v-model="idea.image" :enabled="idea.includeImage" :post-text="idea.post_text" :title="idea.title" :locked="approved.includes(index) || actionLoadingIndex !== null" />

            <div v-if="idea.cta" class="mt-3 rounded-sm bg-paper-shade px-3 py-2 text-sm text-ink-secondary">
              CTA: {{ idea.cta }}
            </div>

            <div class="mt-4 flex flex-wrap gap-2">
              <button
                class="inline-flex h-9 items-center gap-2 rounded-sm bg-ink px-3 text-sm font-semibold text-paper hover:bg-ink-hover disabled:cursor-not-allowed disabled:opacity-55"
                :disabled="actionLoadingIndex !== null || approved.includes(index) || !idea.post_text?.trim() || postLength(idea.post_text) > 280 || (idea.includeImage && idea.image?.status !== 'ready')"
                type="button"
                @click="approveIdea(idea, index)"
              >
                <Send :size="16" aria-hidden="true" />
                {{ actionLoadingIndex === index ? "Posting" : (idea.includeImage ? "Approve and post text + image" : "Approve and post text") }}
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
            <div class="font-semibold">{{ sourceMode === 'trends' ? 'Research AI and technology trends' : 'Generate post ideas' }}</div>
            <p v-if="sourceMode === 'trends'" class="mt-1 text-sm leading-6 text-muted">Find recent stories with measurable interest, then create original posts with links to the research behind them.</p>
            <p v-else class="mt-1 text-sm leading-6 text-muted">
              Turn what you have liked and saved into original drafts. Your recent interests guide the topics; focus and themes are optional.
            </p>
          </div>
        </div>
      </div>
    </section>
  </main>
</template>
