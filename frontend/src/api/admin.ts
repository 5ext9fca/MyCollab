/** Admin-console API (`/api/admin/`), distinct from Django Admin. */
import { buildQuery, request } from './client'
import type { QueryParams } from './client'
import type { Member, Paginated, RegistrationRequest } from './types'

export const listRegistrations = (
  params: QueryParams = {},
): Promise<Paginated<RegistrationRequest>> =>
  request<Paginated<RegistrationRequest>>('GET', `/api/admin/registrations/${buildQuery(params)}`)

export const approveRegistration = (id: string): Promise<RegistrationRequest> =>
  request<RegistrationRequest>('POST', `/api/admin/registrations/${id}/approve/`, {})

export const rejectRegistration = (id: string, note = ''): Promise<RegistrationRequest> =>
  request<RegistrationRequest>('POST', `/api/admin/registrations/${id}/reject/`, { note })

export const listMembers = (params: QueryParams = {}): Promise<Paginated<Member>> =>
  request<Paginated<Member>>('GET', `/api/admin/users/${buildQuery(params)}`)
