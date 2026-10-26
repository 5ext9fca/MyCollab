<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'

import { listTeamMembers } from '../api/auth'
import { ApiException } from '../api/client'
import {
  createComment,
  deleteComment,
  listComments,
  updateComment,
} from '../api/comments'
import {
  addDependency,
  cancelMission,
  claimMission,
  getMission,
  listDependencies,
  listEvents,
  listMissions,
  listSubmissions,
  releaseMission,
  removeDependency,
  reopenMission,
  reviewMission,
  submitMission,
  transferReview,
  updateMission,
} from '../api/missions'
import type {
  Comment,
  Mission,
  MissionEvent,
  MissionFormValues,
  MissionPrerequisiteRef,
  MissionRef,
  MissionSubmission,
  ReviewDecision,
  SubmissionBuildInput,
  SubmissionSourceInput,
  User,
} from '../api/types'
import {
  BUILD_STATUS_LABELS,
  BUILD_STATUS_OPTIONS,
  MILESTONE_STATUS_LABELS,
  PRIORITY_TAG,
  SOURCE_PROVIDER_OPTIONS,
  SUBMISSION_OUTCOME_LABELS,
  TYPE_LABELS,
  TYPE_TAG,
} from '../missionMeta'
import MarkdownContent from '../components/MarkdownContent.vue'
import MissionDesignLink from '../components/MissionDesignLink.vue'
import MissionSubscription from '../components/MissionSubscription.vue'
import MissionSchedule from '../components/MissionSchedule.vue'
import MarkdownEditor from '../components/MarkdownEditor.vue'
import MissionForm from '../components/MissionForm.vue'
import AssistancePanel from '../components/AssistancePanel.vue'
import AgentPanel from '../components/AgentPanel.vue'
import CodeReport from '../components/CodeReport.vue'
import type { CodeExecution } from '../api/codeExecutions'
import type { ExecutionCandidate } from '../api/executions'
import StatusTag from '../components/StatusTag.vue'

const props = defineProps<{ id: string }>()
const router = useRouter()

const mission = ref<Mission | null>(null)
const events = ref<MissionEvent[]>([])
const loading = ref(false)
const editing = ref(false)
const editBaseVersion = ref(1)
const members = ref<User[]>([])

const prerequisites = ref<MissionPrerequisiteRef[]>([])
const dependents = ref<MissionRef[]>([])
const submissions = ref<MissionSubmission[]>([])

const COMMENTS_PAGE_SIZE = 20
const comments = ref<Comment[]>([])
const commentTotal = ref(0)
const commentPage = ref(1)
const newComment = ref('')
const postingComment = ref(false)
const editingCommentId = ref<string | null>(null)
const editingCommentBody = ref('')

const allowed = computed(() => mission.value?.allowed_actions ?? [])
const children = computed(() => mission.value?.children ?? [])
const currentSubmission = computed(
  () =>
    submissions.value.find((item) => item.id === mission.value?.current_submission) ?? null,
)
const succeededBuilds = computed(() =>
  (currentSubmission.value?.build_references ?? []).filter((build) => build.status === 'Succeeded'),
)
const acceptBlockedByBuild = computed(
  () => (currentSubmission.value?.build_references.length ?? 0) > 0 && !succeededBuilds.value.length,
)
const blockingMissions = computed(() => {
  const ids = mission.value?.blocking_mission_ids ?? []
  return prerequisites.value.filter((item) => ids.includes(item.id))
})
const unfinishedChildren = computed(() => {
  const ids = mission.value?.unfinished_child_ids ?? []
  return children.value.filter((child) => ids.includes(child.id))
})

const ACTION_LABELS: Record<string, string> = {
  created: '创建了任务',
  updated: '修改了内容',
  claimed: '认领了任务',
  released: '退出了任务',
  submitted: '提交了成果',
  review_approved: '验收通过',
  review_rejected: '退回任务',
  cancelled: '取消了任务',
  child_created: '创建了子任务',
  type_changed: '修改了类型',
  priority_changed: '修改了优先级',
  reviewer_changed: '修改了验收者',
  review_transferred: '转交了验收',
  reopened: '重新打开了任务',
  milestone_changed: '修改了里程碑',
  design_element_changed: '修改了设计依据',
  assets_changed: '修改了相关资产',
  schedule_changed: '修改了计划日期',
  dependency_added: '添加了前置依赖',
  dependency_removed: '移除了前置依赖',
}

// --- data loading -------------------------------------------------------- //
async function refreshEvents() {
  events.value = (await listEvents(props.id)).results
}

async function refreshComments(page = 1) {
  const data = await listComments(props.id, { page, page_size: COMMENTS_PAGE_SIZE })
  comments.value = data.results
  commentTotal.value = data.count
  commentPage.value = page
}

