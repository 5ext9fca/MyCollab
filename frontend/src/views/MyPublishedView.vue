<script setup lang="ts">
import MissionListSection from '../components/MissionListSection.vue'
</script>

<template>
  <MissionListSection title="我发布的" :query="{ creator: 'me' }" />
</template>
