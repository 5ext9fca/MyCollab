<script setup lang="ts">
import BlockedLink from '../components/BlockedLink.vue'
import { computed, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'

import { ApiException } from '../api/client'
import { getMilestone, transitionMilestone, updateMilestone } from '../api/milestones'
import { listMissions } from '../api/missions'
import type { Milestone, MilestoneStatus, Mission } from '../api/types'
import { useAuthStore } from '../stores/auth'
import {
  MILESTONE_STATUS_LABELS,
  MILESTONE_STATUS_TAG,
  PRIORITY_TAG,
  TYPE_LABELS,
  TYPE_TAG,
} from '../missionMeta'
import StatusTag from '../components/StatusTag.vue'

const props = defineProps<{ id: string }>()
const router = useRouter()
const auth = useAuthStore()

const milestone = ref<Milestone | null>(null)
const missions = ref<Mission[]>([])
const loading = ref(false)
const editing = ref(false)

const canManage = computed(
  () =>
    !!milestone.value &&
    (auth.user?.is_staff || milestone.value.created_by.id === auth.user?.id),
)

const TRANSITIONS: Record<
  MilestoneStatus,
  { to: MilestoneStatus; label: string; type: 'primary' | 'success' | 'warning' | 'danger'; needsReason?: boolean }[]
> = {
  Planned: [
    { to: 'Active', label: '开始', type: 'primary' },
    { to: 'Cancelled', label: '取消', type: 'danger' },
  ],
  Active: [
    { to: 'Completed', label: '完成', type: 'success' },
    { to: 'Cancelled', label: '取消', type: 'danger' },
  ],
  Completed: [{ to: 'Active', label: '恢复为进行中', type: 'warning', needsReason: true }],
  Cancelled: [{ to: 'Active', label: '恢复为进行中', type: 'warning', needsReason: true }],
}

const transitions = computed(() =>
  milestone.value ? TRANSITIONS[milestone.value.status] : [],
)

function progressText(): string {
  const current = milestone.value
  if (!current) return ''
  if (current.progress === null) return '无有效任务'
  return `${Math.round(current.progress * 100)}%（${current.mission_counts.done}/${current.mission_counts.effective_total}）`
}

async function load() {
  loading.value = true
  try {
    milestone.value = await getMilestone(props.id)
    missions.value = (await listMissions({ milestone: props.id, page_size: 100 })).results
  } catch (error) {
    if (error instanceof ApiException && error.status === 404) {
      ElMessage.error('里程碑不存在')
      await router.push({ name: 'milestones' })
    } else {
      ElMessage.error(error instanceof ApiException ? error.message : '加载失败')
    }
  } finally {
    loading.value = false
  }
}

async function onTransition(to: MilestoneStatus, needsReason?: boolean) {
  if (!milestone.value) return
  let reason = ''
  if (needsReason) {
    try {
      const result = await ElMessageBox.prompt('恢复里程碑必须记录原因', '恢复里程碑', {
        inputType: 'textarea',
        inputValidator: (text: string) => (text.trim() ? true : '必须填写原因'),
      })
      reason = result.value
    } catch {
      return
    }
  } else {
    try {
      await ElMessageBox.confirm(`确认将里程碑置为「${MILESTONE_STATUS_LABELS[to]}」？`, '变更状态', {
        type: 'warning',
      })
    } catch {
      return
    }
  }
  try {
    milestone.value = await transitionMilestone(props.id, to, milestone.value.version, reason)
    ElMessage.success('状态已更新')
  } catch (error) {
    if (error instanceof ApiException && error.status === 409) {
      ElMessage.warning(error.message)
      await load()
    } else {
      ElMessage.error(error instanceof ApiException ? error.message : '操作失败')
    }
  }
}

// --- edit --------------------------------------------------------------- //
const form = reactive({ name: '', description: '', due_date: '' })

function startEdit() {
  if (!milestone.value) return
  form.name = milestone.value.name
  form.description = milestone.value.description
  form.due_date = milestone.value.due_date ?? ''
  editing.value = true
}

async function saveEdit() {
  if (!milestone.value) return
  if (!form.name.trim()) {
    ElMessage.warning('名称不能为空')
    return
  }
  try {
    milestone.value = await updateMilestone(props.id, {
      expected_version: milestone.value.version,
      name: form.name,
      description: form.description,
      due_date: form.due_date || null,
    })
    editing.value = false
    ElMessage.success('已保存')
  } catch (error) {
    ElMessage.error(error instanceof ApiException ? error.message : '保存失败')
  }
}

onMounted(load)
</script>

<template>
  <div v-loading="loading" class="page">
    <template v-if="milestone">
      <div class="page-header">
        <div>
          <h2 style="margin: 0">{{ milestone.name }}</h2>
          <div class="meta">
            创建者：{{ milestone.created_by.display_name }} · 目标日期：{{ milestone.due_date || '未设置' }}
          </div>
        </div>
        <div class="milestone-tags">
          <el-tag :type="MILESTONE_STATUS_TAG[milestone.status]" disable-transitions>
            {{ MILESTONE_STATUS_LABELS[milestone.status] }}
          </el-tag>
          <el-tag v-if="milestone.overdue" type="danger" disable-transitions>已延期</el-tag>
        </div>
      </div>

      <el-alert
        v-if="milestone.overdue"
        type="warning"
        :closable="false"
        show-icon
        style="margin-bottom: 12px"
        title="已超过目标日期，仍未完成"
      />

      <div class="detail-actions">
        <el-button v-if="canManage" @click="editing ? (editing = false) : startEdit()">
          {{ editing ? '取消编辑' : '编辑' }}
        </el-button>
        <el-button
          v-for="action in transitions"
          :key="action.to"
          :type="action.type"
          @click="onTransition(action.to, action.needsReason)"
        >
          {{ action.label }}
        </el-button>
      </div>

      <el-card v-if="editing" style="margin-bottom: 16px">
        <el-form label-position="top">
          <el-form-item label="名称">
            <el-input v-model="form.name" maxlength="200" />
          </el-form-item>
          <el-form-item label="目标说明">
            <el-input v-model="form.description" type="textarea" :rows="3" />
          </el-form-item>
          <el-form-item label="目标日期">
            <el-date-picker v-model="form.due_date" type="date" value-format="YYYY-MM-DD" style="width: 100%" />
          </el-form-item>
          <el-form-item>
            <el-button type="primary" @click="saveEdit">保存</el-button>
          </el-form-item>
        </el-form>
      </el-card>

      <section class="section">
        <h3>进度</h3>
        <div class="meta">
          {{ progressText() }} · 任务数：{{ milestone.mission_counts.total }}（有效
          {{ milestone.mission_counts.effective_total }}，已完成 {{ milestone.mission_counts.done }}）
        </div>
        <el-progress
          v-if="milestone.progress !== null"
          :percentage="Math.round(milestone.progress * 100)"
          style="max-width: 420px; margin-top: 8px"
        />
      </section>

      <section v-if="milestone.description" class="section">
        <h3>交付目标</h3>
        <p>{{ milestone.description }}</p>
      </section>

      <section class="section">
        <h3>关联任务</h3>
        <el-empty v-if="!missions.length" description="暂无关联任务" :image-size="60" />
        <div v-else class="mission-links">
          <div v-for="item in missions" :key="item.id" class="mission-link">
            <router-link class="app-link app-link--action" :to="{ name: 'mission-detail', params: { id: item.id } }">
              {{ item.title }}
            </router-link>
            <el-tag :type="TYPE_TAG[item.type]" size="small" disable-transitions>
              {{ TYPE_LABELS[item.type] }}
            </el-tag>
            <el-tag :type="PRIORITY_TAG[item.priority]" size="small" disable-transitions>
              {{ item.priority }}
            </el-tag>
            <BlockedLink v-if="item.is_blocked" :mission-id="item.id" />
            <StatusTag :status="item.status" />
          </div>
        </div>
      </section>
    </template>
  </div>
</template>

<style scoped>
.milestone-tags {
  display: flex;
  gap: 6px;
  align-items: center;
}

.mission-links {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.mission-link {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
</style>
