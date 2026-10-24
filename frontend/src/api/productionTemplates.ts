import { buildQuery, request } from './client'
import type { QueryParams } from './client'
import type { MissionEvent, Paginated, ProductionData, ProductionTemplate } from './types'
export type TemplateInput = Pick<ProductionTemplate, 'name' | 'description' | 'steps'>
export const listProductionTemplates = (params: QueryParams = {}) => request<Paginated<ProductionTemplate>>('GET', `/api/production-templates/${buildQuery(params)}`)
export const getProductionTemplate = (id: string) => request<ProductionTemplate>('GET', `/api/production-templates/${id}/`)
export const createProductionTemplate = (data: TemplateInput) => request<ProductionTemplate>('POST', '/api/production-templates/', data)
export const updateProductionTemplate = (id: string, data: Partial<TemplateInput> & { expected_version: number; archived?: boolean }) => request<ProductionTemplate>('PATCH', `/api/production-templates/${id}/`, data)
export const listTemplateEvents = (id: string, page = 1) => request<Paginated<MissionEvent>>('GET', `/api/production-templates/${id}/events/${buildQuery({ page })}`)
export const getProduction = (assetId: string) => request<ProductionData>('GET', `/api/design-elements/${assetId}/production/`)
export const instantiateProduction = (assetId: string, data: { template_id: string; template_version: number; expected_version: number; milestone_id: string | null }) =>
  request<{ batch_id: string; asset_version: number; template_version: number; items: { step_key: string; mission_id: string }[] }>('POST', `/api/design-elements/${assetId}/instantiate/`, data)
