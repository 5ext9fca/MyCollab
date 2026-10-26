<script setup lang="ts">
import type { CodeReport } from '../api/codeExecutions'
import MarkdownContent from './MarkdownContent.vue'
defineProps<{ report: CodeReport; patchUrl?: string | null }>()
const labels = { passed: '通过', failed: '失败', timeout: '超时', not_run: '未运行' }
</script>
<template>
  <el-card shadow="never" class="code-report">
    <h4>本地代码验证报告</h4>
    <p>这是用户本地 Runner 提供的证据，服务器没有运行测试。请审查补丁及验证覆盖范围后再提交或验收。</p>
    <p>基线：<code>{{ report.base_commit }}</code></p>
    <MarkdownContent :source="report.summary" />
    <a v-if="patchUrl" class="app-link" :href="patchUrl" target="_blank" rel="noopener">下载补丁（文本文件）</a>
    <p v-if="!report.verification.length">未配置验证；不能视为测试通过。</p>
    <el-table v-else :data="report.verification"><el-table-column prop="label" label="验证项" /><el-table-column label="结果"><template #default="{ row }"><el-tag :type="row.status === 'passed' ? 'success' : 'danger'">{{ labels[row.status as keyof typeof labels] }}</el-tag></template></el-table-column><el-table-column prop="exit_code" label="退出码" /><el-table-column label="时长"><template #default="{ row }">{{ (row.duration_ms / 1000).toFixed(1) }} 秒</template></el-table-column></el-table>
    <details><summary>变更文件（{{ report.changed_files.length }}）</summary><ul><li v-for="file in report.changed_files" :key="file.path"><code>{{ file.path }}</code> · {{ { added: '新增', modified: '修改', deleted: '删除' }[file.change] }}</li></ul></details>
  </el-card>
</template>
<style scoped>
.code-report { margin-top: 12px; }
code { overflow-wrap: anywhere; }
summary { cursor: pointer; padding: 12px 0; }
</style>
