import { buildQuery, request, type QueryParams } from './client'
import type { Paginated } from './types'
export type ViewTarget = 'List' | 'Overview' | 'Gantt'
export interface ViewDefinition { filters: Record<string, string | number | boolean | string[]>; ordering: string | null; date_window: null | { mode: 'absolute'; date_from: string; date_to: string } | { mode: 'relative'; preset: 'this_week' | 'next_7_days' }; zoom: 'day' | 'week' | null }
export interface SavedView { id: string; name: string; owner: number; owner_name: string; visibility: 'Private' | 'Team'; target: ViewTarget; definition: ViewDefinition; version: number; warnings: string[] }
export type ViewInput = Pick<SavedView, 'name' | 'visibility' | 'target' | 'definition'>
export const listSavedViews = (page = 1) => request<Paginated<SavedView>>('GET', `/api/saved-views/${buildQuery({ page })}`)
export const getSavedView = (id: string) => request<SavedView>('GET', `/api/saved-views/${id}/`)
export const createSavedView = (data: ViewInput) => request<SavedView>('POST', '/api/saved-views/', data)
export const updateSavedView = (id: string, data: ViewInput, expected_version: number) => request<SavedView>('PATCH', `/api/saved-views/${id}/`, { ...data, expected_version })
export const deleteSavedView = (id: string, expected_version: number) => request<void>('DELETE', `/api/saved-views/${id}/${buildQuery({ expected_version })}`)
export const resolveSavedView = (id: string) => request<{ target: ViewTarget; query: QueryParams; today: string; warnings: string[] }>('GET', `/api/saved-views/${id}/resolve/`)
export const filterLabels: Record<string, string> = { q: '关键词', status: '状态', type: '类型', priority: '优先级', tag: '标签（同时包含）', creator: '发起者', assignee: '认领者', reviewer: '验收者', parent: '父任务', milestone: '里程碑', design_element: '设计条目', production_batch: '生产批次', blocked: '受阻', revalidation: '需复核', ordering: '排序', date_from: '计划窗口起始（含未排期）', date_to: '计划窗口结束（含未排期）' }
export function definitionFromQuery(query: QueryParams, target: ViewTarget): ViewDefinition {
  const filters: ViewDefinition['filters'] = {}
  for (const key of Object.keys(filterLabels).filter(key => !['ordering', 'date_from', 'date_to'].includes(key))) {
    const value = query[key]
    if (value === undefined || value === null || value === '' || (key === 'status' && value === 'all')) continue
    if (key === 'tag') filters[key] = [...new Set((Array.isArray(value) ? value : String(value).split(',')).map(String).filter(Boolean))]
    else if (key === 'blocked' || key === 'revalidation') filters[key] = value === true || value === 'true' ? true : value === false || value === 'false' ? false : String(value)
    else if (['creator', 'assignee', 'reviewer'].includes(key) && /^\d+$/.test(String(value))) filters[key] = Number(value)
    else filters[key] = String(value)
  }
  return { filters, ordering: query.ordering ? String(query.ordering) : null, date_window: query.date_from || query.date_to ? { mode: 'absolute', date_from: String(query.date_from ?? ''), date_to: String(query.date_to ?? '') } : null, zoom: target === 'Gantt' ? query.zoom === 'week' ? 'week' : 'day' : null }
}
export function viewLocation(target: ViewTarget, query: QueryParams, id: string) {
  const normalized: Record<string, string | string[]> = {}
  for (const [key, value] of Object.entries(query)) if (value !== undefined && value !== null) normalized[key] = Array.isArray(value) ? value.map(String) : String(value)
  if (target === 'List' && !normalized.status) normalized.status = 'all'
  return { path: target === 'List' ? '/missions' : '/workspace', query: { ...normalized, ...(target === 'List' ? {} : { view: target === 'Gantt' ? 'graph' : 'overview' }), saved_view: id } }
}
