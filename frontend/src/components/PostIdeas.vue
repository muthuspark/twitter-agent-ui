<script setup>
import {
  AlertCircle,
  CheckCircle2,
  FileText,
  Send,
  Sparkles,
  X,
} from "@lucide/vue";
import { computed, ref } from "vue";

const profileFocus = ref("");
const themes = ref("");
const count = ref(5);
const ideas = ref([]);
const loading = ref(false);
const actionLoadingIndex = ref(null);
const error = ref("");
const approved = ref([]);
const likedPostsUsed = ref(null);
const bookmarkedPostsUsed = ref(null);
const contextWarning = ref("");

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
  try {
    const body = await requestJson("/api/posts/ideas", {
      profile_focus: profileFocus.value,
      themes: themes.value,
      count: count.value,
    });
    ideas.value = (body.ideas ?? []).map((idea) => ({ ...idea }));
    likedPostsUsed.value = body.liked_posts_used ?? 0;
    bookmarkedPostsUsed.value = body.bookmarked_posts_used ?? 0;
    contextWarning.value = body.context_warning ?? body.likes_warning ?? "";
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
          <span class="font-medium">Profile focus (optional)</span>
          <textarea
            v-model="profileFocus"
            placeholder="Leave empty to follow your recent interests"
            class="min-h-28 rounded-sm border border-rule-strong bg-paper px-3 py-2 leading-5"
          ></textarea>
        </label>
        <label class="grid gap-1.5 text-sm">
          <span class="font-medium">Themes (optional)</span>
          <textarea
            v-model="themes"
            placeholder="Any topics you want to emphasize"
            class="min-h-24 rounded-sm border border-rule-strong bg-paper px-3 py-2 leading-5"
          ></textarea>
        </label>
        <label class="grid gap-1.5 text-sm">
          <span class="font-medium">Ideas</span>
          <input
            v-model.number="count"
            class="h-9 rounded-sm border border-rule-strong bg-paper px-3"
            max="8"
            min="1"
            type="number"
          />
        </label>
        <button
          class="inline-flex h-9 items-center justify-center gap-2 rounded-sm bg-ink px-4 text-sm font-semibold text-paper hover:bg-ink-hover disabled:cursor-not-allowed disabled:opacity-55"
          :disabled="loading"
          type="button"
          @click="generateIdeas"
        >
          <Sparkles :class="{ 'animate-spin': loading }" :size="16" aria-hidden="true" />
          {{ loading ? "Generating ideas" : "Generate ideas" }}
        </button>
        <p class="text-xs leading-5 text-muted">
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
          <span class="rounded-sm bg-paper-shade px-2 py-1">{{ ideas.length }} ideas</span>
          <span class="rounded-sm bg-paper-shade px-2 py-1">{{ approved.length }} approved</span>
          <span v-if="likedPostsUsed !== null" class="rounded-sm bg-paper-shade px-2 py-1">{{ likedPostsUsed }} likes used</span>
          <span v-if="bookmarkedPostsUsed !== null" class="rounded-sm bg-paper-shade px-2 py-1">{{ bookmarkedPostsUsed }} bookmarks used</span>
        </div>
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

            <label class="mt-4 grid gap-1.5 text-sm">
              <span class="font-medium">Editable final post</span>
              <textarea
                v-model="idea.post_text"
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
                :disabled="actionLoadingIndex === index || approved.includes(index) || postLength(idea.post_text) > 280"
                type="button"
                @click="approveIdea(idea, index)"
              >
                <Send :size="16" aria-hidden="true" />
                {{ actionLoadingIndex === index ? "Posting" : "Approve and post" }}
              </button>
              <button
                class="inline-flex h-9 items-center gap-2 rounded-sm border border-rule-strong bg-paper px-3 text-sm font-semibold hover:bg-paper-shade disabled:cursor-not-allowed disabled:opacity-55"
                :disabled="actionLoadingIndex === index"
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
            <div class="font-semibold">Generate post ideas</div>
            <p class="mt-1 text-sm leading-6 text-muted">
              Turn what you have liked and saved into original drafts. Your recent interests guide the topics; focus and themes are optional.
            </p>
          </div>
        </div>
      </div>
    </section>
  </main>
</template>
