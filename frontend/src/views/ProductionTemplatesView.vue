<script setup lang="ts">
import DesignNavigation from '../components/DesignNavigation.vue'
import { onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { ApiException } from '../api/client'
import { createProductionTemplate, getProductionTemplate, listProductionTemplates, listTemplateEvents, updateProductionTemplate } from '../api/productionTemplates'
import type { TemplateInput } from '../api/productionTemplates'
import type { MissionEvent, ProductionTemplate } from '../api/types'
import ProductionStepsEditor from '../components/ProductionStepsEditor.vue'
import MarkdownContent from '../components/MarkdownContent.vue'
const templates = ref<ProductionTemplate[]>([])
const total = ref(0)
const page = ref(1)
const query = ref('')
const archived = ref('false')
const selected = ref<ProductionTemplate | null>(null)
const events = ref<MissionEvent[]>([])
const eventPage = ref(1)
const eventTotal = ref(0)
const dialog = ref(false)
const editingId = ref<string | null>(null)
const version = ref(1)
const saving = ref(false)
const loading = ref(false)
const form = reactive<TemplateInput>({ name: '', description: '', steps: [] })
let sequence = 0
let detailSequence = 0
function report(err: unknown) { ElMessage.error(err instanceof ApiException ? Object.values(err.fieldErrors).flat().join('；') || err.message : '操作失败') }
async function load() {
  const seq = ++sequence; loading.value = true
  try { const data = await listProductionTemplates({ q: query.value, archived: archived.value, page: page.value }); if (seq === sequence) { templates.value = data.results; total.value = data.count } }
  catch (err) { if (seq === sequence) report(err) } finally { if (seq === sequence) loading.value = false }
}
async function inspect(item: ProductionTemplate) {
  const seq = ++detailSequence
  selected.value = item
  try { const result = await listTemplateEvents(item.id, eventPage.value); if (seq === detailSequence) { events.value = result.results; eventTotal.value = result.count } } catch (err) { report(err) }
}
function edit(item?: ProductionTemplate) {
  editingId.value = item?.id ?? null; version.value = item?.version ?? 1
  Object.assign(form, item ? { name: item.name, description: item.description, steps: structuredClone(item.steps.map(s => ({ ...s, tags: [...s.tags], prerequisite_keys: [...s.prerequisite_keys] }))) } : { name: '', description: '', steps: [{ key: 'step_1', title: '', content: '', acceptance_criteria: '', type: 'Task', priority: 'P2', tags: [], prerequisite_keys: [] }] })
  dialog.value = true
}
async function refreshConflict(err: unknown) {
  report(err)
  if (err instanceof ApiException && err.status === 409 && editingId.value) {
    try { version.value = (await getProductionTemplate(editingId.value)).version } catch (error) { report(error) }
  }
}
async function save() {
  saving.value = true
  try {
    const input = { name: form.name, description: form.description, steps: form.steps }
    const item = editingId.value ? await updateProductionTemplate(editingId.value, { ...input, expected_version: version.value }) : await createProductionTemplate(input)
    dialog.value = false; await load(); eventPage.value = 1; await inspect(item); ElMessage.success('模板已保存，已生成的任务不受影响')
  } catch (err) { await refreshConflict(err) } finally { saving.value = false }
}
async function archive(item: ProductionTemplate) {
  saving.value = true
  try { const updated = await updateProductionTemplate(item.id, { archived: !item.archived, expected_version: item.version }); await load(); await inspect(updated) }
  catch (err) { report(err); await load(); try { await inspect(await getProductionTemplate(item.id)) } catch (error) { report(error) } }
  finally { saving.value = false }
}
function filter() { page.value = 1; void load() }
onMounted(load)
</script>
<template>
  <div class="page">
    <div class="page-header design-page-header"><h2>资产生产模板</h2><DesignNavigation active="production-templates" /><el-button type="primary" @click="edit()">新建模板</el-button></div>
    <el-card class="section-card" shadow="never">
    <div class="toolbar"><el-input v-model="query" placeholder="搜索模板" clearable @keyup.enter="filter" @clear="filter" /><el-select v-model="archived" @change="filter"><el-option label="未归档" value="false" /><el-option label="已归档" value="true" /><el-option label="全部" value="all" /></el-select><el-button @click="filter">查询</el-button></div>
    <el-table v-loading="loading" :data="templates" @row-click="(item: ProductionTemplate) => { eventPage = 1; inspect(item) }">
      <el-table-column label="模板"><template #default="{ row }"><el-button link type="primary" @click.stop="eventPage = 1; inspect(row)">{{ row.name }}</el-button></template></el-table-column>
      <el-table-column label="步骤数"><template #default="{ row }">{{ row.steps.length }}</template></el-table-column>
      <el-table-column prop="version" label="版本" />
      <el-table-column label="操作"><template #default="{ row }"><el-button v-if="row.allowed_actions.includes('edit')" link @click.stop="edit(row)">编辑</el-button><el-button v-if="row.allowed_actions.includes('archive') || row.allowed_actions.includes('restore')" link :loading="saving" @click.stop="archive(row)">{{ row.archived ? '恢复' : '归档' }}</el-button></template></el-table-column>
    </el-table>
    <el-pagination v-if="total > 20" v-model:current-page="page" :total="total" :page-size="20" layout="prev, pager, next" @current-change="load" />
    </el-card>
    <el-card v-if="selected" class="section-card" shadow="never"><h3>{{ selected.name }} · 版本 {{ selected.version }}</h3><p>{{ selected.description }}</p>
      <ol><li v-for="step in selected.steps" :key="step.key"><strong>{{ step.title }}</strong><p>前置步骤：{{ step.prerequisite_keys.map(key => selected!.steps.find(s => s.key === key)?.title ?? key).join('、') || '无，可并行' }}</p><MarkdownContent :source="step.content" /><p>验收标准</p><MarkdownContent :source="step.acceptance_criteria" /></li></ol>
      <h3>活动记录</h3><ul><li v-for="event in events" :key="event.id">{{ event.actor.display_name }} · {{ ({ created: '创建', updated: '修改', archived: '归档', restored: '恢复' } as Record<string, string>)[event.action] ?? event.action }} · {{ new Date(event.created_at).toLocaleString() }}</li></ul>
      <el-pagination v-if="eventTotal > 20" v-model:current-page="eventPage" :total="eventTotal" :page-size="20" layout="prev, pager, next" @current-change="inspect(selected)" />
    </el-card>
    <el-dialog v-model="dialog" :title="editingId ? '编辑生产模板' : '新建生产模板'" width="min(800px, 95vw)" :close-on-click-modal="!saving">
      <el-form label-position="top" @submit.prevent="save"><el-form-item label="名称"><el-input v-model="form.name" maxlength="200" /></el-form-item><el-form-item label="说明"><el-input v-model="form.description" type="textarea" /></el-form-item><ProductionStepsEditor v-model="form.steps" /><p>模板不保存认领者、里程碑或日期；所有步骤将生成待认领 Mission。</p><el-button type="primary" native-type="submit" :loading="saving">保存模板</el-button></el-form>
    </el-dialog>
  </div>
</template>
