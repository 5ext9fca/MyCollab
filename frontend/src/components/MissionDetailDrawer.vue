<script setup lang="ts">
/**
 * F5 detail drawer: shows a mission's own data, its three relation kinds
 * (prerequisites / dependents / parent+children) separately, submission
 * history, and the controlled actions the current user may run.
 *
 * Edits and evidence submission stay on the full detail page; the drawer only
 * offers the quick, state-machine-safe actions plus a link to the full page.
 */
import AssistancePanel from './AssistancePanel.vue'
import AgentPanel from './AgentPanel.vue'
import CodeReport from './CodeReport.vue'
import { computed, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'

import { ApiException } from '../api/client'
import { listTeamMembers } from '../api/auth'
import {
  addDependency,
  cancelMission,
  claimMission,
  getMission,
  listDependencies,
  listMissions,
  listSubmissions,
  releaseMission,
  removeDependency,
  reopenMission,
  reviewMission,
  transferReview,
} from '../api/missions'
import type {
  Mission,
  MissionPrerequisiteRef,
  MissionRef,
  MissionSubmission,
  ReviewDecision,
  User,
} from '../api/types'
import {
  BUILD_STATUS_LABELS,
  MILESTONE_STATUS_LABELS,
  SUBMISSION_OUTCOME_LABELS,
} from '../missionMeta'
import MarkdownContent from './MarkdownContent.vue'
import MissionDesignLink from './MissionDesignLink.vue'
import MissionSubscription from './MissionSubscription.vue'
import MissionSchedule from './MissionSchedule.vue'
import StatusTag from './StatusTag.vue'

const props = defineProps<{ missionId: string | null; open: boolean }>()
const emit = defineEmits<{
  (event: 'close'): void
  (event: 'changed'): void
  (event: 'focus', id: string): void
}>()

const router = useRouter()

const mission = ref<Mission | null>(null)
const prerequisites = ref<MissionPrerequisiteRef[]>([])
const dependents = ref<MissionRef[]>([])
const submissions = ref<MissionSubmission[]>([])
const members = ref<User[]>([])
const loading = ref(false)

const allowed = computed(() => mission.value?.allowed_actions ?? [])
const children = computed(() => mission.value?.children ?? [])
const currentSubmission = computed(
  () => submissions.value.find((item) => item.id === mission.value?.current_submission) ?? null,
)
const succeededBuilds = computed(() =>
  (currentSubmission.value?.build_references ?? []).filter((build) => build.status === 'Succeeded'),
)

async function load() {
  if (!props.missionId) {
    mission.value = null
    return
  }
  loading.value = true
  try {
    const id = props.missionId
    mission.value = await getMission(id)
    const [deps, subs] = await Promise.all([
      listDependencies(id),
      listSubmissions(id, { page_size: 50 }),
    ])
    prerequisites.value = deps.prerequisites
    dependents.value = deps.dependents
    submissions.value = subs.results
  } catch (error) {
    if (error instanceof ApiException && error.status === 404) {
      mission.value = null
      ElMessage.warning('任务不存在或已失去访问权')
      emit('close')
    } else {
      ElMessage.error(error instanceof ApiException ? error.message : '加载失败')
    }
  } finally {
    loading.value = false
  }
}

watch(() => props.missionId, load, { immediate: true })

watch(
  () => props.open,
  async (isOpen) => {
    if (isOpen && !members.value.length) {
      try {
        members.value = await listTeamMembers()
      } catch {
        members.value = []
      }
    }
  },
)

function reportError(error: unknown, fallback = '操作失败') {
  if (error instanceof ApiException) {
    if (error.status === 409) {
      ElMessage.warning(error.message)
      void load()
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
    await load()
    emit('changed')
    ElMessage.success(successMessage)
    return true
  } catch (error) {
    reportError(error)
    return false
  }
}

const onClaim = () =>
  mission.value && run(() => claimMission(mission.value!.id, mission.value!.version), '认领成功')
const onRelease = () =>
  mission.value && run(() => releaseMission(mission.value!.id, mission.value!.version), '已退出')

async function onReopen() {
  if (!mission.value) return
  try {
    const { value } = await ElMessageBox.prompt(
      '请填写重新打开原因。历史提交与验收记录会保留。',
      '重新打开',
      {
        inputType: 'textarea',
        inputValidator: (text: string) => (text.trim() ? true : '必须填写原因'),
      },
    )
    await run(() => reopenMission(mission.value!.id, value, mission.value!.version), '已重新打开')
  } catch {
    /* cancelled */
  }
}

async function onCancel() {
  if (!mission.value) return
  try {
    const { value } = await ElMessageBox.prompt('请填写取消原因（子任务必填）', '取消任务', {
      inputType: 'textarea',
    })
    await run(() => cancelMission(mission.value!.id, value ?? '', mission.value!.version), '已取消')
  } catch {
    /* cancelled */
  }
}

// --- review --------------------------------------------------------------- //
const reviewDialogVisible = ref(false)
const reviewDecision = ref<ReviewDecision>('accept')
const reviewComment = ref('')
const reviewBuildId = ref<string | null>(null)

function openReview(decision: ReviewDecision) {
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
        mission.value!.id,
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

// --- transfer review ------------------------------------------------------ //
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
        mission.value!.id,
        transferReviewerId.value!,
        transferReason.value,
        mission.value!.version,
      ),
    '已转交验收',
  )
  if (ok) transferDialogVisible.value = false
}