async function refreshDependencies() {
  const data = await listDependencies(props.id)
  prerequisites.value = data.prerequisites
  dependents.value = data.dependents
}

async function refreshSubmissions() {
  submissions.value = (await listSubmissions(props.id, { page_size: 50 })).results
}

async function refreshSideData() {
  await Promise.all([refreshEvents(), refreshDependencies(), refreshSubmissions()])
}

async function reload() {
  mission.value = await getMission(props.id)
  await refreshSideData()
}

async function load() {
  loading.value = true
  try {
    await reload()
    await refreshComments()
  } catch (error) {
    if (error instanceof ApiException && error.status === 404) {
      ElMessage.error('任务不存在')
      await router.push({ name: 'square' })
    } else {
      ElMessage.error(error instanceof ApiException ? error.message : '加载失败')
    }
  } finally {
    loading.value = false
  }
}

onMounted(async () => {
  try {
    members.value = await listTeamMembers()
  } catch {
    members.value = []
  }
  await load()
})

// --- generic action runner ----------------------------------------------- //
function reportError(error: unknown, fallback = '操作失败') {
  if (error instanceof ApiException) {
    if (error.status === 409) {
      ElMessage.warning(error.message)
      void reload()
    } else {
      ElMessage.error(error.message)
    }
  } else {
    ElMessage.error(fallback)
  }
}

async function run(action: () => Promise<Mission>, successMessage: string): Promise<boolean> {
  try {
    mission.value = await action()
    await refreshSideData()
    ElMessage.success(successMessage)
    return true
  } catch (error) {
    reportError(error)
    return false
  }
}

const onClaim = () =>
  mission.value && run(() => claimMission(props.id, mission.value!.version), '认领成功')
const onRelease = () =>
  mission.value && run(() => releaseMission(props.id, mission.value!.version), '已退出')

// --- submit deliverables ------------------------------------------------- //
const submitDialogVisible = ref(false)
const submittingResult = ref(false)
const submitForm = reactive({
  description: '',
  verification_description: '',
  source_references: [] as SubmissionSourceInput[],
  build_references: [] as SubmissionBuildInput[],
  execution_candidate_ids: [] as string[],
  code_execution_ids: [] as string[],
})

function openSubmit() {
  submitForm.description = ''
  submitForm.verification_description = ''
  submitForm.source_references = []
  submitForm.build_references = []
  submitForm.execution_candidate_ids = []
  submitForm.code_execution_ids = []
  submitDialogVisible.value = true
}

function adoptExecution(candidates: ExecutionCandidate[]) {
  if (!submitDialogVisible.value) openSubmit()
  for (const candidate of candidates) {
    if (!candidate.url || submitForm.execution_candidate_ids.includes(candidate.id)) continue
    submitForm.execution_candidate_ids.push(candidate.id)
    submitForm.description += `\n![${candidate.name.replace(/[\[\]<>]/g, '')}](${candidate.url})\n`
  }
}

function adoptCodeExecution(execution: CodeExecution) {
  if (!execution.patch_url || !execution.report) return
  if (!submitDialogVisible.value) openSubmit()
  if (submitForm.code_execution_ids.includes(execution.id)) return
  submitForm.code_execution_ids.push(execution.id)
  submitForm.description += `\n[代码补丁：${execution.repository_key} · 版本 ${execution.version}](${execution.patch_url})\n基线：${execution.report.base_commit}\n`
}

function addSourceRow() {
  submitForm.source_references.push({
    provider: 'Git',
    repository: '',
    revision: '',
    browse_url: '',
  })
}

function addBuildRow() {
  submitForm.build_references.push({
    provider: '',
    build_id: '',
    platform: '',
    source_revision: '',
    artifact_url: '',
    status: 'Succeeded',
    verification_note: '',
  })
}

async function confirmSubmit() {
  if (!mission.value) return
  if (!submitForm.description.trim()) {
    ElMessage.warning('提交成果不能为空')
    return
  }
  const sources = submitForm.source_references.filter(
    (item) => item.repository.trim() && item.revision.trim(),
  )
  const builds = submitForm.build_references.filter(
    (item) => item.provider.trim() && item.build_id.trim() && item.platform.trim(),
  )
  if (!sources.length && !builds.length && !submitForm.verification_description.trim()) {
    ElMessage.warning('必须提供源码引用、构建引用或人工验证说明之一')
    return
  }
  submittingResult.value = true
  try {
    const ok = await run(
      () =>
        submitMission(
          props.id,
          {
            description: submitForm.description,
            verification_description: submitForm.verification_description,
            source_references: sources,
            build_references: builds,
            execution_candidate_ids: submitForm.execution_candidate_ids,
            code_execution_ids: submitForm.code_execution_ids,
          },
          mission.value!.version,
        ),
      '已提交，等待验收',
    )
    if (ok) submitDialogVisible.value = false
  } finally {
    submittingResult.value = false
  }
}

