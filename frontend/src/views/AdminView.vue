<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'

import {
  approveRegistration,
  listMembers,
  listRegistrations,
  rejectRegistration,
} from '../api/admin'
import { ApiException } from '../api/client'
import type { Member, RegistrationRequest, RegistrationStatus } from '../api/types'

const pageSize = 10

const activeTab = ref('registrations')

// -- Registration review --------------------------------------------------- //
const registrations = ref<RegistrationRequest[]>([])
const regTotal = ref(0)
const regPage = ref(1)
const regStatus = ref<RegistrationStatus | ''>('Pending')
const regLoading = ref(false)

const statusOptions: { label: string; value: RegistrationStatus | '' }[] = [
  { label: '待审批', value: 'Pending' },
  { label: '已通过', value: 'Approved' },
  { label: '已拒绝', value: 'Rejected' },
  { label: '全部', value: '' },
]
const statusType: Record<RegistrationStatus, 'warning' | 'success' | 'danger'> = {
  Pending: 'warning',
  Approved: 'success',
  Rejected: 'danger',
}
const statusLabel: Record<RegistrationStatus, string> = {
  Pending: '待审批',
  Approved: '已通过',
  Rejected: '已拒绝',
}

// -- Members --------------------------------------------------------------- //
const members = ref<Member[]>([])
const memberTotal = ref(0)
const memberPage = ref(1)
const memberSearch = ref('')
const memberLoading = ref(false)

function messageOf(error: unknown, fallback: string): string {
  return error instanceof ApiException ? error.message : fallback
}

function formatDate(value: string): string {
  return value ? new Date(value).toLocaleString() : '—'
}

async function loadRegistrations() {
  regLoading.value = true
  try {
    const data = await listRegistrations({
      status: regStatus.value || undefined,
      page: regPage.value,
      page_size: pageSize,
    })
    registrations.value = data.results
    regTotal.value = data.count
  } catch (error) {
    ElMessage.error(messageOf(error, '加载注册申请失败'))
  } finally {
    regLoading.value = false
  }
}

async function onApprove(row: RegistrationRequest) {
  try {
    await approveRegistration(row.id)
    ElMessage.success(`已通过 ${row.username} 的注册申请`)
    await loadRegistrations()
  } catch (error) {
    ElMessage.error(messageOf(error, '操作失败'))
  }
}

async function onReject(row: RegistrationRequest) {
  let note = ''
  try {
    const result = (await ElMessageBox.prompt('请填写拒绝原因（可选）', '拒绝注册申请', {
      confirmButtonText: '确认拒绝',
      cancelButtonText: '取消',
      inputPlaceholder: '例如：资料不完整',
    })) as { value?: string }
    note = result.value ?? ''
  } catch {
    return
  }
  try {
    await rejectRegistration(row.id, note)
    ElMessage.success(`已拒绝 ${row.username} 的注册申请`)
    await loadRegistrations()
  } catch (error) {
    ElMessage.error(messageOf(error, '操作失败'))
  }
}

async function loadMembers() {
  memberLoading.value = true
  try {
    const data = await listMembers({
      search: memberSearch.value || undefined,
      page: memberPage.value,
      page_size: pageSize,
    })
    members.value = data.results
    memberTotal.value = data.count
  } catch (error) {
    ElMessage.error(messageOf(error, '加载成员失败'))
  } finally {
    memberLoading.value = false
  }
}

function onRegFilter() {
  regPage.value = 1
  loadRegistrations()
}

function onRegPage(page: number) {
  regPage.value = page
  loadRegistrations()
}

function onMemberFilter() {
  memberPage.value = 1
  loadMembers()
}

function onMemberPage(page: number) {
  memberPage.value = page
  loadMembers()
}

onMounted(async () => {
  await Promise.all([loadRegistrations(), loadMembers()])
})
</script>

<template>
  <div class="page">
    <div class="page-header">
      <h2>管理后台</h2>
      <span class="meta">审批注册申请、查看团队成员（与 Django Admin 相互独立）</span>
    </div>

    <el-tabs v-model="activeTab">
      <el-tab-pane label="注册审批" name="registrations">
        <div class="toolbar">
          <el-select v-model="regStatus" style="width: 140px" @change="onRegFilter">
            <el-option
              v-for="item in statusOptions"
              :key="item.label"
              :label="item.label"
              :value="item.value"
            />
          </el-select>
          <el-button @click="onRegFilter">刷新</el-button>
        </div>

        <el-table v-loading="regLoading" :data="registrations" style="width: 100%">
          <el-table-column prop="username" label="用户名" min-width="120" />
          <el-table-column prop="display_name" label="姓名" min-width="100" />
          <el-table-column prop="email" label="邮箱" min-width="160" />
          <el-table-column prop="message" label="申请说明" min-width="160" show-overflow-tooltip />
          <el-table-column label="状态" width="100">
            <template #default="{ row }">
              <el-tag :type="statusType[row.status as RegistrationStatus]">
                {{ statusLabel[row.status as RegistrationStatus] }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="申请时间" width="180">
            <template #default="{ row }">{{ formatDate(row.created_at) }}</template>
          </el-table-column>
          <el-table-column label="操作" width="150" fixed="right">
            <template #default="{ row }">
              <template v-if="row.status === 'Pending'">
                <el-button class="app-link app-link--action" link type="primary" @click="onApprove(row)">通过</el-button>
                <el-button class="app-link app-link--action" link type="danger" @click="onReject(row)">拒绝</el-button>
              </template>
              <span v-else class="meta">{{ row.review_note || '—' }}</span>
            </template>
          </el-table-column>
          <template #empty>
            <el-empty description="暂无注册申请" />
          </template>
        </el-table>

        <el-pagination
          v-if="regTotal > pageSize"
          background
          layout="prev, pager, next"
          :total="regTotal"
          :page-size="pageSize"
          :current-page="regPage"
          @current-change="onRegPage"
        />
      </el-tab-pane>

      <el-tab-pane label="成员" name="members">
        <div class="toolbar">
          <el-input
            v-model="memberSearch"
            placeholder="搜索用户名 / 姓名 / 邮箱"
            style="width: 260px"
            clearable
            @keyup.enter="onMemberFilter"
            @clear="onMemberFilter"
          />
          <el-button @click="onMemberFilter">查询</el-button>
        </div>

        <el-table v-loading="memberLoading" :data="members" style="width: 100%">
          <el-table-column prop="username" label="用户名" min-width="120" />
          <el-table-column prop="display_name" label="姓名" min-width="100" />
          <el-table-column prop="email" label="邮箱" min-width="160" />
          <el-table-column label="状态" width="90">
            <template #default="{ row }">
              <el-tag :type="row.is_active ? 'success' : 'info'">
                {{ row.is_active ? '启用' : '停用' }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="角色" width="100">
            <template #default="{ row }">
              <el-tag :type="row.is_staff ? 'warning' : 'info'">
                {{ row.is_staff ? '管理员' : '成员' }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="加入时间" width="180">
            <template #default="{ row }">{{ formatDate(row.date_joined) }}</template>
          </el-table-column>
          <template #empty>
            <el-empty description="暂无成员" />
          </template>
        </el-table>

        <el-pagination
          v-if="memberTotal > pageSize"
          background
          layout="prev, pager, next"
          :total="memberTotal"
          :page-size="pageSize"
          :current-page="memberPage"
          @current-change="onMemberPage"
        />
      </el-tab-pane>
    </el-tabs>
  </div>
</template>
