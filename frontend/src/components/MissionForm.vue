<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import type { FormInstance, FormRules } from 'element-plus'

import { listTeamMembers } from '../api/auth'
import { listMilestones } from '../api/milestones'
import { listTags } from '../api/missions'
import type { Milestone, MissionFormValues, User } from '../api/types'
import {
  MILESTONE_ACCEPTING_STATUSES,
  PRIORITY_OPTIONS,
  TYPE_OPTIONS,
} from '../missionMeta'
import MarkdownEditor from './MarkdownEditor.vue'
import DesignElementSelect from './DesignElementSelect.vue'
import AssetSelect from './AssetSelect.vue'

const props = withDefaults(
  defineProps<{
    initial?: Partial<MissionFormValues>
    submitLabel?: string
    loading?: boolean
  }>(),
  { submitLabel: '保存', loading: false },
)

const emit = defineEmits<{ (e: 'submit', payload: MissionFormValues): void }>()

const formRef = ref<FormInstance>()
const form = reactive<MissionFormValues>({
  design_element_id: props.initial?.design_element_id ?? null,
  asset_ids: [...(props.initial?.asset_ids ?? [])],
  planned_start_date: props.initial?.planned_start_date ?? null,
  planned_end_date: props.initial?.planned_end_date ?? null,
  title: props.initial?.title ?? '',
  content: props.initial?.content ?? '',
  acceptance_criteria: props.initial?.acceptance_criteria ?? '',
  tags: [...(props.initial?.tags ?? [])] as string[],
  type: props.initial?.type ?? 'Task',
  priority: props.initial?.priority ?? 'P2',
  reviewer_id: props.initial?.reviewer_id ?? null,
  milestone_id: props.initial?.milestone_id ?? null,
})
const tagOptions = ref<string[]>([])
const members = ref<User[]>([])
const milestones = ref<Milestone[]>([])
const rules: FormRules = {
  title: [{ required: true, message: '请填写标题', trigger: 'blur' }],
}

/** Closed milestones cannot receive tasks, but the current one stays visible. */
function milestoneDisabled(milestone: Milestone): boolean {
  return (
    !MILESTONE_ACCEPTING_STATUSES.includes(milestone.status) &&
    milestone.id !== form.milestone_id
  )
}

onMounted(async () => {
  const [tags, memberList, milestoneList] = await Promise.allSettled([
    listTags(),
    listTeamMembers(),
    listMilestones({ page_size: 100 }),
  ])
  if (tags.status === 'fulfilled') tagOptions.value = tags.value.map((tag) => tag.name)
  if (memberList.status === 'fulfilled') members.value = memberList.value
  if (milestoneList.status === 'fulfilled') milestones.value = milestoneList.value.results
})

async function onSubmit() {
  if (!formRef.value) return
  const valid = await formRef.value.validate().catch(() => false)
  if (!valid) return
  emit('submit', {
    design_element_id: form.design_element_id || null,
    asset_ids: [...(form.asset_ids ?? [])],
    planned_start_date: form.planned_start_date || null,
    planned_end_date: form.planned_end_date || null,
    title: form.title,
    content: form.content,
    acceptance_criteria: form.acceptance_criteria,
    tags: form.tags,
    type: form.type,
    priority: form.priority,
    reviewer_id: form.reviewer_id,
    milestone_id: form.milestone_id,
  })
}
</script>

<template>
  <el-form
    ref="formRef"
    :model="form"
    :rules="rules"
    label-position="top"
    @submit.prevent="onSubmit"
  >
    <el-form-item label="标题" prop="title">
      <el-input v-model="form.title" maxlength="200" show-word-limit placeholder="一句话说明要做什么" />
    </el-form-item>
    <el-form-item label="背景与目标（Markdown）">
      <MarkdownEditor v-model="form.content" :rows="5" placeholder="背景、目标与要求" />
    </el-form-item>
    <el-form-item label="验收标准（Markdown）">
      <MarkdownEditor v-model="form.acceptance_criteria" :rows="4" placeholder="可验证的完成标准" />
    </el-form-item>
    <el-row :gutter="16">
      <el-col :md="8" :sm="12">
        <el-form-item label="类型">
          <el-select v-model="form.type" style="width: 100%">
            <el-option v-for="item in TYPE_OPTIONS" :key="item.value" :label="item.label" :value="item.value" />
          </el-select>
        </el-form-item>
      </el-col>
      <el-col :md="8" :sm="12">
        <el-form-item label="优先级">
          <el-select v-model="form.priority" style="width: 100%">
            <el-option v-for="item in PRIORITY_OPTIONS" :key="item.value" :label="item.label" :value="item.value" />
          </el-select>
        </el-form-item>
      </el-col>
      <el-col :md="8" :sm="24">
        <el-form-item label="目标里程碑">
          <el-select
            v-model="form.milestone_id"
            clearable
            filterable
            placeholder="不关联里程碑"
            style="width: 100%"
          >
            <el-option
              v-for="milestone in milestones"
              :key="milestone.id"
              :label="milestone.name"
              :value="milestone.id"
              :disabled="milestoneDisabled(milestone)"
            />
          </el-select>
        </el-form-item>
      </el-col>
    </el-row>
    <el-row :gutter="16">
      <el-col :sm="12"><el-form-item label="计划开始日期（可空）"><el-date-picker v-model="form.planned_start_date" value-format="YYYY-MM-DD" type="date" placeholder="未计划" /></el-form-item></el-col>
      <el-col :sm="12"><el-form-item label="计划结束日期（可空）"><el-date-picker v-model="form.planned_end_date" value-format="YYYY-MM-DD" type="date" placeholder="未计划" /></el-form-item></el-col>
    </el-row>
    <p class="meta">日期仅用于计划与风险提示，不限制认领，不自动调整其他任务。</p>
    <el-form-item label="设计依据"><DesignElementSelect v-model="form.design_element_id" /></el-form-item>
    <el-form-item label="相关资产"><AssetSelect v-model="form.asset_ids" /></el-form-item>
    <el-form-item label="验收者">
      <el-select
        v-model="form.reviewer_id"
        clearable
        filterable
        placeholder="默认由发起者验收"
        style="width: 100%"
      >
        <el-option
          v-for="member in members"
          :key="member.id"
          :label="member.display_name"
          :value="member.id"
        />
      </el-select>
    </el-form-item>
    <el-form-item label="标签">
      <el-select
        v-model="form.tags"
        multiple
        filterable
        allow-create
        default-first-option
        placeholder="选择或输入标签"
        style="width: 100%"
      >
        <el-option v-for="name in tagOptions" :key="name" :label="name" :value="name" />
      </el-select>
    </el-form-item>
    <el-form-item>
      <el-button type="primary" native-type="submit" :loading="loading">
        {{ submitLabel }}
      </el-button>
    </el-form-item>
  </el-form>
</template>
