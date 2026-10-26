<script setup lang="ts">
import type { DesignElementBrief } from '../api/types'
defineProps<{ element?: DesignElementBrief | null }>()
</script>
<template>
  <p v-if="element" class="design-reference"><span class="meta">设计依据</span><router-link class="app-link app-link--title" :to="{ name: 'design', params: { id: element.id } }">{{ element.title }}</router-link><span v-if="element.archived">（已归档）</span></p>
  <p v-else class="meta">未关联设计依据</p>
</template>

<style scoped>
.design-reference { display: flex; align-items: baseline; flex-wrap: wrap; gap: 8px; }
</style>
