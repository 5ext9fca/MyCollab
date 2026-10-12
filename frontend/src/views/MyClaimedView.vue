<script setup lang="ts">
import MissionListSection from '../components/MissionListSection.vue'
</script>

<template>
  <MissionListSection title="我认领的" :query="{ assignee: 'me' }" />
</template>