// --- review -------------------------------------------------------------- //
const reviewDialogVisible = ref(false)
const reviewDecision = ref<ReviewDecision>('accept')
const reviewComment = ref('')
const reviewBuildId = ref<string | null>(null)

function openReview(decision: ReviewDecision) {
  if (!currentSubmission.value) return
  reviewDecision.value = decision
  reviewComment.value = ''
  reviewBuildId.value = null
  reviewDialogVisible.value = true
}

async function confirmReview() {
  if (!mission.value || !currentSubmission.value) return
  const builds = currentSubmission.value.build_references
  if (reviewDecision.value === 'accept') {
    if (builds.length && !reviewBuildId.value) {
      ElMessage.warning('请选择所验证的构建版本')
      return
    }
    if (!builds.length && !reviewComment.value.trim()) {
      ElMessage.warning('没有构建时必须填写人工验证说明')
      return
    }
  } else if (!reviewComment.value.trim()) {
    ElMessage.warning('退回时必须填写验收意见')
    return
  }
  const ok = await run(
    () =>
      reviewMission(
        props.id,
        {
          submission_id: currentSubmission.value!.id,
          decision: reviewDecision.value,
          comment: reviewComment.value,
          verified_build_reference_id: reviewBuildId.value,
        },
        mission.value!.version,
      ),
    reviewDecision.value === 'accept' ? '已验收通过' : '已退回',
  )
  if (ok) reviewDialogVisible.value = false
}

// --- transfer review ----------------------------------------------------- //
const transferDialogVisible = ref(false)
const transferReviewerId = ref<number | null>(null)
const transferReason = ref('')

function openTransfer() {
  transferReviewerId.value = null
  transferReason.value = ''
  transferDialogVisible.value = true
}

async function confirmTransfer() {
  if (!mission.value) return
  if (!transferReviewerId.value) {
    ElMessage.warning('请选择新的验收者')
    return
  }
  if (!transferReason.value.trim()) {
    ElMessage.warning('转交验收必须填写原因')
    return
  }
  const ok = await run(
    () =>
      transferReview(
        props.id,
        transferReviewerId.value!,
        transferReason.value,
        mission.value!.version,
      ),
    '已转交验收',
  )
  if (ok) transferDialogVisible.value = false
}

// --- reopen / cancel ----------------------------------------------------- //
async function onReopen() {
  if (!mission.value) return
  try {
    const { value } = await ElMessageBox.prompt('请填写重新打开原因', '重新打开', {
      inputType: 'textarea',
      inputValidator: (text: string) => (text.trim() ? true : '必须填写原因'),
    })
    await run(() => reopenMission(props.id, value, mission.value!.version), '已重新打开')
  } catch {
    /* dialog cancelled */
  }
}

async function onCancel() {
  if (!mission.value) return
  try {
    const { value } = await ElMessageBox.prompt('请填写取消原因（子任务必填）', '取消任务', {
      inputType: 'textarea',
    })
    await run(() => cancelMission(props.id, value ?? '', mission.value!.version), '已取消')
  } catch {
    /* dialog cancelled */
  }
}

// --- dependencies -------------------------------------------------------- //
const depSearch = ref('')
const depOptions = ref<Mission[]>([])
const depSelected = ref<string | null>(null)
const addingDependency = ref(false)

async function searchDependencies(keyword: string) {
  if (!keyword.trim()) {
    depOptions.value = []
    return
  }
  try {
    const data = await listMissions({ search: keyword, page_size: 20 })
    depOptions.value = data.results.filter((item) => item.id !== props.id)
  } catch {
    depOptions.value = []
  }
}

async function onAddDependency() {
  if (!mission.value || !depSelected.value) return
  addingDependency.value = true
  try {
    const ok = await run(
      () => addDependency(props.id, depSelected.value!, mission.value!.version),
      '已添加前置依赖',
    )
    if (ok) {
      depSelected.value = null
      depSearch.value = ''
      depOptions.value = []
    }
  } finally {
    addingDependency.value = false
  }
}

async function onRemoveDependency(edge: MissionPrerequisiteRef) {
  if (!mission.value) return
  try {
    await ElMessageBox.confirm(`确认移除对「${edge.title}」的依赖？`, '移除依赖', {
      type: 'warning',
    })
  } catch {
    return
  }
  try {
    await removeDependency(props.id, edge.dependency_id, mission.value.version)
    await reload()
    ElMessage.success('已移除依赖')
  } catch (error) {
    reportError(error)
  }
}

