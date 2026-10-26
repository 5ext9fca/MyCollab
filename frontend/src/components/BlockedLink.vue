<script setup lang="ts">
defineProps<{ missionId: string }>()
</script>
<template>
  <router-link class="app-link app-link--action app-link--warning" :to="{ name: 'mission-detail', params: { id: missionId }, hash: '#dependencies' }" aria-label="受阻：查看前置依赖" @click.stop @keydown.stop>受阻</router-link>
</template>
