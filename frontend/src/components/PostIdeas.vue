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

const profileFocus = ref(
  "Jovis.ai target customers: founders, RevOps, sales ops, support ops, and business teams trying to get answers from live business data without waiting on SQL, dashboards, or data teams",
);
const themes = ref(
  "data team bottlenecks, manual reporting, chat with database, CRM analytics, support analytics, RevOps reporting, founder dashboards",
);
const count = ref(5);
const ideas = ref([]);
const loading = ref(false);
const actionLoadingIndex = ref(null);
const error = ref("");
const approved = ref([]);

const hasIdeas = computed(() => ideas.value.length > 0);

function postLength(text) {
  return String(text ?? "").length;
}

function postTone(idea) {
  if (postLength(idea.post_text) > 280) return "text-[oklch(42%_0.09_30)]";
  return "text-[oklch(48%_0.024_245)]";
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
  try {
    const body = await requestJson("/api/posts/ideas", {
      profile_focus: profileFocus.value,
      themes: themes.value,
      count: count.value,
    });
    ideas.value = (body.ideas ?? []).map((idea) => ({ ...idea }));
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
    class="grid min-h-[calc(100vh-112px)] overflow-hidden rounded-lg border border-[oklch(85%_0.012_245)] bg-[oklch(98%_0.004_245)] shadow-sm xl:grid-cols-[340px_minmax(0,1fr)]"
  >
    <aside class="border-b border-[oklch(87%_0.011_245)] bg-[oklch(94%_0.007_245)] p-4 xl:border-b-0 xl:border-r">
      <div class="mb-3 flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.08em] text-[oklch(47%_0.024_245)]">
        <FileText :size="14" aria-hidden="true" />
        Post Ideas
      </div>
      <div class="grid gap-4">
        <label class="grid gap-1.5 text-sm">
          <span class="font-medium">Profile focus</span>
          <textarea
            v-model="profileFocus"
            class="min-h-28 rounded-md border border-[oklch(82%_0.014_245)] bg-[oklch(99%_0.004_245)] px-3 py-2 leading-5"
          ></textarea>
        </label>
        <label class="grid gap-1.5 text-sm">
          <span class="font-medium">Themes</span>
          <textarea
            v-model="themes"
            class="min-h-24 rounded-md border border-[oklch(82%_0.014_245)] bg-[oklch(99%_0.004_245)] px-3 py-2 leading-5"
          ></textarea>
        </label>
        <label class="grid gap-1.5 text-sm">
          <span class="font-medium">Ideas</span>
          <input
            v-model.number="count"
            class="h-9 rounded-md border border-[oklch(82%_0.014_245)] bg-[oklch(99%_0.004_245)] px-3"
            max="8"
            min="1"
            type="number"
          />
        </label>
        <button
          class="inline-flex h-9 items-center justify-center gap-2 rounded-md bg-[oklch(58%_0.13_245)] px-4 text-sm font-semibold text-[oklch(98%_0.004_245)] hover:bg-[oklch(52%_0.14_245)] disabled:cursor-not-allowed disabled:opacity-55"
          :disabled="loading"
          type="button"
          @click="generateIdeas"
        >
          <Sparkles :class="{ 'animate-spin': loading }" :size="16" aria-hidden="true" />
          {{ loading ? "Generating" : "Generate ideas" }}
        </button>
      </div>

      <div class="mt-6 rounded-md border border-[oklch(83%_0.02_80)] bg-[oklch(96%_0.022_80)] p-3 text-sm text-[oklch(38%_0.055_80)]">
        <div class="flex items-center gap-2 font-semibold">
          <CheckCircle2 :size="16" aria-hidden="true" />
          Approval required
        </div>
        <p class="mt-1 leading-5">
          Drafts are never posted automatically. Edit the final text, then approve one post.
        </p>
      </div>
    </aside>

    <section class="grid min-h-[620px] grid-rows-[auto_1fr] gap-4 overflow-hidden p-4">
      <div class="grid gap-3">
        <div
          v-if="error"
          class="flex items-start gap-3 rounded-md border border-[oklch(79%_0.052_30)] bg-[oklch(96%_0.025_30)] p-3 text-sm text-[oklch(36%_0.075_30)]"
        >
          <AlertCircle class="mt-0.5 shrink-0" :size="18" aria-hidden="true" />
          <div>{{ error }}</div>
        </div>
        <div class="flex flex-wrap gap-2 text-sm text-[oklch(48%_0.024_245)]">
          <span class="rounded-md bg-[oklch(94%_0.007_245)] px-2 py-1">{{ ideas.length }} ideas</span>
          <span class="rounded-md bg-[oklch(94%_0.007_245)] px-2 py-1">{{ approved.length }} approved</span>
        </div>
      </div>

      <div class="min-h-0 overflow-auto pr-1">
        <div v-if="loading" class="grid gap-3">
          <div
            v-for="index in 5"
            :key="index"
            class="h-44 animate-pulse rounded-md border border-[oklch(87%_0.012_245)] bg-[oklch(95%_0.007_245)]"
          ></div>
        </div>

        <div v-else-if="hasIdeas" class="grid gap-3">
          <article
            v-for="(idea, index) in ideas"
            :key="`${idea.title}-${index}`"
            class="rounded-md border border-[oklch(86%_0.012_245)] bg-[oklch(99%_0.004_245)] p-4"
          >
            <div class="flex flex-wrap items-start justify-between gap-3">
              <div class="min-w-0">
                <h2 class="text-base font-semibold">{{ idea.title || "Post idea" }}</h2>
                <p class="mt-1 text-sm leading-5 text-[oklch(48%_0.024_245)]">{{ idea.angle }}</p>
              </div>
              <span
                v-if="approved.includes(index)"
                class="inline-flex h-7 items-center gap-1 rounded-md bg-[oklch(94%_0.034_155)] px-2 text-xs font-semibold text-[oklch(34%_0.08_155)]"
              >
                <CheckCircle2 :size="14" aria-hidden="true" />
                Posted
              </span>
            </div>

            <div class="mt-3 grid gap-2 text-sm">
              <div v-if="idea.audience" class="text-[oklch(48%_0.024_245)]">
                <span class="font-medium text-[oklch(34%_0.02_245)]">Audience:</span>
                {{ idea.audience }}
              </div>
              <div v-if="idea.rationale" class="text-[oklch(48%_0.024_245)]">
                <span class="font-medium text-[oklch(34%_0.02_245)]">Why:</span>
                {{ idea.rationale }}
              </div>
            </div>

            <label class="mt-4 grid gap-1.5 text-sm">
              <span class="font-medium">Editable final post</span>
              <textarea
                v-model="idea.post_text"
                class="min-h-28 rounded-md border border-[oklch(82%_0.014_245)] bg-[oklch(99%_0.004_245)] px-3 py-2 leading-5"
              ></textarea>
            </label>
            <div class="mt-2 text-xs" :class="postTone(idea)">
              {{ postLength(idea.post_text) }}/280 characters
            </div>

            <div v-if="idea.cta" class="mt-3 rounded-md bg-[oklch(94%_0.007_245)] px-3 py-2 text-sm text-[oklch(38%_0.02_245)]">
              CTA: {{ idea.cta }}
            </div>

            <div class="mt-4 flex flex-wrap gap-2">
              <button
                class="inline-flex h-9 items-center gap-2 rounded-md bg-[oklch(58%_0.13_245)] px-3 text-sm font-semibold text-[oklch(98%_0.004_245)] hover:bg-[oklch(52%_0.14_245)] disabled:cursor-not-allowed disabled:opacity-55"
                :disabled="actionLoadingIndex === index || approved.includes(index) || postLength(idea.post_text) > 280"
                type="button"
                @click="approveIdea(idea, index)"
              >
                <Send :size="16" aria-hidden="true" />
                {{ actionLoadingIndex === index ? "Posting" : "Approve and post" }}
              </button>
              <button
                class="inline-flex h-9 items-center gap-2 rounded-md border border-[oklch(82%_0.014_245)] bg-[oklch(99%_0.004_245)] px-3 text-sm font-semibold hover:bg-[oklch(94%_0.007_245)] disabled:cursor-not-allowed disabled:opacity-55"
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

        <div v-else class="grid min-h-72 place-items-center rounded-md border border-dashed border-[oklch(82%_0.014_245)] text-center">
          <div class="max-w-sm">
            <div class="font-semibold">Generate post ideas</div>
            <p class="mt-1 text-sm leading-6 text-[oklch(48%_0.024_245)]">
              Create original post drafts for buyers with data access, reporting, CRM, support, and RevOps pain.
            </p>
          </div>
        </div>
      </div>
    </section>
  </main>
</template>
