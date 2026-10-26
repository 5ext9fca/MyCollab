<script setup lang="ts">
import { setThemePreference, themePreference, type ThemePreference } from '../theme'
</script>

<template>
  <label class="theme-select">
    <span>外观</span>
    <select :value="themePreference" aria-label="外观主题" @change="setThemePreference(($event.target as HTMLSelectElement).value as ThemePreference)">
      <option value="system">跟随系统</option>
      <option value="light">浅色</option>
      <option value="dark">深色</option>
    </select>
  </label>
</template>

<style scoped>
.theme-select { display: inline-flex; align-items: center; gap: 8px; color: var(--el-text-color-regular); font-size: 13px; white-space: nowrap; }
select { font: inherit; color: var(--el-text-color-primary); background: var(--el-fill-color-blank); border: 1px solid var(--el-border-color); border-radius: var(--el-border-radius-base); padding: 6px 8px; cursor: pointer; }
select:focus-visible { outline: 2px solid var(--el-color-primary); outline-offset: 2px; }
</style>
