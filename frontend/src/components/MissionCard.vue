<script setup lang="ts">
import MissionSchedule from './MissionSchedule.vue'
import { useRouter } from 'vue-router'

import type { Mission } from '../api/types'
import { PRIORITY_TAG, TYPE_LABELS, TYPE_TAG } from '../missionMeta'
import StatusTag from './StatusTag.vue'

const props = defineProps<{ mission: Mission; openInDrawer?: boolean }>()
const emit = defineEmits<{ open: [id: string] }>()
const router = useRouter()

function open() {
  if (props.openInDrawer) { emit('open', props.mission.id); return }
  router.push({ name: 'mission-detail', params: { id: props.mission.id } })
}
</script>

<template>
  <el-card class="mission-card" shadow="hover" @click="open">
    <div class="mission-card__layout">
      <div v-if="$slots.selection" class="mission-card__selection" @click.stop>
        <slot name="selection" />
      </div>
      <div class="mission-card__content">
        <div class="mission-card__row">
          <span class="mission-card__title">{{ mission.title }}</span>
          <div class="mission-card__tags">
            <el-tag :type="TYPE_TAG[mission.type]" size="small" disable-transitions>
              {{ TYPE_LABELS[mission.type] }}
            </el-tag>
            <el-tag :type="PRIORITY_TAG[mission.priority]" size="small" disable-transitions>
              {{ mission.priority }}
            </el-tag>
            <el-tag v-if="mission.is_blocked" type="warning" size="small" disable-transitions>
              受阻
            </el-tag>
            <StatusTag :status="mission.status" />
          </div>
        </div>
        <div class="meta">
          发起者：{{ mission.creator.display_name }}
          <template v-if="mission.assignee"> · 认领者：{{ mission.assignee.display_name }}</template>
          <template v-else> · 待认领</template>
          <template v-if="mission.milestone"> · 里程碑：{{ mission.milestone.name }}</template>
        </div>
        <MissionSchedule v-if="mission.planned_start_date || mission.planned_end_date" :mission="mission" />
        <div v-if="mission.tags.length" class="tag-row">
          <el-tag v-for="tag in mission.tags" :key="tag.id" size="small" type="info">
            {{ tag.name }}
          </el-tag>
        </div>
      </div>
    </div>
  </el-card>
</template>

<style scoped>
.mission-card__layout {
  display: flex;
  align-items: center;
  gap: 12px;
}
.mission-card__selection {
  flex: none;
  cursor: default;
}
.mission-card__content {
  flex: 1;
  min-width: 0;
}

.mission-card__row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 6px;
}

.mission-card__tags {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
  justify-content: flex-end;
}
</style>
