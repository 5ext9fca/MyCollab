<script setup lang="ts">
defineProps<{ id: string; label: string }>()
</script>
<template>
  <div class="selectable-card-selection" @click.stop @keydown.stop><el-checkbox :value="id" :aria-label="label" /></div>
</template>
