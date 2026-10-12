<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import type { FormInstance, FormRules } from 'element-plus'

import { listTags } from '../api/missions'
import type { MissionWritePayload } from '../api/types'
import MarkdownEditor from './MarkdownEditor.vue'

const props = withDefaults(
  defineProps<{
    initial?: Partial<MissionWritePayload>
    submitLabel?: string
    loading?: boolean
  }>(),
  { submitLabel: '保存', loading: false },
)

const emit = defineEmits<{ (e: 'submit', payload: MissionWritePayload): void }>()

const formRef = ref<FormInstance>()
const form = reactive({
  title: props.initial?.title ?? '',
  content: props.initial?.content ?? '',
  acceptance_criteria: props.initial?.acceptance_criteria ?? '',
  tags: [...(props.initial?.tags ?? [])] as string[],
})
const tagOptions = ref<string[]>([])
const rules: FormRules = {
  title: [{ required: true, message: '请填写标题', trigger: 'blur' }],
}

onMounted(async () => {
  try {
    tagOptions.value = (await listTags()).map((tag) => tag.name)
  } catch {
    tagOptions.value = []
  }
})

async function onSubmit() {
  if (!formRef.value) return
  const valid = await formRef.value.validate().catch(() => false)
  if (!valid) return
  emit('submit', {
    title: form.title,
    content: form.content,
    acceptance_criteria: form.acceptance_criteria,
    tags: form.tags,
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