// --- dependencies --------------------------------------------------------- //
const depSearch = ref('')
const depOptions = ref<Mission[]>([])
const depSelected = ref<string | null>(null)
const depLoading = ref(false)

async function searchDependencies(keyword: string) {
  if (!keyword.trim()) {
    depOptions.value = []
    return
  }
  depLoading.value = true
  try {
    const data = await listMissions({ search: keyword, page_size: 20 })
    depOptions.value = data.results.filter((item) => item.id !== props.missionId)
  } catch {
    depOptions.value = []
  } finally {
    depLoading.value = false
  }
}

async function onAddDependency() {
  if (!mission.value || !depSelected.value) return
  const ok = await run(
    () => addDependency(mission.value!.id, depSelected.value!, mission.value!.version),
    '已添加前置依赖',
  )
  if (ok) {
    depSelected.value = null
    depSearch.value = ''
    depOptions.value = []
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
    await removeDependency(mission.value.id, edge.dependency_id, mission.value.version)
    await load()
    emit('changed')
    ElMessage.success('已移除依赖')
  } catch (error) {
    reportError(error)
  }
}

function openFullDetail() {
  if (!mission.value) return
  router.push({ name: 'mission-detail', params: { id: mission.value.id } })
}

const formatDate = (value: string | null) => (value ? new Date(value).toLocaleString() : '')
</script>

