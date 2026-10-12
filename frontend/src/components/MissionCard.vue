<script setup lang="ts">
import { useRouter } from 'vue-router'

import type { Mission } from '../api/types'
import StatusTag from './StatusTag.vue'

const props = defineProps<{ mission: Mission }>()
const router = useRouter()

function open() {
  router.push({ name: 'mission-detail', params: { id: props.mission.id } })
}
</script>

<template>
  <el-card class="mission-card" shadow="hover" @click="open">
    <div class="mission-card__row">
      <span class="mission-card__title">{{ mission.title }}</span>
      <StatusTag :status="mission.status" />
    </div>
    <div class="meta">
      发起者：{{ mission.creator.display_name }}
      <template v-if="mission.assignee"> · 认领者：{{ mission.assignee.display_name }}</template>
      <template v-else> · 待认领</template>
    </div>
    <div v-if="mission.tags.length" class="tag-row">
      <el-tag v-for="tag in mission.tags" :key="tag.id" size="small" type="info">
        {{ tag.name }}
      </el-tag>
    </div>
  </el-card>
</template>

<style scoped>
.mission-card__row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 6px;
}
</style>
