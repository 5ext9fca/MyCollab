<script setup lang="ts">
import CardListSort from '../components/CardListSort.vue'
import { reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'

import CardList from '../components/CardList.vue'
import { useCardList } from '../composables/useCardList'
import { ApiException } from '../api/client'
import { createMilestone, listMilestones } from '../api/milestones'
import type { Milestone, MilestoneStatus } from '../api/types'
import { MILESTONE_STATUS_LABELS, MILESTONE_STATUS_TAG } from '../missionMeta'

const ordering = ref('-created_at')
const statusFilter = ref<MilestoneStatus | ''>('')

const statusOptions: { label: string; value: MilestoneStatus | '' }[] = [
  { label: '全部', value: '' },
  { label: '计划中', value: 'Planned' },
  { label: '进行中', value: 'Active' },
  { label: '已完成', value: 'Completed' },
  { label: '已取消', value: 'Cancelled' },
]

const dialogVisible = ref(false)
const creating = ref(false)
const form = reactive({ name: '', description: '', due_date: '' })

const { items: milestones, total, loading, page, pageSize, reload: load } = useCardList(() => ({ status: statusFilter.value || undefined, ordering: ordering.value }), listMilestones, 10)
function progressText(milestone: Milestone): string {
  if (milestone.progress === null) return '无有效任务'
  return `${Math.round(milestone.progress * 100)}%（${milestone.mission_counts.done}/${milestone.mission_counts.effective_total}）`
}

function openCreate() {
  form.name = ''
  form.description = ''
  form.due_date = ''
  dialogVisible.value = true
}

async function confirmCreate() {
  if (!form.name.trim()) {
    ElMessage.warning('请填写里程碑名称')
    return
  }
  creating.value = true
  try {
    await createMilestone({
      name: form.name,
      description: form.description,
      due_date: form.due_date || null,
    })
    dialogVisible.value = false
    ElMessage.success('里程碑已创建')
    await load()
  } catch (error) {
    ElMessage.error(error instanceof ApiException ? error.message : '创建失败')
  } finally {
    creating.value = false
  }
}

</script>

<template>
  <div class="page">
    <div class="page-header">
      <h2>里程碑</h2>
      <el-button type="primary" @click="openCreate">新建里程碑</el-button>
    </div>

    <CardList :items="milestones" :total="total" :loading="loading" v-model:page="page" v-model:page-size="pageSize" empty-text="暂无里程碑">
    <template #filters><div class="toolbar toolbar--flush">
      <el-select v-model="statusFilter" style="width: 140px">
        <el-option v-for="item in statusOptions" :key="item.label" :label="item.label" :value="item.value" />
      </el-select>
      <CardListSort v-model="ordering" label="里程碑排序" :options="[{ label: '最新创建', value: '-created_at' }, { label: '最早创建', value: 'created_at' }, { label: '目标日期升序', value: 'due_date' }, { label: '名称升序', value: 'name' }]" />
      <el-button @click="load">查询</el-button>
    </div></template>

    <template #item="{ item: milestone }">
      <el-card class="milestone-card" shadow="never">
        <div class="milestone-card__row">
          <router-link class="app-link app-link--title" :to="{ name: 'milestone-detail', params: { id: milestone.id } }">
            {{ milestone.name }}
          </router-link>
          <div class="milestone-card__tags">
            <el-tag :type="MILESTONE_STATUS_TAG[milestone.status]" size="small" disable-transitions>
              {{ MILESTONE_STATUS_LABELS[milestone.status] }}
            </el-tag>
            <el-tag v-if="milestone.overdue" type="danger" size="small" disable-transitions>
              已延期
            </el-tag>
          </div>
        </div>
        <div class="meta">
          目标日期：{{ milestone.due_date || '未设置' }} · 进度：{{ progressText(milestone) }}
        </div>
        <div v-if="milestone.description" class="meta">{{ milestone.description }}</div>
      </el-card>
    </template>
    </CardList>

    <el-dialog v-model="dialogVisible" title="新建里程碑" width="480px">
      <el-form label-position="top">
        <el-form-item label="名称">
          <el-input v-model="form.name" maxlength="200" placeholder="如：首个可玩版本" />
        </el-form-item>
        <el-form-item label="目标说明">
          <el-input v-model="form.description" type="textarea" :rows="3" />
        </el-form-item>
        <el-form-item label="目标日期">
          <el-date-picker v-model="form.due_date" type="date" value-format="YYYY-MM-DD" style="width: 100%" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="creating" @click="confirmCreate">创建</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.milestone-card {
  margin-bottom: 16px;
}

.milestone-card__row {
  display: flex;
  align-items: flex-start;
  flex-wrap: wrap;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 6px;
}

.milestone-card__tags {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  align-items: center;
}
</style>
