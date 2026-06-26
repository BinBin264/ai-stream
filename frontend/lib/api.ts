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

export interface PlayoutSession {
  session_id: string
  avatar_id: string
  live_session_id: string | null
  status: string
  output_mode: string
  idle_video_path: string
  output_path: string | null
  active_segment_id: string | null
  error_code: string | null
  error_message: string | null
}

export interface PlayoutHealth {
  session_id: string
  status: string
  runtime_alive: boolean
  active_segment_id: string | null
  queued_segments: number
  output_path: string | null
  last_error_code: string | null
}

export interface PlayoutSegment {
  segment_id: string
  playout_session_id: string
  status: string
  priority: string
  source_video_path: string | null
  error_code: string | null
  error_message: string | null
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
  if (response.status === 204) {
    return undefined as T
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
  deleteLive: (liveId: string) => request<void>(`/api/live/${liveId}`, { method: 'DELETE' }),
  answerComment: (commentId: string) =>
    request<{ job: ResponseJob }>(`/api/comments/${commentId}/answer`, { method: 'POST' }),
  listPlayoutSessions: () =>
    request<{ items: PlayoutSession[] }>('/api/playout-sessions'),
  createPlayoutSession: (avatarId: string, liveSessionId: string | null, outputMode: string) =>
    request<PlayoutSession>('/api/playout-sessions', {
      method: 'POST',
      body: JSON.stringify({ avatar_id: avatarId, live_session_id: liveSessionId, output_mode: outputMode }),
    }),
  startPlayoutSession: (sessionId: string) =>
    request<{ session_id: string; status: string }>(`/api/playout-sessions/${sessionId}/start`, { method: 'POST' }),
  stopPlayoutSession: (sessionId: string, force = false) =>
    request<{ session_id: string; status: string }>(`/api/playout-sessions/${sessionId}/stop`, {
      method: 'POST',
      body: JSON.stringify({ force }),
    }),
  deletePlayoutSession: (sessionId: string) =>
    request<void>(`/api/playout-sessions/${sessionId}`, { method: 'DELETE' }),
  getPlayoutHealth: (sessionId: string) =>
    request<PlayoutHealth>(`/api/playout-sessions/${sessionId}/health`),
  submitPlayoutScript: (sessionId: string, text: string, priority = 'P2') =>
    request<{ render_job_id: string; playout_segment_id: string | null; status: string; message: string }>(
      `/api/playout-sessions/${sessionId}/scripts`,
      { method: 'POST', body: JSON.stringify({ text, priority }) },
    ),
  enqueuePlayoutSegment: (sessionId: string, sourceVideoPath: string, priority = 'P2') =>
    request<PlayoutSegment>(`/api/playout-sessions/${sessionId}/segments`, {
      method: 'POST',
      body: JSON.stringify({ source_video_path: sourceVideoPath, priority }),
    }),
}

export function liveWsUrl(liveId: string): string {
  return `${WS_URL}/ws/live/${encodeURIComponent(liveId)}`
}
