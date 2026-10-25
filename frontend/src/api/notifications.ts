import { buildQuery, request, type QueryParams } from './client'
import type { Mission, Paginated } from './types'

export type WorkCategory = 'review' | 'returned' | 'due_soon' | 'overdue' | 'unblocked' | 'revalidation'
export interface WorkSummary { today: string; counts: Record<WorkCategory, number>; unread_notification_count: number }
export interface Notification { id: string; mission: string; mission_title: string; mission_status: string; payload: { summary: string }; read_at: string | null; created_at: string }
export interface Subscription { subscription: { id: string; mode: 'Follow' | 'Mute'; version: number } | null; effective_following: boolean; mandatory_reminders: boolean }
export const workSummary = () => request<WorkSummary>('GET', '/api/my-work/summary/')
export const workMissions = (category: WorkCategory, page: number) => request<Paginated<Mission>>('GET', `/api/my-work/missions/${buildQuery({ category, page })}`)
export const listNotifications = (query: QueryParams) => request<Paginated<Notification>>('GET', `/api/notifications/${buildQuery(query)}`)
export const notificationSummary = () => request<{ unread_count: number }>('GET', '/api/notifications/summary/')
export const readNotifications = (ids: string[]) => request<{ changed_count: number }>('POST', '/api/notifications/read/', { ids })
export const getSubscription = (id: string) => request<Subscription>('GET', `/api/missions/${id}/subscription/`)
export const putSubscription = (id: string, mode: 'Follow' | 'Mute', expected_version: number) => request<Subscription>('PUT', `/api/missions/${id}/subscription/`, { mode, expected_version })
export const notifyChanged = () => window.dispatchEvent(new Event('notifications-changed'))
