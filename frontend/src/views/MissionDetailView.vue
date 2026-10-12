<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'

import { ApiException } from '../api/client'
import {
  createComment,
  deleteComment,
  listComments,
  updateComment,
} from '../api/comments'
import {
  cancelMission,
  claimMission,
  getMission,
  listEvents,
  releaseMission,
  reviewMission,
  submitMission,
  updateMission,
} from '../api/missions'
import type { Comment, Mission, MissionEvent, MissionWritePayload } from '../api/types'
import MarkdownContent from '../components/MarkdownContent.vue'
import MarkdownEditor from '../components/MarkdownEditor.vue'
import MissionForm from '../components/MissionForm.vue'
import StatusTag from '../components/StatusTag.vue'

const props = defineProps<{ id: string }>()
const router = useRouter()

const mission = ref<Mission | null>(null)
const events = ref<MissionEvent[]>([])
const loading = ref(false)
const editing = ref(false)

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
}

async function refreshEvents() {
  const data = await listEvents(props.id)
  events.value = data.results
}

async function refreshComments(page = 1) {
  const data = await listComments(props.id, { page, page_size: COMMENTS_PAGE_SIZE })
  comments.value = data.results
  commentTotal.value = data.count
  commentPage.value = page
}

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

async function load() {
  loading.value = true
  try {
    mission.value = await getMission(props.id)
    await refreshEvents()
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

async function run(action: () => Promise<Mission>, successMessage: string): Promise<boolean> {
  try {
    mission.value = await action()
    await refreshEvents()
    ElMessage.success(successMessage)
    return true
  } catch (error) {
    if (error instanceof ApiException && error.status === 409) {
      ElMessage.warning(error.message)
      await load()
    } else if (error instanceof ApiException) {
      ElMessage.error(error.message)
    } else {
      ElMessage.error('操作失败')
    }
    return false
  }
}

const onClaim = () => run(() => claimMission(props.id), '认领成功')
const onRelease = () => run(() => releaseMission(props.id), '已退出')

const resultDialogVisible = ref(false)
const submitResult = ref('')
const submittingResult = ref(false)

function onSubmitResult() {
  submitResult.value = ''
  resultDialogVisible.value = true
}

async function confirmSubmitResult() {
  if (!submitResult.value.trim()) {
    ElMessage.warning('提交成果不能为空')
    return
  }
  submittingResult.value = true
  try {
    const ok = await run(() => submitMission(props.id, submitResult.value), '已提交，等待验收')
    if (ok) resultDialogVisible.value = false
  } finally {
    submittingResult.value = false
  }
}

async function onApprove() {
  try {
    await ElMessageBox.confirm('确认验收通过？', '验收', { type: 'success' })
    await run(() => reviewMission(props.id, true), '已验收通过')
  } catch {
    /* dialog cancelled */
  }
}

async function onReject() {
  try {
    const { value } = await ElMessageBox.prompt('请填写退回意见', '退回', { inputType: 'textarea' })
    await run(() => reviewMission(props.id, false, value), '已退回')
  } catch {
    /* dialog cancelled */
  }
}

async function onCancel() {
  try {
    const { value } = await ElMessageBox.prompt('请填写取消原因（子任务必填）', '取消任务', {
      inputType: 'textarea',
    })
    await run(() => cancelMission(props.id, value), '已取消')
  } catch {
    /* dialog cancelled */
  }
}

async function onEditSubmit(payload: MissionWritePayload) {
  if (!mission.value) return
  const version = mission.value.version
  await run(() => updateMission(props.id, { ...payload, version }), '已保存')
  editing.value = false
}

const onCreateChild = () => router.push({ name: 'mission-create', query: { parent: props.id } })

onMounted(load)
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
          </div>
        </div>
        <StatusTag :status="mission.status" />
      </div>

      <div v-if="mission.tags.length" class="tag-row" style="margin-bottom: 12px">
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

      <div class="detail-actions">
        <el-button v-if="allowed.includes('claim')" type="primary" @click="onClaim">认领</el-button>
        <el-button v-if="allowed.includes('release')" @click="onRelease">退出</el-button>
        <el-button v-if="allowed.includes('submit')" type="primary" @click="onSubmitResult">
          提交成果
        </el-button>
        <el-button v-if="allowed.includes('review')" type="success" @click="onApprove">
          验收通过
        </el-button>
        <el-button v-if="allowed.includes('review')" type="warning" @click="onReject">退回</el-button>
        <el-button v-if="allowed.includes('edit')" @click="editing = !editing">
          {{ editing ? '取消编辑' : '编辑' }}
        </el-button>
        <el-button v-if="allowed.includes('cancel')" type="danger" plain @click="onCancel">
          取消
        </el-button>
        <el-button v-if="allowed.includes('create_child')" @click="onCreateChild">拆分任务</el-button>
      </div>

      <el-card v-if="editing" style="margin-bottom: 16px">
        <MissionForm
          :initial="{
            title: mission.title,
            content: mission.content,
            acceptance_criteria: mission.acceptance_criteria,
            tags: mission.tags.map((tag) => tag.name),
          }"
          submit-label="保存"
          @submit="onEditSubmit"
        />
      </el-card>

      <section class="section">
        <h3>背景与目标</h3>
        <MarkdownContent :source="mission.content" />
      </section>

      <section class="section">
        <h3>验收标准</h3>
        <MarkdownContent :source="mission.acceptance_criteria" />
      </section>

      <section v-if="mission.result" class="section">
        <h3>成果</h3>
        <MarkdownContent :source="mission.result" />
      </section>

      <section class="section">
        <h3>子任务</h3>
        <el-empty v-if="!children.length" description="没有子任务" :image-size="60" />
        <div v-else class="children-list">
          <router-link
            v-for="child in children"
            :key="child.id"
            :to="{ name: 'mission-detail', params: { id: child.id } }"
          >
            {{ child.title }}
          </router-link>
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

    <el-dialog v-model="resultDialogVisible" title="提交成果" width="600px">
      <MarkdownEditor
        v-model="submitResult"
        :rows="6"
        placeholder="成果说明、测试结果或链接（支持 Markdown）"
      />
      <template #footer>
        <el-button @click="resultDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="submittingResult" @click="confirmSubmitResult">
          提交
        </el-button>
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
  border-top: 1px solid #e5e7eb;
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
</style>
