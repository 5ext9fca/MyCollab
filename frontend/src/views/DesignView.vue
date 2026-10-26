<script setup lang="ts">
import DesignNavigation from '../components/DesignNavigation.vue'
import { computed, reactive, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import { ApiException } from '../api/client'
import { createDesignElement, getDesignElement, listDesignEvents, updateDesignElement } from '../api/designElements'
import { listMissions } from '../api/missions'
import type { DesignElement, DesignInput, Mission, MissionEvent } from '../api/types'
import DesignTreeBranch from '../components/DesignTreeBranch.vue'
import DesignElementSelect from '../components/DesignElementSelect.vue'
import AssetSelect from '../components/AssetSelect.vue'
import ElementMultiSelect from '../components/ElementMultiSelect.vue'
import MarkdownContent from '../components/MarkdownContent.vue'
import MarkdownEditor from '../components/MarkdownEditor.vue'
import MissionDetailDrawer from '../components/MissionDetailDrawer.vue'
import ProductionPanel from '../components/ProductionPanel.vue'
import StatusTag from '../components/StatusTag.vue'

const route = useRoute()
const id = computed(() => typeof route.params.id === 'string' ? route.params.id : '')
const element = ref<DesignElement | null>(null)
const missions = ref<Mission[]>([])
const events = ref<MissionEvent[]>([])
const hasBatch = ref(false)
const total = ref(0)
const eventTotal = ref(0)
const page = ref(1)
const eventPage = ref(1)
const loading = ref(false)
const error = ref('')
const treeRevision = ref(0)
const search = ref('')
const query = ref('')
const archived = ref('false')
const kind = ref('')
const selected = ref<string | null>(null)
const dialog = ref(false)
const editingId = ref<string | null>(null)
const saving = ref(false)
const form = reactive<DesignInput>({ title: '', content: '', kind: 'Design', parent: null, asset_ids: [], prerequisite_ids: [] })
const actionLabels: Record<string, string> = { created: '创建', updated: '修改', moved: '移动', archived: '归档', restored: '恢复', instantiated: '生成生产任务', dependencies_changed: '修改前置依赖' }
let seq = 0
async function load() {
  const current = ++seq
  if (!id.value) { element.value = null; return }
  loading.value = true; error.value = ''
  try {
    const [detail, tasks, activity] = await Promise.all([
      getDesignElement(id.value),
      listMissions({ design_element: id.value, production_batch: 'none', page: page.value }),
      listDesignEvents(id.value, eventPage.value),
    ])
    if (current !== seq) return
    element.value = detail; missions.value = tasks.results; total.value = tasks.count
    events.value = activity.results; eventTotal.value = activity.count
  } catch (err) { if (current === seq) error.value = err instanceof ApiException ? err.message : '加载失败' }
  finally { if (current === seq) loading.value = false }
}
watch(id, () => { page.value = 1; eventPage.value = 1; element.value = null; selected.value = null; hasBatch.value = false; void load() }, { immediate: true })
function openEditor(edit = false, child = false) {
  const source = edit ? element.value : null
  editingId.value = source?.id ?? null
  Object.assign(form, { title: source?.title ?? '', content: source?.content ?? '', kind: source?.kind ?? (child ? element.value?.kind : 'Design') ?? 'Design', parent: source?.parent?.id ?? (child ? id.value : null), asset_ids: source?.assets?.map(asset => asset.id) ?? [], prerequisite_ids: source?.prerequisites?.map(item => item.id) ?? [] })
  dialog.value = true
}
function report(err: unknown) {
  ElMessage.error(err instanceof ApiException ? Object.values(err.fieldErrors).flat().join('；') || err.message : '操作失败')
}
async function save() {
  if (!form.title.trim()) { ElMessage.warning('请填写标题'); return }
  saving.value = true
  try {
    if (editingId.value && element.value) {
      await updateDesignElement(editingId.value, { title: form.title, content: form.content, parent: form.parent, prerequisite_ids: form.prerequisite_ids, asset_ids: form.kind === 'Design' ? form.asset_ids : [], expected_version: element.value.version })
    } else await createDesignElement({ ...form })
    dialog.value = false; treeRevision.value++; await load(); ElMessage.success('已保存')
  } catch (err) { report(err); if (err instanceof ApiException && err.status === 409) await load() }
  finally { saving.value = false }
}
async function archive() {
  if (!element.value) return
  saving.value = true
  try {
    await updateDesignElement(element.value.id, { archived: !element.value.archived, expected_version: element.value.version })
    treeRevision.value++; await load()
  } catch (err) { report(err); if (err instanceof ApiException && err.status === 409) await load() }
  finally { saving.value = false }
}
async function changed() { await load(); treeRevision.value++ }
</script>
<template>
  <div class="page">
    <div class="page-header design-page-header"><h2>设计与资产</h2><DesignNavigation active="design" /><el-button type="primary" @click="openEditor()">新建条目</el-button></div>
    <div class="design-layout">
      <aside>
        <el-card class="section-card" shadow="never"><div class="design-filters">
        <el-input v-model="search" placeholder="搜索设计或资产的标题与正文" clearable @keyup.enter="query = search" @clear="query = ''" />
        <el-button @click="query = search">搜索</el-button>
        <el-select v-model="archived" aria-label="归档筛选"><el-option label="未归档" value="false" /><el-option label="全部" value="all" /><el-option label="已归档" value="true" /></el-select>
        <el-select v-model="kind" clearable placeholder="条目类型"><el-option label="设计" value="Design" /><el-option label="资产" value="Asset" /></el-select>
        </div></el-card>
        <section v-for="treeKind in (['Design', 'Asset'] as const)" v-show="!kind || kind === treeKind" :key="treeKind" :aria-label="treeKind === 'Design' ? '设计树' : '资产树'">
          <h3>{{ treeKind === 'Design' ? '设计树' : '资产树' }}</h3>
          <DesignTreeBranch :key="`${treeRevision}:${archived}:${query}:${treeKind}`" :archived="archived" :query="query" :kind="treeKind" />
        </section>
      </aside>
      <main v-loading="loading">
        <el-alert v-if="error" :title="error" type="error" :closable="false" /><el-button v-if="error" @click="load">重试</el-button>
        <el-empty v-if="!id" description="选择设计条目，查看设计依据与执行任务" />
        <template v-if="element">
          <el-card class="section-card" shadow="never">
          <template #header>
            <div class="design-summary">
              <nav v-if="element.ancestors.length" class="design-ancestors" aria-label="所属条目路径">
                <span class="meta">所属路径</span>
                <ol>
                  <li v-for="(ancestor, index) in element.ancestors" :key="ancestor.id">
                    <span v-if="index" class="meta" aria-hidden="true">/</span>
                    <router-link class="app-link app-link--title" :to="{ name: 'design', params: { id: ancestor.id } }">{{ ancestor.title }}</router-link>
                  </li>
                </ol>
              </nav>
              <div class="card-heading">
                <h2>{{ element.title }}</h2>
                <div class="design-badges"><el-tag>{{ element.kind === 'Asset' ? '资产' : '设计' }}</el-tag><el-tag v-if="element.archived" type="info">已归档</el-tag></div>
              </div>
              <p class="meta">创建者：{{ element.created_by.display_name }} · 更新于 {{ new Date(element.updated_at).toLocaleString() }} · 版本 {{ element.version }}</p>
              <div class="toolbar toolbar--flush design-actions" role="group" aria-label="设计条目操作">
                <router-link v-if="!element.archived" v-slot="{ href, navigate }" custom :to="{ name: 'mission-create', query: element.kind === 'Asset' ? { asset: element.id } : { design_element: element.id } }">
                  <el-button tag="a" type="primary" :href="href" @click="navigate">发布 Mission</el-button>
                </router-link>
                <router-link v-slot="{ href, navigate }" custom :to="{ name: 'workspace', query: { view: 'graph', design_element: element.id } }">
                  <el-button tag="a" :href="href" @click="navigate">查看任务依赖</el-button>
                </router-link>
                <el-button v-if="!element.archived" @click="openEditor(false, true)">新建子条目</el-button>
                <el-button v-if="element.allowed_actions.includes('edit')" @click="openEditor(true)">编辑</el-button>
                <el-button v-if="element.allowed_actions.includes('archive') || element.allowed_actions.includes('restore')" :loading="saving" @click="archive">{{ element.archived ? '恢复' : '归档' }}</el-button>
              </div>
            </div>
          </template>
          <MarkdownContent :source="element.content" />
          <h3>{{ element.kind === 'Design' ? '引用资产' : '引用此资产的设计' }}</h3>
          <div class="design-references">
            <router-link v-for="reference in (element.kind === 'Design' ? element.assets : element.referencing_designs)" :key="reference.id" class="app-link app-link--title" :to="{ name: 'design', params: { id: reference.id } }">{{ reference.title }}{{ reference.archived ? '（已归档）' : '' }}</router-link>
          </div>
          <p v-if="!(element.kind === 'Design' ? element.assets : element.referencing_designs)?.length" class="meta">暂无引用</p>
          <h3>直属任务进度</h3>
          <p>{{ element.progress.progress === null ? '暂无有效任务' : `${element.progress.done}/${element.progress.effective_total} 已完成（${Math.round(element.progress.progress * 100)}%）` }} · 受阻 {{ element.progress.blocked }} · 需复核 {{ element.progress.revalidation }}</p>
          <p class="meta">按直接关联的有效 Mission 数量统计，不表示工时或资产验收状态。</p>
          </el-card>
          <el-card class="section-card" shadow="never">
            <h3>{{ element.kind === 'Design' ? '设计依赖' : '资产依赖' }}</h3>
            <p class="meta">前置依赖表示当前条目的先后约束，与父子组成关系独立；不会自动改变任务依赖或状态。通过编辑条目维护。</p>
            <h4>前置依赖</h4>
            <div class="design-references"><router-link v-for="item in element.prerequisites" :key="item.id" class="app-link app-link--title" :to="{ name: 'design', params: { id: item.id } }">{{ item.title }}{{ item.archived ? '（已归档）' : '' }}</router-link></div>
            <p v-if="!element.prerequisites?.length" class="meta">无前置依赖</p>
            <h4>依赖此条目</h4>
            <div class="design-references"><router-link v-for="item in element.dependents" :key="item.id" class="app-link app-link--title" :to="{ name: 'design', params: { id: item.id } }">{{ item.title }}{{ item.archived ? '（已归档）' : '' }}</router-link></div>
            <p v-if="!element.dependents?.length" class="meta">暂无条目依赖它</p>
          </el-card>
          <ProductionPanel v-if="element.kind === 'Asset'" :asset="element" @open="selected = $event" @changed="changed" @batch-loaded="hasBatch = $event" />
          <el-card class="section-card" shadow="never">
          <h3>{{ hasBatch ? '其他关联任务' : '关联任务' }}</h3>
          <ul class="task-list"><li v-for="mission in missions" :key="mission.id"><button type="button" class="app-link app-link--title" @click="selected = mission.id">{{ mission.title }}</button> <StatusTag :status="mission.status" /><span v-if="mission.is_blocked"> · 受阻</span></li></ul>
          <el-empty v-if="!missions.length" description="暂无关联任务" />
          <el-pagination v-if="total > 20" v-model:current-page="page" :page-size="20" :total="total" layout="prev, pager, next" @current-change="load" />
          </el-card>
          <el-card class="section-card" shadow="never">
          <h3>活动记录</h3>
          <ul><li v-for="event in events" :key="event.id">{{ event.actor.display_name }} · {{ actionLabels[event.action] ?? event.action }} · {{ new Date(event.created_at).toLocaleString() }}</li></ul>
          <el-pagination v-if="eventTotal > 20" v-model:current-page="eventPage" :page-size="20" :total="eventTotal" layout="prev, pager, next" @current-change="load" />
          </el-card>
        </template>
      </main>
    </div>
    <el-dialog v-model="dialog" :title="editingId ? '编辑设计条目' : '新建设计条目'" width="min(680px, 95vw)" :close-on-click-modal="!saving">
      <el-form label-position="top" @submit.prevent="save">
        <el-form-item label="标题"><el-input v-model="form.title" maxlength="200" /></el-form-item>
        <el-form-item label="类型"><el-select v-model="form.kind" :disabled="!!editingId" @change="form.parent = null; form.asset_ids = []; form.prerequisite_ids = []"><el-option label="设计说明" value="Design" /><el-option label="资产" value="Asset" /></el-select></el-form-item>
        <el-form-item :label="form.kind === 'Asset' ? '上级资产' : '上级设计'"><DesignElementSelect v-model="form.parent" :kind="form.kind" /></el-form-item>
        <el-form-item label="前置依赖"><ElementMultiSelect v-model="form.prerequisite_ids" :kind="form.kind" :exclude-id="editingId ?? undefined" label="前置依赖" /></el-form-item>
        <el-form-item v-if="form.kind === 'Design'" label="引用资产"><AssetSelect v-model="form.asset_ids" /></el-form-item>
        <el-form-item label="设计内容"><MarkdownEditor v-model="form.content" /></el-form-item>
        <el-button native-type="submit" type="primary" :loading="saving">保存</el-button>
      </el-form>
    </el-dialog>
    <MissionDetailDrawer :mission-id="selected" :open="!!selected" @close="selected = null" @focus="selected = $event" @changed="changed" />
  </div>
</template>
<style scoped>
.design-references { display: flex; flex-wrap: wrap; gap: 12px; }
.design-layout { display: grid; grid-template-columns: minmax(220px, 28%) minmax(0, 1fr); gap: 16px; }
aside, main { min-width: 0; }
main h2, main nav { overflow-wrap: anywhere; }
.design-filters { display: flex; flex-direction: column; gap: 12px; }
.task-list { list-style: none; padding: 0; }
.task-list li { display: flex; align-items: center; flex-wrap: wrap; gap: 8px; padding: 8px 0; }
.design-summary { display: flex; flex-direction: column; gap: 12px; }
.design-summary h2, .design-summary p { margin: 0; }
.design-summary h2 { min-width: 0; }
.design-ancestors, .design-ancestors ol, .design-ancestors li, .design-badges { display: flex; align-items: center; flex-wrap: wrap; gap: 8px; min-width: 0; }
.design-ancestors ol { list-style: none; margin: 0; padding: 0; }
.design-actions .el-button + .el-button { margin-left: 0; }
.design-actions a { text-decoration: none; }
@media (max-width: 720px) { .design-layout { grid-template-columns: 1fr; } aside { border-right: 0; } }
</style>