<template>
  <el-drawer
    :model-value="open"
    size="420px"
    :with-header="true"
    title="任务详情"
    @update:model-value="(value: boolean) => !value && emit('close')"
  >
    <div v-loading="loading" class="drawer">
      <template v-if="mission">
        <div class="drawer__head">
          <h3 class="drawer__title">{{ mission.title }}</h3>
          <StatusTag :status="mission.status" />
        </div>
        <div class="tag-row">
          <el-tag size="small" type="info" disable-transitions>#{{ mission.id.slice(0, 8) }}</el-tag>
          <el-tag size="small" disable-transitions>{{ mission.type }}</el-tag>
          <el-tag size="small" disable-transitions>{{ mission.priority }}</el-tag>
          <el-tag v-if="mission.is_blocked" type="warning" size="small" disable-transitions>受阻</el-tag>
          <el-tag v-if="mission.needs_dependency_review" type="danger" size="small" disable-transitions>需复核</el-tag>
          <el-tag v-if="mission.milestone" type="success" size="small" disable-transitions>
            {{ mission.milestone.name }}（{{ MILESTONE_STATUS_LABELS[mission.milestone.status] }}）
          </el-tag>
        </div>

        <el-alert
          v-if="mission.needs_dependency_review"
          type="error"
          :closable="false"
          show-icon
          class="drawer__alert"
          title="前置任务已不满足，需要复核；重新打开会保留全部历史并要求填写原因"
        />
        <el-alert
          v-else-if="mission.is_blocked && mission.status === 'Submitted'"
          type="warning"
          :closable="false"
          show-icon
          class="drawer__alert"
          title="存在未完成前置任务，暂时无法验收通过；可退回后等待前置完成"
        />
        <el-alert
          v-if="mission.milestone_closed"
          type="info"
          :closable="false"
          show-icon
          class="drawer__alert"
          title="目标里程碑已关闭，重新打开前需先恢复里程碑"
        />
        <el-alert
          v-if="mission.reviewer_missing"
          type="warning"
          :closable="false"
          show-icon
          class="drawer__alert"
          title="验收者无效或缺失，提交或验收前需重新指定"
        />

        <div class="drawer__section">
          <div class="meta">
            发起者：{{ mission.creator.display_name }} ·
            认领者：{{ mission.assignee?.display_name ?? '待认领' }} ·
            验收者：{{ mission.reviewer?.display_name ?? '缺失' }}
          </div>
        </div>

        <div class="drawer__actions">
          <el-button v-if="allowed.includes('claim')" type="primary" size="small" @click="onClaim">
            认领
          </el-button>
          <el-button v-if="allowed.includes('release')" size="small" @click="onRelease">退出</el-button>
          <el-button
            v-if="allowed.includes('review')"
            type="success"
            size="small"
            @click="openReview('accept')"
          >
            验收
          </el-button>
          <el-button
            v-if="allowed.includes('review')"
            type="warning"
            plain
            size="small"
            @click="openReview('reject')"
          >
            退回
          </el-button>
          <el-button
            v-if="allowed.includes('transfer_review')"
            size="small"
            @click="openTransfer"
          >
            转交验收
          </el-button>
          <el-button v-if="allowed.includes('reopen')" size="small" @click="onReopen">
            重新打开
          </el-button>
          <el-button v-if="allowed.includes('cancel')" type="danger" plain size="small" @click="onCancel">
            取消
          </el-button>
          <el-button size="small" @click="openFullDetail">完整详情页</el-button>
        </div>

        <el-tabs class="drawer__tabs">
          <el-tab-pane label="内容">
            <h4>背景与目标</h4>
            <MissionDesignLink :element="mission.design_element" :assets="mission.assets" />
            <MissionSubscription v-if="mission" :mission-id="mission.id" />
            <MissionSchedule :mission="mission" />
            <MarkdownContent :source="mission.content" />
            <AgentPanel records-only v-if="open" :key="mission.id" :mission="mission" />
            <h4>验收标准</h4>
            <MarkdownContent :source="mission.acceptance_criteria" />
          </el-tab-pane>

          <el-tab-pane label="关系">
            <h4>前置依赖（{{ prerequisites.length }}）</h4>
            <el-empty
              v-if="!prerequisites.length"
              description="没有显式前置依赖"
              :image-size="50"
            />
            <ul v-else class="drawer__list">
              <li v-for="edge in prerequisites" :key="edge.dependency_id">
                <span>{{ edge.title }}</span>
                <el-tag size="small" :type="edge.status === 'Done' ? 'success' : 'warning'">
                  {{ edge.status }}
                </el-tag>
                <el-button link type="primary" size="small" @click="emit('focus', edge.id)">
                  定位
                </el-button>
                <el-button
                  v-if="allowed.includes('manage_dependencies')"
                  link
                  type="danger"
                  size="small"
                  @click="onRemoveDependency(edge)"
                >
                  移除
                </el-button>
              </li>
            </ul>
            <div v-if="allowed.includes('manage_dependencies')" class="drawer__dep-add">
              <el-select
                v-model="depSelected"
                remote
                filterable
                clearable
                reserve-keyword
                placeholder="搜索并添加前置任务"
                :remote-method="searchDependencies"
                :loading="depLoading"
              >
                <el-option
                  v-for="option in depOptions"
                  :key="option.id"
                  :label="option.title"
                  :value="option.id"
                />
              </el-select>
              <el-button size="small" type="primary" :disabled="!depSelected" @click="onAddDependency">
                添加
              </el-button>
            </div>

            <h4>下游任务（{{ dependents.length }}）</h4>
            <el-empty v-if="!dependents.length" description="没有下游任务" :image-size="50" />
            <ul v-else class="drawer__list">
              <li v-for="item in dependents" :key="item.id">
                <span>{{ item.title }}</span>
                <el-button link type="primary" size="small" @click="emit('focus', item.id)">
                  定位
                </el-button>
              </li>
            </ul>

            <h4>父子关系</h4>
            <div class="meta">
              父任务：
              <template v-if="mission.parent">
                {{ mission.parent.slice(0, 8) }}
              </template>
              <template v-else>无</template>
            </div>
            <el-empty v-if="!children.length" description="没有子任务" :image-size="50" />
            <ul v-else class="drawer__list">
              <li v-for="child in children" :key="child.id">
                <span>{{ child.title }}（{{ child.status }}）</span>
                <el-button link type="primary" size="small" @click="emit('focus', child.id)">
                  定位
                </el-button>
              </li>
            </ul>
          </el-tab-pane>

          <el-tab-pane label="成果与验收">
            <el-empty v-if="!submissions.length" description="还没有提交记录" :image-size="50" />
            <div v-for="item in submissions" :key="item.id" class="drawer__submission">
              <div class="drawer__submission-head">
                <span class="meta">
                  {{ item.submitted_by.display_name }} · {{ formatDate(item.submitted_at) }}
                </span>
                <el-tag
                  size="small"
                  :type="
                    item.outcome === 'Accepted'
                      ? 'success'
                      : item.outcome === 'Rejected'
                        ? 'danger'
                        : 'warning'
                  "
                >
                  {{ SUBMISSION_OUTCOME_LABELS[item.outcome] }}
                </el-tag>
              </div>
              <MarkdownContent :source="item.description" />
              <CodeReport v-for="artifact in item.code_artifacts" :key="artifact.execution_id" :report="artifact.report" :patch-url="artifact.patch_url" />
            <el-card v-if="item.execution_artifacts?.length" shadow="never"><h4>本轮图像成果</h4><p v-for="artifact in item.execution_artifacts" :key="artifact.candidate_id"><a class="app-link" :href="artifact.url">{{ artifact.name }} · 版本 {{ artifact.version }}</a></p></el-card>
              <div v-if="item.build_references.length" class="meta">
                构建：
                <span v-for="build in item.build_references" :key="build.id">
                  {{ build.build_id }}（{{ BUILD_STATUS_LABELS[build.status] }}）
                </span>
              </div>
              <div v-if="item.reviewed_at" class="meta">
                验收：{{ item.reviewed_by?.display_name ?? '—' }}
              </div>
            </div>
          </el-tab-pane>
        </el-tabs>
      </template>

      <el-empty v-else-if="!loading" description="选择一个任务查看详情" />
    </div>
  </el-drawer>

  <el-dialog
    v-model="reviewDialogVisible"
    :title="reviewDecision === 'accept' ? '验收通过' : '退回任务'"
    width="520px"
    append-to-body
  >
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
      <el-form-item :label="reviewDecision === 'accept' ? '验收说明（无构建时必填）' : '退回意见（必填）'">
        <el-input v-model="reviewComment" type="textarea" :rows="3" />
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="reviewDialogVisible = false">取消</el-button>
      <el-button
        :type="reviewDecision === 'accept' ? 'success' : 'warning'"
        @click="confirmReview"
      >
        {{ reviewDecision === 'accept' ? '确认通过' : '确认退回' }}
      </el-button>
    </template>
  </el-dialog>

  <el-dialog v-model="transferDialogVisible" title="转交验收" width="420px" append-to-body>
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
        <el-input v-model="transferReason" type="textarea" :rows="2" />
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="transferDialogVisible = false">取消</el-button>
      <el-button type="primary" @click="confirmTransfer">确认转交</el-button>
    </template>
  </el-dialog>
</template>

<style scoped>
.drawer__head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 8px;
}
.drawer__title {
  margin: 0 0 6px;
  font-size: 16px;
}
.drawer__alert {
  margin-top: 8px;
}
.drawer__section {
  margin-top: 12px;
}
.drawer__actions {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin: 12px 0;
}
.drawer__tabs {
  margin-top: 8px;
}
.drawer__list {
  margin: 0 0 8px;
  padding-left: 0;
  list-style: none;
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.drawer__list li {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
}
.drawer__dep-add {
  display: flex;
  gap: 6px;
  margin-bottom: 12px;
}
.drawer__submission {
  border-top: 1px solid var(--el-border-color);
  padding-top: 8px;
  margin-top: 8px;
}
.drawer__submission-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 4px;
}
</style>
