<script setup lang="ts">
/**
 * F5 filter bar.
 *
 * The keyword is debounced (300 ms) before it reaches the request; select
 * changes fire immediately. New requests supersede old ones in WorkspaceView,
 * which owns the request sequence.
 */
import { onBeforeUnmount, ref, watch } from 'vue'

import type { User } from '../api/types'
import { PRIORITY_OPTIONS, STATUS_OPTIONS, TYPE_OPTIONS } from '../missionMeta'
import type { QuickKey, WorkspaceFilters } from '../workspace/filters'

const props = defineProps<{
  filters: WorkspaceFilters
  members: User[]
  milestoneOptions: { id: string; name: string }[]
  onlyMine: boolean
  onlyBlocked: boolean
  onlyReview: boolean
  onlyRevalidation: boolean
}>()

const emit = defineEmits<{
  (event: 'change'): void
  (event: 'toggle', key: QuickKey): void
}>()

const DEBOUNCE_MS = 300
const keyword = ref(props.filters.q)
let timer: ReturnType<typeof setTimeout> | undefined

watch(
  () => props.filters.q,
  (value) => {
    if (value !== keyword.value) keyword.value = value
  },
)

watch(keyword, (value) => {
  if (timer) clearTimeout(timer)
  timer = setTimeout(() => {
    if (value === props.filters.q) return
    props.filters.q = value
    emit('change')
  }, DEBOUNCE_MS)
})

onBeforeUnmount(() => {
  if (timer) clearTimeout(timer)
})
</script>

<template>
  <div class="filters">
    <div class="filters__row">
      <el-input
        v-model="keyword"
        placeholder="搜索标题或内容"
        style="width: 200px"
        clearable
      />
      <el-select
        v-model="filters.milestone"
        placeholder="里程碑"
        clearable
        filterable
        style="width: 170px"
        @change="emit('change')"
      >
        <el-option
          v-for="item in milestoneOptions"
          :key="item.id"
          :label="item.name"
          :value="item.id"
        />
        <el-option label="未归属里程碑" value="none" />
      </el-select>
      <el-select
        v-model="filters.status"
        placeholder="状态"
        clearable
        style="width: 130px"
        @change="emit('change')"
      >
        <el-option
          v-for="item in STATUS_OPTIONS"
          :key="item.value"
          :label="item.label"
          :value="item.value"
        />
      </el-select>
      <el-select
        v-model="filters.assignee"
        placeholder="认领者"
        clearable
        filterable
        style="width: 150px"
        @change="emit('change')"
      >
        <el-option label="我" value="me" />
        <el-option label="未认领" value="none" />
        <el-option
          v-for="member in members"
          :key="member.id"
          :label="member.display_name"
          :value="String(member.id)"
        />
      </el-select>
      <el-select
        v-model="filters.type"
        placeholder="类型"
        clearable
        style="width: 120px"
        @change="emit('change')"
      >
        <el-option
          v-for="item in TYPE_OPTIONS"
          :key="item.value"
          :label="item.label"
          :value="item.value"
        />
      </el-select>
      <el-select
        v-model="filters.priority"
        placeholder="优先级"
        clearable
        style="width: 130px"
        @change="emit('change')"
      >
        <el-option
          v-for="item in PRIORITY_OPTIONS"
          :key="item.value"
          :label="item.label"
          :value="item.value"
        />
      </el-select>
      <el-tooltip placement="top" content="存在未完成前置任务的任务即为受阻">
        <el-select
          v-model="filters.blocked"
          placeholder="受阻"
          clearable
          style="width: 110px"
          @change="emit('change')"
        >
          <el-option label="仅受阻" value="true" />
          <el-option label="不受阻" value="false" />
        </el-select>
      </el-tooltip>
    </div>

    <div class="filters__quick">
      <el-checkbox-button :model-value="onlyMine" @change="emit('toggle', 'mine')">
        只看我的
      </el-checkbox-button>
      <el-checkbox-button :model-value="onlyBlocked" @change="emit('toggle', 'blocked')">
        只看阻塞
      </el-checkbox-button>
      <el-checkbox-button :model-value="onlyReview" @change="emit('toggle', 'review')">
        待我验收
      </el-checkbox-button>
      <el-checkbox-button :model-value="onlyRevalidation" @change="emit('toggle', 'revalidation')">
        需复核
      </el-checkbox-button>
    </div>
  </div>
</template>

<style scoped>
.filters__row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 10px;
}
.filters__quick {
  display: flex;
  gap: 8px;
  margin-bottom: 12px;
}
</style>
