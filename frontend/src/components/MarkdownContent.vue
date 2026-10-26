<script setup lang="ts">
import { computed } from 'vue'
import DOMPurify from 'dompurify'
import { marked } from 'marked'

const props = defineProps<{ source?: string | null }>()

// User-authored Markdown is untrusted: render then sanitize before injecting.
const html = computed(() => {
  const raw = marked.parse(props.source ?? '', { async: false }) as string
  const clean = DOMPurify.sanitize(raw, { RETURN_DOM_FRAGMENT: true })
  clean.querySelectorAll('a').forEach(link => link.classList.add('app-link'))
  const container = document.createElement('div')
  container.append(clean)
  return container.innerHTML
})
</script>

<template>
  <div class="markdown" v-html="html"></div>
</template>
