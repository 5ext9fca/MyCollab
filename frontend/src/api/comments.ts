/** Mission comments. Content is Markdown, same as Mission.content. */
import { buildQuery, request } from './client'
import type { QueryParams } from './client'
import type { Comment, Paginated } from './types'

export const listComments = (
  missionId: string,
  params: QueryParams = {},
): Promise<Paginated<Comment>> =>
  request<Paginated<Comment>>(
    'GET',
    `/api/missions/${missionId}/comments/${buildQuery(params)}`,
  )

export const createComment = (missionId: string, content: string): Promise<Comment> =>
  request<Comment>('POST', `/api/missions/${missionId}/comments/`, { content })

export const updateComment = (commentId: string, content: string): Promise<Comment> =>
  request<Comment>('PATCH', `/api/comments/${commentId}/`, { content })

export const deleteComment = (commentId: string): Promise<void> =>
  request<void>('DELETE', `/api/comments/${commentId}/`)
