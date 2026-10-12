<script setup lang="ts">
import { computed } from 'vue'

import type { MissionStatus } from '../api/types'

const props = defineProps<{ status: MissionStatus }>()

type TagType = 'primary' | 'success' | 'warning' | 'info' | 'danger'

const MAP: Record<MissionStatus, { label: string; type: TagType }> = {
  Open: { label: '待认领', type: 'info' },
  InProgress: { label: '进行中', type: 'primary' },
  Submitted: { label: '待验收', type: 'warning' },
  Done: { label: '已完成', type: 'success' },
  Cancelled: { label: '已取消', type: 'danger' },
}

const current = computed(() => MAP[props.status])
</script>

<template>
  <el-tag :type="current.type" disable-transitions>{{ current.label }}</el-tag>
</template>
