<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import MissionQueryForm from './MissionQueryForm.vue'
import { useAuthStore } from '../stores/auth'
import type { QueryParams } from '../api/client'
import { createSavedView, updateSavedView, deleteSavedView, listSavedViews, getSavedView, resolveSavedView, definitionFromQuery, viewLocation, filterLabels, type SavedView, type ViewTarget } from '../api/savedViews'
const props = defineProps<{ query: QueryParams; target: ViewTarget }>()
const emit = defineEmits<{ remove: [key: string]; opened: [] }>()
const route = useRoute(), router = useRouter(), auth = useAuthStore()
const rows = ref<SavedView[]>([]), active = ref<SavedView | null>(null)
const total = ref(0), page = ref(1), manage = ref(false), dialog = ref(false), busy = ref(false)
const editingRow = ref<SavedView | null>(null)
const draftQuery = ref<QueryParams | null>(null)
const saveTarget = ref<ViewTarget>(props.target)
const name = ref(''), visibility = ref<'Private' | 'Team'>('Private'), dateMode = ref('current'), updating = ref(false)
const current = computed(() => definitionFromQuery(props.query, props.target))
const applied = ref('')
const modified = computed(() => active.value && applied.value !== JSON.stringify(current.value))
const canWrite = (row: SavedView) => row.owner === auth.user?.id || row.visibility === 'Team' && !!auth.user?.is_staff
let generation = 0
watch(() => route.query.saved_view, async id => {
  const token = ++generation
  active.value = null
  if (typeof id !== 'string') return
  try { const row = await getSavedView(id); if (token === generation) { active.value = row; applied.value = JSON.stringify(current.value) } }
  catch (e) { ElMessage.error(e instanceof Error ? e.message : '筛选加载失败') }
}, { immediate: true })
async function load() {
  try { const data = await listSavedViews(page.value); rows.value = data.results; total.value = data.count }
  catch (e) { ElMessage.error(e instanceof Error ? e.message : '筛选加载失败') }
}
function prepare(update: boolean) {
  editingRow.value = null; draftQuery.value = null; saveTarget.value = props.target
  updating.value = update
  name.value = update ? active.value?.name ?? '' : ''
  visibility.value = update ? active.value?.visibility ?? 'Private' : 'Private'
  dateMode.value = update && active.value?.definition.date_window?.mode === 'relative' ? active.value.definition.date_window.preset : 'current'
  dialog.value = true
}
function edit(row: SavedView) {
  editingRow.value = row; updating.value = true; saveTarget.value = row.target
  name.value = row.name; visibility.value = row.visibility
  const def = row.definition
  draftQuery.value = { ...def.filters, ordering: def.ordering, zoom: def.zoom, ...(def.date_window?.mode === 'absolute' ? { date_from: def.date_window.date_from, date_to: def.date_window.date_to } : {}) }
  dateMode.value = def.date_window?.mode === 'relative' ? def.date_window.preset : 'current'
  dialog.value = true
}
async function save() {
  if (busy.value) return
  busy.value = true
  try {
    const definition = definitionFromQuery(draftQuery.value ?? props.query, saveTarget.value)
    const source = editingRow.value ?? active.value
    if (dateMode.value === 'none') definition.date_window = null
    if (dateMode.value === 'this_week' || dateMode.value === 'next_7_days') definition.date_window = { mode: 'relative', preset: dateMode.value }
    // 未修改的 me 筛选保留动态语义，团队成员打开时仍解释为各自本人。
    if (updating.value && source && !editingRow.value) for (const key of ['creator', 'assignee', 'reviewer']) {
      if (source.definition.filters[key] === 'me' && definition.filters[key] === auth.user?.id) definition.filters[key] = 'me'
    }
    const data = { name: name.value, visibility: visibility.value, target: saveTarget.value, definition }
    const row = updating.value && source ? await updateSavedView(source.id, data, source.version) : await createSavedView(data)
    if (!editingRow.value || active.value?.id === row.id) { active.value = row; applied.value = JSON.stringify(current.value) }
    if (!editingRow.value) await router.replace({ query: { ...route.query, saved_view: row.id } })
    dialog.value = false
    ElMessage.success('筛选已保存'); await load()
  } catch (e) { ElMessage.error(e instanceof Error ? e.message : '保存失败；输入已保留') }
  finally { busy.value = false }
}
async function open(row: SavedView) {
  try {
    const data = await resolveSavedView(row.id)
    await router.push(viewLocation(data.target, data.query, row.id))
    active.value = row; applied.value = JSON.stringify(definitionFromQuery(data.query, data.target)); manage.value = false
    emit('opened')
  } catch (e) { ElMessage.error(e instanceof Error ? e.message : '条件失效，请修复筛选') }
}
async function remove(row: SavedView) {
  try { await ElMessageBox.confirm(`删除筛选「${row.name}」？`, '删除筛选') } catch { return }
  try { await deleteSavedView(row.id, row.version); if (active.value?.id === row.id) active.value = null; await load() }
  catch (e) { ElMessage.error(e instanceof Error ? e.message : '删除失败') }
}
</script>
<template>
  <section>
    <div class="toolbar"><el-button @click="prepare(false)">{{ active ? '另存为' : '保存当前筛选' }}</el-button><el-button @click="manage = true; load()">打开 / 管理筛选</el-button>
      <template v-if="active"><span>{{ active.name }} · {{ active.visibility === 'Team' ? '团队' : '个人' }} {{ modified ? '（已修改，尚未保存）' : '' }}</span><el-button v-if="canWrite(active)" @click="prepare(true)">更新筛选</el-button></template>
    </div>
    <div class="toolbar" aria-label="当前生效筛选"><template v-for="(label, key) in filterLabels" :key="key"><el-tag v-if="query[key] !== undefined && query[key] !== '' && query[key] !== null" closable @close="emit('remove', String(key))">{{ label }}：{{ query[key] }}</el-tag></template></div>
    <el-dialog v-model="dialog" title="保存筛选" width="480px">
      <el-form label-width="100px"><el-form-item label="名称"><el-input v-model="name" maxlength="100" /></el-form-item>
      <el-form-item label="可见范围"><el-select v-model="visibility"><el-option label="仅自己" value="Private" /><el-option label="团队共享" value="Team" /></el-select></el-form-item>
      <el-form-item label="计划窗口"><el-select v-model="dateMode"><el-option label="当前计划窗口（含未排期）" value="current" /><el-option label="不限制（甘特使用默认窗口）" value="none" /><el-option label="本周（周一至周日，含未排期）" value="this_week" /><el-option label="未来 7 天（含今天及未排期）" value="next_7_days" /></el-select></el-form-item></el-form>
      <MissionQueryForm v-if="draftQuery" :query="draftQuery" @apply="draftQuery = $event" />
      <p>保存查询定义，不保存任务快照。手动调整不会自动覆盖保存筛选。</p>
      <template #footer><el-button :loading="busy" @click="save">确认保存</el-button></template>
    </el-dialog>
    <el-dialog v-model="manage" title="保存筛选" width="680px">
      <div v-for="row in rows" :key="row.id" class="toolbar"><span>{{ row.name }} · {{ row.owner_name }} · {{ row.visibility === 'Team' ? '团队' : '个人' }}</span><el-button @click="open(row)">打开</el-button><el-button class="app-link app-link--action" v-if="canWrite(row)" link @click="edit(row)">编辑 / 修复</el-button><el-button class="app-link app-link--action" v-if="canWrite(row)" type="danger" link @click="remove(row)">删除</el-button><p v-for="warning in row.warnings" :key="warning">{{ warning }}</p></div>
      <el-empty v-if="!rows.length" description="暂无保存筛选" /><el-pagination :total="total" :page-size="20" :current-page="page" layout="prev, pager, next" @current-change="page = $event; load()" />
    </el-dialog>
  </section>
</template>
