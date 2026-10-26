<script setup lang="ts">
import type { DesignElementBrief } from '../api/types'
defineProps<{ element?: DesignElementBrief | null; assets?: DesignElementBrief[] }>()
</script>
<template>
  <p v-if="element" class="design-reference"><span class="meta">设计依据</span><router-link class="app-link app-link--action" :to="{ name: 'design', params: { id: element.id } }">{{ element.title }}</router-link><span v-if="element.archived">（已归档）</span></p>
  <p v-else class="meta">未关联设计依据</p>
  <div v-if="assets?.length" class="design-reference"><span class="meta">相关资产</span><router-link v-for="asset in assets" :key="asset.id" class="app-link app-link--action" :to="{ name: 'design', params: { id: asset.id } }">{{ asset.title }}{{ asset.archived ? '（已归档）' : '' }}</router-link></div>
</template>

<style scoped>
.design-reference { display: flex; align-items: baseline; flex-wrap: wrap; gap: 8px; }
</style>
