<script setup>
import { X } from "@lucide/vue";
import { onBeforeUnmount, ref } from "vue";

const props = defineProps({ src: { type: String, required: true }, alt: { type: String, default: "" } });
const open = ref(false);

function onKeydown(event) {
  if (event.key === "Escape") open.value = false;
}
function show() {
  open.value = true;
  window.addEventListener("keydown", onKeydown);
}
function close() {
  open.value = false;
  window.removeEventListener("keydown", onKeydown);
}
onBeforeUnmount(() => window.removeEventListener("keydown", onKeydown));
</script>

<template>
  <button class="feed-image-trigger" type="button" :aria-label="`Open image full screen${alt ? `: ${alt}` : ''}`" @click.stop="show">
    <img :src="src" :alt="alt" loading="lazy" decoding="async" referrerpolicy="no-referrer" />
  </button>
  <Teleport to="body">
    <div v-if="open" class="image-lightbox" role="dialog" aria-modal="true" :aria-label="alt || 'Image preview'" @click.self="close">
      <button class="image-lightbox-close" type="button" aria-label="Close image" @click="close"><X :size="23" aria-hidden="true" /></button>
      <img class="image-lightbox-image" :src="src" :alt="alt" referrerpolicy="no-referrer" />
    </div>
  </Teleport>
</template>
