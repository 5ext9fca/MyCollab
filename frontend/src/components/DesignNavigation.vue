<script setup lang="ts">
import { useRouter } from 'vue-router'
defineProps<{ active: 'design' | 'production-templates' }>()
const router = useRouter()
</script>

<template>
  <nav class="design-navigation" aria-label="设计与生产导航">
    <el-button :type="active === 'design' ? 'primary' : 'default'" :aria-current="active === 'design' ? 'page' : undefined" @click="router.push({ name: 'design' })">设计与资产</el-button>
    <el-button :type="active === 'production-templates' ? 'primary' : 'default'" :aria-current="active === 'production-templates' ? 'page' : undefined" @click="router.push({ name: 'production-templates' })">生产模板</el-button>
  </nav>
</template>

<style scoped>
.design-navigation { display: flex; flex-wrap: wrap; gap: 8px; }
.design-navigation .el-button + .el-button { margin-left: 0; }
</style>