// --- edit ---------------------------------------------------------------- //
async function onEditSubmit(values: MissionFormValues) {
  if (!mission.value) return
  const ok = await run(
    () =>
      updateMission(props.id, {
        expected_version: editBaseVersion.value,
        title: values.title,
        content: values.content,
        acceptance_criteria: values.acceptance_criteria,
        tags: values.tags,
        type: values.type,
        priority: values.priority,
        reviewer: values.reviewer_id,
        milestone: values.milestone_id,
        design_element_id: values.design_element_id,
        asset_ids: values.asset_ids,
        planned_start_date: values.planned_start_date,
        planned_end_date: values.planned_end_date,
      }),
    '已保存',
  )
  if (ok) editing.value = false
}

const onCreateChild = () => router.push({ name: 'mission-create', query: { parent: props.id } })

// --- comments ------------------------------------------------------------ //
async function onPostComment() {
  postingComment.value = true
  try {
    await createComment(props.id, newComment.value)
    newComment.value = ''
    await refreshComments(1)
    ElMessage.success('评论已发布')
  } catch (error) {
    ElMessage.error(error instanceof ApiException ? error.message : '评论失败')
  } finally {
    postingComment.value = false
  }
}

function startEditComment(comment: Comment) {
  editingCommentId.value = comment.id
  editingCommentBody.value = comment.content
}

function cancelEditComment() {
  editingCommentId.value = null
  editingCommentBody.value = ''
}

async function saveEditComment(comment: Comment) {
  try {
    await updateComment(comment.id, editingCommentBody.value)
    cancelEditComment()
    await refreshComments(commentPage.value)
    ElMessage.success('评论已更新')
  } catch (error) {
    ElMessage.error(error instanceof ApiException ? error.message : '保存失败')
  }
}

async function removeComment(comment: Comment) {
  try {
    await ElMessageBox.confirm('确认删除这条评论？', '删除评论', { type: 'warning' })
  } catch {
    return
  }
  try {
    await deleteComment(comment.id)
    await refreshComments(commentPage.value)
    ElMessage.success('评论已删除')
  } catch (error) {
    ElMessage.error(error instanceof ApiException ? error.message : '删除失败')
  }
}

function onCommentPage(page: number) {
  refreshComments(page)
}

function formatDate(value: string | null) {
  return value ? new Date(value).toLocaleString() : ''
}
</script>

