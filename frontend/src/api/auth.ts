import { request } from './client'
import type { CurrentUser, RegistrationRequest, User } from './types'

export interface RegisterPayload {
  username: string
  password: string
  email?: string
  display_name?: string
  message?: string
}

export const login = (username: string, password: string): Promise<CurrentUser> =>
  request<CurrentUser>('POST', '/api/auth/login/', { username, password })

export const register = (payload: RegisterPayload): Promise<RegistrationRequest> =>
  request<RegistrationRequest>('POST', '/api/auth/register/', payload)

export const logout = (): Promise<void> => request<void>('POST', '/api/auth/logout/')

export const me = (): Promise<CurrentUser> => request<CurrentUser>('GET', '/api/auth/me/')

/** Active team members, used to pick a reviewer or transfer acceptance. */
export const listTeamMembers = (): Promise<User[]> => request<User[]>('GET', '/api/members/')
