<script setup>
import { computed, onBeforeUnmount, ref, watch } from 'vue';
import { ImagePlus, RefreshCw } from '@lucide/vue';

const props = defineProps({
  postText: { type: String, default: '' },
  title: { type: String, default: '' },
  enabled: Boolean,
  locked: Boolean,
  modelValue: { type: Object, default: null },
});
const emit = defineEmits(['update:modelValue']);
const starting = ref(false);
const error = ref('');
const pending = computed(() => starting.value || ['queued', 'generating'].includes(props.modelValue?.status));
const changed = computed(() => props.modelValue?.post_text && props.modelValue.post_text !== props.postText.trim());
let timer;
let disposed = false;
let pollAttempts = 0;

async function readResponse(response) {
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(body.detail || 'Image request failed. Please retry.');
  return body.image;
}

function schedulePoll(id) {
  clearTimeout(timer);
  if (disposed) return;
  if (pollAttempts >= 360) {
    error.value = 'This image is taking longer than expected. Check its status below.';
    return;
  }
  timer = setTimeout(async () => {
    try {
      const image = await readResponse(await fetch(`/api/posts/images/${id}`));
      if (disposed || props.modelValue?.id !== id) return;
      emit('update:modelValue', image);
      pollAttempts += 1;
      if (['queued', 'generating'].includes(image.status)) schedulePoll(id);
    } catch (failure) {
      if (!disposed) error.value = failure.message;
    }
  }, 2000);
}

async function generateImage() {
  if (pending.value || props.locked) return;
  starting.value = true;
  error.value = '';
  clearTimeout(timer);
  try {
    const image = await readResponse(await fetch('/api/posts/images', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ post_text: props.postText, title: props.title }),
    }));
    if (disposed) return;
    emit('update:modelValue', image);
    pollAttempts = 0;
    if (['queued', 'generating'].includes(image.status)) schedulePoll(image.id);
  } catch (failure) {
    if (!disposed) error.value = failure.message;
  } finally {
    starting.value = false;
  }
}

function resumePoll() {
  error.value = '';
  pollAttempts = 0;
  schedulePoll(props.modelValue.id);
}

watch(() => props.enabled, (enabled) => {
  if (!enabled) return;
  if (['queued', 'generating'].includes(props.modelValue?.status)) schedulePoll(props.modelValue.id);
  else if (!props.modelValue) generateImage();
}, { immediate: true });
onBeforeUnmount(() => { disposed = true; clearTimeout(timer); });
</script>

<template>
  <section v-if="enabled" class="mt-4 border-t border-rule pt-4" aria-label="Post image">
    <div class="flex flex-wrap items-center justify-between gap-2">
      <h3 class="text-sm font-bold">Post image</h3>
      <span v-if="modelValue?.status === 'ready'" class="text-xs text-muted">Generated illustration</span>
    </div>
    <div v-if="pending" role="status" class="mt-3 flex min-h-36 items-center justify-center gap-3 border border-rule bg-paper-shade p-5 text-sm text-muted">
      <RefreshCw :size="17" class="animate-spin" aria-hidden="true" />
      {{ modelValue?.status === 'queued' ? 'Image queued' : 'Creating your image' }}
    </div>
    <figure v-if="modelValue?.status === 'ready'" class="mt-3">
      <img :src="modelValue.url" :alt="`Generated illustration for ${title || 'this post'}`" :width="modelValue.width" :height="modelValue.height" class="max-h-96 w-full border border-rule bg-paper-shade object-contain" />
      <figcaption class="mt-2 text-xs leading-5 text-muted">This image will be attached to your post.</figcaption>
    </figure>
    <p v-if="changed" class="mt-2 text-xs leading-5 text-warning">Your text has changed since image generation. Check that the image still fits, or regenerate it.</p>
    <p v-if="error || modelValue?.error" role="alert" class="mt-3 text-sm text-danger">{{ error || modelValue.error }}</p>
    <div class="mt-3 flex flex-wrap gap-3">
      <button v-if="!pending" type="button" :disabled="locked || !postText.trim() || postText.length > 280" class="inline-flex min-h-9 items-center gap-2 border border-rule-strong px-3 text-sm hover:bg-paper-shade disabled:opacity-55" @click="generateImage">
        <ImagePlus :size="15" aria-hidden="true" />
        {{ modelValue?.status === 'ready' ? 'Regenerate image' : 'Generate image' }}
      </button>
      <button v-if="error && pending && modelValue?.id" type="button" :disabled="locked" class="min-h-9 px-2 text-sm underline underline-offset-4" @click="resumePoll">Check status</button>
    </div>
    <details v-if="modelValue?.prompt" class="mt-2 text-xs text-muted">
      <summary class="min-h-9 cursor-pointer py-2">Image brief</summary>
      <p class="whitespace-pre-wrap break-words pb-2 leading-5">{{ modelValue.prompt }}</p>
    </details>
  </section>
</template>
