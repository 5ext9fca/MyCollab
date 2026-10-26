import { request } from './client'

export type TransferStatus = 'waiting' | 'paired' | 'accepted' | 'completed' | 'failed' | 'cancelled' | 'expired'
export interface TransferSession {
  id: string
  role: 'sender' | 'receiver'
  name: string
  size: number
  sha256: string
  received_sha256: string
  status: TransferStatus
  error: string
  sender_name: string
  receiver_name: string | null
  pair_expires_at: string
  expires_at: string
  offer: string
  answer: string
  code?: string
}
export type TransferAction = 'poll' | 'accept' | 'offer' | 'answer' | 'complete' | 'cancel' | 'fail'
export function createTransfer(file: { name: string; size: number; sha256: string }, token: string) {
  return request<TransferSession>('POST', '/api/file-transfers/', { ...file, token }, AbortSignal.timeout(15000))
}
export function joinTransfer(code: string, token: string) {
  return request<TransferSession>('POST', '/api/file-transfers/join/', { code, token }, AbortSignal.timeout(15000))
}
export function operateTransfer(id: string, token: string, action: TransferAction = 'poll', extra: { sdp?: string; sha256?: string; error?: string } = {}) {
  return request<TransferSession>('POST', `/api/file-transfers/${id}/`, { token, action, ...extra }, AbortSignal.timeout(15000))
}
