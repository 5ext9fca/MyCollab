import { buildQuery, request } from './client'
import type { QueryParams } from './client'
import type { DesignElement, DesignInput, MissionEvent, Paginated } from './types'

export const listDesignElements = (params: QueryParams = {}) =>
  request<Paginated<DesignElement>>('GET', `/api/design-elements/${buildQuery(params)}`)
export const getDesignElement = (id: string) => request<DesignElement>('GET', `/api/design-elements/${id}/`)
export const createDesignElement = (data: DesignInput) => request<DesignElement>('POST', '/api/design-elements/', data)
export const updateDesignElement = (id: string, data: Partial<Omit<DesignInput, 'kind'>> & { expected_version: number; archived?: boolean }) =>
  request<DesignElement>('PATCH', `/api/design-elements/${id}/`, data)
export const listDesignEvents = (id: string, page = 1) =>
  request<Paginated<MissionEvent>>('GET', `/api/design-elements/${id}/events/${buildQuery({ page })}`)