<template>
  <div v-loading="loading" class="page">
    <template v-if="mission">
      <div class="page-header">
        <div>
          <h2 style="margin: 0">{{ mission.title }}</h2>
          <div class="meta">
            发起者：{{ mission.creator.display_name }}
            <template v-if="mission.assignee"> · 认领者：{{ mission.assignee.display_name }}</template>
            <template v-else> · 待认领</template>
            <template v-if="mission.reviewer"> · 验收者：{{ mission.reviewer.display_name }}</template>
            <template v-else> · 验收者缺失</template>
          </div>
        </div>
        <StatusTag :status="mission.status" />
      </div>

      <div class="tag-row" style="margin-bottom: 12px">
        <el-tag :type="TYPE_TAG[mission.type]" size="small" disable-transitions>
          {{ TYPE_LABELS[mission.type] }}
        </el-tag>
        <el-tag :type="PRIORITY_TAG[mission.priority]" size="small" disable-transitions>
          {{ mission.priority }}
        </el-tag>
        <el-tag v-if="mission.is_blocked" type="warning" size="small" disable-transitions>
          受阻
        </el-tag>
        <router-link
          v-if="mission.milestone"
          :to="{ name: 'milestone-detail', params: { id: mission.milestone.id } }"
        >
          <el-tag size="small" type="success" disable-transitions>
            里程碑：{{ mission.milestone.name }}（{{ MILESTONE_STATUS_LABELS[mission.milestone.status] }}）
          </el-tag>
        </router-link>
        <el-tag v-for="tag in mission.tags" :key="tag.id" size="small" type="info">
          {{ tag.name }}
        </el-tag>
      </div>

      <div v-if="mission.parent" class="meta" style="margin-bottom: 12px">
        父任务：
        <router-link :to="{ name: 'mission-detail', params: { id: mission.parent } }">
          {{ mission.parent }}
        </router-link>
      </div>

      <el-alert
        v-if="mission.is_blocked"
        type="warning"
        :closable="false"
        show-icon
        style="margin-bottom: 8px"
        title="存在未完成的前置任务，暂时无法提交或验收通过"
      >
        <template #default>
          受阻于：{{ blockingMissions.map((item) => item.title).join('、') }}
        </template>
      </el-alert>
      <el-alert
        v-if="mission.needs_dependency_review"
        type="error"
        :closable="false"
        show-icon
        style="margin-bottom: 8px"
        title="前置任务已不满足，需要复核：请确认后重新打开此任务"
      />
      <el-alert
        v-if="mission.reviewer_missing"
        type="warning"
        :closable="false"
        show-icon
        style="margin-bottom: 8px"
        title="验收者无效或缺失，提交或验收前请重新指定验收者"
      />
      <el-alert
        v-if="mission.milestone_closed"
        type="info"
        :closable="false"
        show-icon
        style="margin-bottom: 8px"
        title="目标里程碑已关闭，重新打开此任务前需先恢复里程碑"
      />

      <div class="detail-actions">
        <el-button v-if="allowed.includes('claim')" type="primary" @click="onClaim">认领</el-button>
        <el-button v-if="allowed.includes('release')" @click="onRelease">退出</el-button>
        <el-button v-if="allowed.includes('submit')" type="primary" @click="openSubmit">
          提交成果
        </el-button>
        <el-button v-if="allowed.includes('review')" type="success" @click="openReview('accept')">
          验收
        </el-button>
        <el-button
          v-if="allowed.includes('review')"
          type="warning"
          plain
          @click="openReview('reject')"
        >
          退回
        </el-button>
        <el-button
          v-if="allowed.includes('transfer_review')"
          type="warning"
          plain
          @click="openTransfer"
        >
          转交验收
        </el-button>
        <el-button v-if="allowed.includes('reopen')" @click="onReopen">重新打开</el-button>
        <el-button v-if="allowed.includes('edit')" @click="editing = !editing; if (editing) editBaseVersion = mission.version">
          {{ editing ? '取消编辑' : '编辑' }}
        </el-button>
        <el-button v-if="allowed.includes('cancel')" type="danger" plain @click="onCancel">
          取消
        </el-button>
        <el-button v-if="allowed.includes('create_child')" @click="onCreateChild">拆分任务</el-button>
      </div>

      <el-card v-if="editing" style="margin-bottom: 16px">
        <el-card v-if="editBaseVersion !== mission.version" shadow="never"><h3>服务器版本已变化，请比较后继续</h3><p>{{ mission.title }}</p><MarkdownContent :source="mission.content" /><MarkdownContent :source="mission.acceptance_criteria" /><el-button @click="editBaseVersion = mission.version">已比较，保留草稿并使用此版本保存</el-button></el-card>
        <MissionForm :object-id="mission.id" :base-version="editBaseVersion"
          :initial="{
            title: mission.title,
            content: mission.content,
            acceptance_criteria: mission.acceptance_criteria,
            tags: mission.tags.map((tag) => tag.name),
            type: mission.type,
            priority: mission.priority,
            reviewer_id: mission.reviewer?.id ?? null,
            milestone_id: mission.milestone?.id ?? null,
            design_element_id: mission.design_element?.id ?? null,
            asset_ids: mission.assets?.map(asset => asset.id) ?? [],
            planned_start_date: mission.planned_start_date,
            planned_end_date: mission.planned_end_date,
          }"
          submit-label="保存"
          @submit="onEditSubmit"
        />
      </el-card>

      <section class="section">
        <h3>背景与目标</h3>
        <MissionDesignLink :element="mission.design_element" :assets="mission.assets" />
        <MissionSubscription v-if="mission" :mission-id="mission.id" />
        <MissionSchedule :mission="mission" />
        <MarkdownContent :source="mission.content" />
      </section>

      <section class="section">
        <h3>验收标准</h3>
        <MarkdownContent :source="mission.acceptance_criteria" />
      </section>

      <AgentPanel :key="mission.id" :mission="mission" can-adopt @adopt-images="adoptExecution" @adopt-code="adoptCodeExecution" />

      <section v-if="currentSubmission" class="section">
        <h3>最新成果</h3>
        <MarkdownContent :source="currentSubmission.description" />
        <CodeReport v-for="artifact in currentSubmission.code_artifacts" :key="artifact.execution_id" :report="artifact.report" :patch-url="artifact.patch_url" />
        <el-card v-if="currentSubmission.execution_artifacts?.length" shadow="never"><h4>本轮图像成果</h4><p v-for="artifact in currentSubmission.execution_artifacts" :key="artifact.candidate_id"><a class="app-link" :href="artifact.url">{{ artifact.name }} · 版本 {{ artifact.version }}</a></p></el-card>
      </section>

      <section class="section">
        <h3>任务树（子任务）</h3>
        <el-empty v-if="!children.length" description="没有子任务" :image-size="60" />
        <div v-else class="link-list">
          <router-link
            v-for="child in children"
            :key="child.id"
            :to="{ name: 'mission-detail', params: { id: child.id } }"
          >
            {{ child.title }}（{{ child.status }}）
          </router-link>
        </div>
      </section>

      <section class="section">
        <h3>前置依赖</h3>
        <el-empty v-if="!prerequisites.length" description="没有前置依赖" :image-size="60" />
        <ul v-else class="edge-list">
          <li v-for="edge in prerequisites" :key="edge.dependency_id">
            <router-link :to="{ name: 'mission-detail', params: { id: edge.id } }">
              {{ edge.title }}
            </router-link>
            <el-tag size="small" :type="edge.status === 'Done' ? 'success' : 'warning'">
              {{ edge.status }}
            </el-tag>
            <el-button
              v-if="allowed.includes('manage_dependencies')"
              link
              type="danger"
              @click="onRemoveDependency(edge)"
            >
              移除
            </el-button>
          </li>
        </ul>
        <div v-if="allowed.includes('manage_dependencies')" class="dep-add">
          <el-select
            v-model="depSelected"
            remote
            filterable
            clearable
            reserve-keyword
            placeholder="搜索并选择前置任务"
            :remote-method="searchDependencies"
            :loading="addingDependency"
            style="width: 320px"
          >
            <el-option
              v-for="option in depOptions"
              :key="option.id"
              :label="option.title"
              :value="option.id"
            />
          </el-select>
          <el-button type="primary" :disabled="!depSelected" @click="onAddDependency">
            添加依赖
          </el-button>
        </div>
      </section>

      <section class="section">
        <h3>下游任务</h3>
        <el-empty v-if="!dependents.length" description="没有下游任务" :image-size="60" />
        <div v-else class="link-list">
          <router-link
            v-for="item in dependents"
            :key="item.id"
            :to="{ name: 'mission-detail', params: { id: item.id } }"
          >
            {{ item.title }}（{{ item.status }}）
          </router-link>
        </div>
      </section>

      <section class="section">
        <h3>未完成子任务</h3>
        <el-empty v-if="!unfinishedChildren.length" description="子任务均已完成" :image-size="60" />
        <div v-else class="link-list">
          <router-link
            v-for="child in unfinishedChildren"
            :key="child.id"
            :to="{ name: 'mission-detail', params: { id: child.id } }"
          >
            {{ child.title }}
          </router-link>
        </div>
      </section>

      <section class="section">
        <h3>成果提交与验收历史</h3>
        <el-empty v-if="!submissions.length" description="还没有提交记录" :image-size="60" />
        <div v-else class="submission-list">
          <el-card v-for="item in submissions" :key="item.id" class="submission" shadow="never">
            <div class="submission__head">
              <span class="meta">
                {{ item.submitted_by.display_name }} · {{ formatDate(item.submitted_at) }}
              </span>
              <el-tag size="small" :type="item.outcome === 'Accepted' ? 'success' : item.outcome === 'Rejected' ? 'danger' : 'warning'">
                {{ SUBMISSION_OUTCOME_LABELS[item.outcome] }}
              </el-tag>
            </div>
            <MarkdownContent :source="item.description" />
            <CodeReport v-for="artifact in item.code_artifacts" :key="artifact.execution_id" :report="artifact.report" :patch-url="artifact.patch_url" />
            <el-card v-if="item.execution_artifacts?.length" shadow="never"><h4>本轮图像成果</h4><p v-for="artifact in item.execution_artifacts" :key="artifact.candidate_id"><a class="app-link" :href="artifact.url">{{ artifact.name }} · 版本 {{ artifact.version }}</a></p></el-card>
            <div v-if="item.verification_description" class="submission__block">
              <strong>人工验证说明</strong>
              <MarkdownContent :source="item.verification_description" />
            </div>
            <div v-if="item.source_references.length" class="submission__block">
              <strong>源码引用</strong>
              <ul class="edge-list">
                <li v-for="ref in item.source_references" :key="ref.id">
                  {{ ref.provider }} · {{ ref.repository }} @ {{ ref.revision }}
                  <a v-if="ref.browse_url" :href="ref.browse_url" target="_blank" rel="noopener noreferrer">查看</a>
                </li>
              </ul>
            </div>
            <div v-if="item.build_references.length" class="submission__block">
              <strong>构建引用</strong>
              <ul class="edge-list">
                <li v-for="build in item.build_references" :key="build.id">
                  {{ build.provider }} · {{ build.build_id }} · {{ build.platform }} ·
                  {{ BUILD_STATUS_LABELS[build.status] }}
                  <a v-if="build.artifact_url" :href="build.artifact_url" target="_blank" rel="noopener noreferrer">下载</a>
                  <el-tag
                    v-if="item.verified_build_reference === build.id"
                    size="small"
                    type="success"
                  >
                    验收验证版本
                  </el-tag>
                </li>
              </ul>
            </div>
            <div v-if="item.reviewed_at" class="submission__block">
              <strong>验收</strong>
              <span class="meta">
                {{ item.reviewed_by?.display_name ?? '—' }} · {{ formatDate(item.reviewed_at) }}
              </span>
              <MarkdownContent :source="item.review_comment" />
            </div>
          </el-card>
        </div>
      </section>

      <section class="section">
        <h3>讨论</h3>
        <div class="comment-form">
          <MarkdownEditor
            v-model="newComment"
            :rows="3"
            placeholder="支持 Markdown，写下你的想法…"
          />
          <el-button
            type="primary"
            style="margin-top: 8px"
            :loading="postingComment"
            @click="onPostComment"
          >
            发表评论
          </el-button>
        </div>

        <el-empty v-if="!comments.length" description="还没有评论" :image-size="60" />
        <div v-else class="comment-list">
          <div v-for="comment in comments" :key="comment.id" class="comment">
            <div class="comment__head">
              <span class="meta">
                {{ comment.author.display_name }} ·
                {{ new Date(comment.updated_at).toLocaleString() }}
              </span>
              <span v-if="comment.can_edit" class="comment__actions">
                <el-button link type="primary" @click="startEditComment(comment)">编辑</el-button>
                <el-button link type="danger" @click="removeComment(comment)">删除</el-button>
              </span>
            </div>
            <template v-if="editingCommentId === comment.id">
              <MarkdownEditor v-model="editingCommentBody" :rows="3" />
              <div class="comment__actions" style="margin-top: 8px">
                <el-button size="small" type="primary" @click="saveEditComment(comment)">
                  保存
                </el-button>
                <el-button size="small" @click="cancelEditComment">取消</el-button>
              </div>
            </template>
            <MarkdownContent v-else :source="comment.content" />
          </div>
        </div>

        <el-pagination
          v-if="commentTotal > COMMENTS_PAGE_SIZE"
          background
          layout="prev, pager, next"
          :total="commentTotal"
          :page-size="COMMENTS_PAGE_SIZE"
          :current-page="commentPage"
          @current-change="onCommentPage"
        />
      </section>

      <section class="section">
        <h3>活动记录</h3>
        <el-timeline v-if="events.length">
          <el-timeline-item
            v-for="event in events"
            :key="event.id"
            :timestamp="new Date(event.created_at).toLocaleString()"
          >
            {{ event.actor.display_name }} {{ ACTION_LABELS[event.action] ?? event.action }}
          </el-timeline-item>
        </el-timeline>
        <el-empty v-else description="暂无记录" :image-size="60" />
      </section>
    </template>

    <el-dialog v-model="submitDialogVisible" title="提交成果" width="720px">
      <el-form label-position="top">
        <el-form-item label="成果说明（Markdown）">
          <MarkdownEditor
            v-model="submitForm.description"
            :rows="4"
            placeholder="成果说明、测试结果或链接（支持 Markdown）"
          />
        </el-form-item>
        <el-form-item label="人工验证说明（Markdown，无源码/构建时必填）">
          <el-card v-if="submitForm.execution_candidate_ids.length" shadow="never"><p>已关联 {{ submitForm.execution_candidate_ids.length }} 项图像成果。请填写人工验证说明后确认提交。</p><el-button @click="submitForm.execution_candidate_ids = []">清除成果关联</el-button></el-card>
          <el-card v-if="submitForm.code_execution_ids.length" shadow="never"><p>已关联 {{ submitForm.code_execution_ids.length }} 项代码成果。本地报告不等于独立验收，请填写人工验证说明。</p><el-button @click="submitForm.code_execution_ids = []">清除代码成果关联</el-button></el-card>
          <MarkdownEditor v-model="submitForm.verification_description" :rows="3" />
        </el-form-item>

        <div class="builder">
          <div class="builder__head">
            <strong>源码引用</strong>
            <el-button size="small" @click="addSourceRow">添加</el-button>
          </div>
          <div
            v-for="(source, index) in submitForm.source_references"
            :key="`src-${index}`"
            class="builder__row"
          >
            <el-select v-model="source.provider" style="width: 130px">
              <el-option
                v-for="item in SOURCE_PROVIDER_OPTIONS"
                :key="item.value"
                :label="item.label"
                :value="item.value"
              />
            </el-select>
            <el-input v-model="source.repository" placeholder="仓库" style="width: 180px" />
            <el-input v-model="source.revision" placeholder="revision / changelist" style="width: 180px" />
            <el-input v-model="source.browse_url" placeholder="浏览链接（可选）" style="width: 200px" />
            <el-button link type="danger" @click="submitForm.source_references.splice(index, 1)">
              删除
            </el-button>
          </div>
        </div>

        <div class="builder">
          <div class="builder__head">
            <strong>构建引用</strong>
            <el-button size="small" @click="addBuildRow">添加</el-button>
          </div>
          <div
            v-for="(build, index) in submitForm.build_references"
            :key="`build-${index}`"
            class="builder__row"
          >
            <el-input v-model="build.provider" placeholder="构建来源" style="width: 130px" />
            <el-input v-model="build.build_id" placeholder="build_id" style="width: 140px" />
            <el-input v-model="build.platform" placeholder="平台" style="width: 120px" />
            <el-select v-model="build.status" style="width: 120px">
              <el-option
                v-for="item in BUILD_STATUS_OPTIONS"
                :key="item.value"
                :label="item.label"
                :value="item.value"
              />
            </el-select>
            <el-input v-model="build.source_revision" placeholder="对应源码版本（可选）" style="width: 180px" />
            <el-input v-model="build.artifact_url" placeholder="产物链接（可选）" style="width: 180px" />
            <el-button link type="danger" @click="submitForm.build_references.splice(index, 1)">
              删除
            </el-button>
          </div>
        </div>
      </el-form>
      <template #footer>
        <el-button @click="submitDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="submittingResult" @click="confirmSubmit">提交</el-button>
      </template>
    </el-dialog>

    <el-dialog
      v-model="reviewDialogVisible"
      :title="reviewDecision === 'accept' ? '验收通过' : '退回任务'"
      width="600px"
    >
      <el-alert
        v-if="reviewDecision === 'accept' && acceptBlockedByBuild"
        type="error"
        :closable="false"
        show-icon
        title="本次提交没有构建成功的版本，无法通过验收；请退回后重新提交"
        style="margin-bottom: 12px"
      />
      <AssistancePanel v-if="reviewDialogVisible && mission && currentSubmission" kind="review_assist" :draft="{}" :current-comment="reviewComment" :object-id="mission.id" :base-version="mission.version" :submission-id="currentSubmission.id" :review-context="{ content: mission.content, acceptance_criteria: mission.acceptance_criteria, submission: currentSubmission }" @adopt="(field, value) => { if (field === 'comment') reviewComment = String(value) }" />
      <el-form label-position="top">
        <el-form-item v-if="reviewDecision === 'accept' && succeededBuilds.length" label="所验证的构建版本">
          <el-select v-model="reviewBuildId" placeholder="选择构建成功的版本" style="width: 100%">
            <el-option
              v-for="build in succeededBuilds"
              :key="build.id"
              :label="`${build.provider} · ${build.build_id} · ${build.platform}`"
              :value="build.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item
          :label="reviewDecision === 'accept' ? '验收说明（无构建时必填）' : '退回意见（必填）'"
        >
          <MarkdownEditor v-model="reviewComment" :rows="3" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="reviewDialogVisible = false">取消</el-button>
        <el-button
          :type="reviewDecision === 'accept' ? 'success' : 'warning'"
          :disabled="reviewDecision === 'accept' && acceptBlockedByBuild"
          @click="confirmReview"
        >
          {{ reviewDecision === 'accept' ? '确认通过' : '确认退回' }}
        </el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="transferDialogVisible" title="转交验收" width="480px">
      <el-form label-position="top">
        <el-form-item label="新的验收者">
          <el-select v-model="transferReviewerId" filterable placeholder="选择成员" style="width: 100%">
            <el-option
              v-for="member in members"
              :key="member.id"
              :label="member.display_name"
              :value="member.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="转交原因">
          <el-input v-model="transferReason" type="textarea" :rows="3" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="transferDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="confirmTransfer">确认转交</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.comment-form {
  margin-bottom: 16px;
}

.comment-list {
  margin-bottom: 12px;
}

.comment {
  padding: 12px 0;
  border-top: 1px solid var(--el-border-color);
}

.comment:first-child {
  border-top: none;
  padding-top: 0;
}

.comment__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 4px;
}

.comment__actions {
  display: flex;
  gap: 4px;
  white-space: nowrap;
}

.link-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.edge-list {
  margin: 0;
  padding-left: 18px;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.dep-add {
  display: flex;
  gap: 8px;
  margin-top: 10px;
}

.submission {
  margin-bottom: 12px;
}

.submission__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 6px;
}

.submission__block {
  margin-top: 8px;
}

.builder {
  margin-bottom: 16px;
}

.builder__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 6px;
}

.builder__row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}
</style>
