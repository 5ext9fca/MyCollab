<script setup lang="ts" generic="T extends { id: string }">
withDefaults(defineProps<{ items: T[]; total: number; loading: boolean; page: number; pageSize: number; pageSizes?: number[]; emptyText?: string }>(), { pageSizes: () => [10, 20, 50], emptyText: '暂无记录' })
const emit = defineEmits<{ 'update:page': [value: number]; 'update:pageSize': [value: number] }>()
</script>
<template>
  <div class="card-list">
    <el-card v-if="$slots.filters" class="section-card" shadow="never"><slot name="filters" /></el-card>
    <slot name="before-items" />
    <div v-loading="loading" :aria-busy="loading">
      <el-empty v-if="!loading && !items.length" :description="emptyText" />
      <slot name="items"><template v-for="item in items" :key="item.id"><slot name="item" :item="item" /></template></slot>
    </div>
    <el-pagination class="list-pagination" :total="total" :current-page="page" :page-size="pageSize" :page-sizes="pageSizes" layout="total, sizes, prev, pager, next" @current-change="emit('update:page', $event)" @size-change="emit('update:pageSize', $event); emit('update:page', 1)" />
  </div>
</template>
