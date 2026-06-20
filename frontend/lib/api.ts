export type LiveStatus = 'draft' | 'preview' | 'live' | 'stopped' | 'error'

export interface LiveSession {
  id: string
  title: string
  status: LiveStatus
  facebook_live_video_id?: string | null
  rtmps_url?: string | null
  stream_key?: string | null
  created_at: string
}

export interface LiveComment {
  id: string
  live_id: string
  facebook_comment_id?: string | null
  user_name: string
  text: string
  status: string
  priority: number
  created_at: string
}

export interface ResponseJob {
  id: string
  live_id: string
  comment_id: string
  prompt: string
  status: string
  response_text?: string | null
  media_path?: string | null
  created_at: string
}

export interface OpsDashboard {
  live_sessions: number
  comments: number
  queued_comments: number
  orders: number
  stock_reserved_orders: number
  active_reservations: number
  human_handover: number
  failed_comments: number
  speech_queue: number
}

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8100'
const WS_URL = process.env.NEXT_PUBLIC_WS_URL || 'ws://localhost:8100'

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_URL}${path}`, {
    ...init,
    headers: {
      'content-type': 'application/json',
      ...(init?.headers || {}),
    },
  })
  if (!response.ok) {
    throw new Error(await response.text())
  }
  return response.json() as Promise<T>
}

export const api = {
  health: () => request<{ status: string }>('/health'),
  opsDashboard: () => request<OpsDashboard>('/api/ops/live-dashboard'),
  listLives: () => request<{ items: LiveSession[] }>('/api/live'),
  createLive: (title: string) =>
    request<{ live: LiveSession }>('/api/live', {
      method: 'POST',
      body: JSON.stringify({ title }),
    }),
  getLive: (liveId: string) =>
    request<{
      live: LiveSession
      broadcaster_running: boolean
      comments: LiveComment[]
      jobs: ResponseJob[]
    }>(`/api/live/${liveId}`),
  startLive: (liveId: string) => request<{ live: LiveSession }>(`/api/live/${liveId}/start`, { method: 'POST' }),
  goLive: (liveId: string) => request<{ live: LiveSession }>(`/api/live/${liveId}/go-live`, { method: 'POST' }),
  stopLive: (liveId: string) => request<{ live: LiveSession }>(`/api/live/${liveId}/stop`, { method: 'POST' }),
  answerComment: (commentId: string) =>
    request<{ job: ResponseJob }>(`/api/comments/${commentId}/answer`, { method: 'POST' }),
}

export function liveWsUrl(liveId: string): string {
  return `${WS_URL}/ws/live/${encodeURIComponent(liveId)}`
}
