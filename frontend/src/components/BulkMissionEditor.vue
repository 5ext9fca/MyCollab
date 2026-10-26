<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { bulkUpdateMissions, getMission, type BulkChanges, type BulkResult } from '../api/missions'
import { ApiException } from '../api/client'
import { notifyChanged } from '../api/notifications'
import type { Mission } from '../api/types'
const props = defineProps<{ missions: Mission[]; selectedIds: string[]; resetKey: string }>()
const emit = defineEmits<{ 'update:selectedIds': [ids: string[]]; changed: []; 'update:busy': [value: boolean] }>()
const selected = computed(() => props.missions.filter(m => props.selectedIds.includes(m.id)))
const dialog = ref(false), busy = ref(false), preview = ref(false), uncertain = ref(false), refreshing = ref(false)
const rows = ref<Mission[]>([]), results = ref<BulkResult[]>([])
watch(busy, value => emit('update:busy', value), { flush: 'sync' })
const fields = ['priority', 'milestone', 'planned_start_date', 'planned_end_date'] as const
const labels = { priority: '优先级', milestone: '里程碑', planned_start_date: '计划开始', planned_end_date: '计划结束' }
const modes = reactive<Record<string, 'keep' | 'set' | 'clear'>>({ priority: 'keep', milestone: 'keep', planned_start_date: 'keep', planned_end_date: 'keep' })
const values = reactive<Record<string, string>>({ priority: 'P2', milestone: '', planned_start_date: '', planned_end_date: '' })
const changes = computed<BulkChanges>(() => {
  const result: BulkChanges = {}
  for (const key of fields) if (modes[key] !== 'keep') Object.assign(result, { [key]: modes[key] === 'clear' ? null : values[key] })
  return result
})
watch(() => props.resetKey, () => { emit('update:selectedIds', []); if (!busy.value) { dialog.value = false; rows.value = []; results.value = [] } })
function open() { rows.value = selected.value.map(m => ({ ...m })); results.value = []; preview.value = false; uncertain.value = false; dialog.value = true }
function prepare() {
  if (!rows.value.length || rows.value.length > 50 || !Object.keys(changes.value).length) { ElMessage.warning('请选择 1–50 个任务及至少一个修改字段'); return }
  if (fields.some(key => modes[key] === 'set' && !values[key])) { ElMessage.warning('设值字段不可为空，请填写或选择清空'); return }
  preview.value = true
}
async function refreshRows() {
  refreshing.value = true
  try {
    // 刷新全部涉及任务后由用户重新预览确认，绝不自动换版本重发。
    rows.value = await Promise.all(rows.value.map(m => getMission(m.id)))
    uncertain.value = false; preview.value = false
    ElMessage.info('已读取最新数据和版本，请检查后重新预览确认')
  } catch (e) { ElMessage.error(e instanceof Error ? e.message : '刷新失败，不能重试'); uncertain.value = true }
  finally { refreshing.value = false }
}
async function submit() {
  if (busy.value || uncertain.value || !preview.value) return
  busy.value = true
  const resetKey = props.resetKey
  try {
    const data = await bulkUpdateMissions(rows.value.map(m => ({ id: m.id, expected_version: m.version })), changes.value)
    results.value = data.results
    const failed = data.results.filter(r => !r.success).map(r => r.id)
    rows.value = rows.value.filter(m => failed.includes(m.id))
    if (props.resetKey === resetKey) emit('update:selectedIds', failed)
    else { emit('update:selectedIds', []); rows.value = [] }
    uncertain.value = failed.length > 0
    preview.value = false; emit('changed'); notifyChanged()
  } catch (e) {
    uncertain.value = !(e instanceof ApiException && e.status < 500); preview.value = false
    ElMessage.error(`${e instanceof Error ? e.message : '请求中断'}${uncertain.value ? '。结果可能不确定，部分任务可能已成功；请重新读取任务后再决定。' : '。请求未执行，请修正输入。'}`)
    emit('changed')
  } finally { busy.value = false }
}
</script>
<template>
  <el-button :disabled="!selected.length || busy" @click="open">批量编辑计划</el-button>
  <el-dialog v-model="dialog" title="批量编辑计划" width="700px" :close-on-click-modal="!busy" :close-on-press-escape="!busy" :show-close="!busy">
    <p>逐项执行，可能部分成功。仅发起者或管理员可编辑未冻结任务；延后前置受日期约束时，请先调整下游。</p>
    <el-form v-if="!preview" label-width="100px">
      <el-form-item v-for="key in fields" :key="key" :label="labels[key]">
        <el-select v-model="modes[key]" :disabled="busy" style="width: 110px"><el-option label="保持" value="keep" /><el-option label="设值" value="set" /><el-option v-if="key !== 'priority'" label="清空" value="clear" /></el-select>
        <template v-if="modes[key] === 'set'"><el-select v-if="key === 'priority'" v-model="values[key]" style="width: 120px"><el-option v-for="p in ['P0', 'P1', 'P2', 'P3']" :key="p" :label="p" :value="p" /></el-select><el-date-picker v-else-if="key.startsWith('planned_')" v-model="values[key]" value-format="YYYY-MM-DD" /><el-input v-else v-model="values[key]" placeholder="里程碑 UUID" style="width: 320px" /></template>
      </el-form-item>
    </el-form>
    <template v-else><h3>修改预览（尚未写入）</h3><p v-for="key in fields" :key="key">{{ labels[key] }}：{{ modes[key] === 'keep' ? '保持原值' : modes[key] === 'clear' ? '清空' : values[key] }}</p></template>
    <p>待处理 {{ rows.length }} 个任务；预览不保证最终校验通过。</p>
    <ul><li v-for="mission in rows" :key="mission.id">{{ mission.title }} · {{ mission.status }} · {{ mission.priority }} · {{ mission.milestone?.name || '无里程碑' }} · {{ mission.planned_start_date || '未设开始' }} — {{ mission.planned_end_date || '未设结束' }} · 版本 {{ mission.version }}</li></ul>
    <el-alert v-if="uncertain" title="失败或结果不确定：先读取最新任务，再重新预览确认。不会自动重发。" type="warning" :closable="false" />
    <div v-for="result in results" :key="result.id" class="toolbar"><router-link class="app-link app-link--action" :to="`/missions/${result.id}`">{{ result.id }}</router-link><span>{{ result.success ? '成功' : result.error?.message }} {{ result.error?.code }}</span></div>
    <template #footer><el-button v-if="uncertain" :loading="refreshing" @click="refreshRows">读取最新任务</el-button><el-button v-if="preview" :disabled="busy" @click="preview = false">返回修改</el-button><el-button v-if="!preview" :disabled="uncertain || !rows.length || refreshing || busy" @click="prepare">预览变更</el-button><el-button v-else type="primary" :loading="busy" @click="submit">确认逐项执行</el-button></template>
  </el-dialog>
</template>
