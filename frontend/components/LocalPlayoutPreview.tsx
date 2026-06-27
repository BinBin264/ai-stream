'use client'

import { useCallback, useEffect, useRef, useState } from 'react'
import { Play, Square, Send, RefreshCcw, AlertCircle } from 'lucide-react'
import { api, type PlayoutHealth, type PlayoutSession } from '@/lib/api'
import { HlsPlayer } from './HlsPlayer'

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8100'

const STATUS_COLORS: Record<string, string> = {
  stopped: 'bg-slate-100 text-slate-600',
  stopping: 'bg-amber-100 text-amber-700',
  starting: 'bg-blue-100 text-blue-700',
  idle: 'bg-emerald-100 text-emerald-700',
  playing_talking: 'bg-red-100 text-red-700',
  failed: 'bg-red-200 text-red-800',
}

interface Props {
  liveSessionId?: string | null
  avatarId?: string
}

export function LocalPlayoutPreview({ liveSessionId, avatarId = 'model_01' }: Props) {
  const [session, setSession] = useState<PlayoutSession | null>(null)
  const [health, setHealth] = useState<PlayoutHealth | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [scriptText, setScriptText] = useState('')
  const [log, setLog] = useState<string[]>([])

  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const pushLog = (line: string) =>
    setLog((prev) => [`${new Date().toLocaleTimeString()} ${line}`, ...prev].slice(0, 40))

  const clearError = () => setError('')

  const pollHealth = useCallback(async (sid: string) => {
    try {
      const h = await api.getPlayoutHealth(sid)
      setHealth(h)
      if (h.status === 'stopped' || h.status === 'failed') {
        pollRef.current && clearInterval(pollRef.current)
        pollRef.current = null
        setSession(null)
        setHealth(null)
        api.deletePlayoutSession(sid).catch(() => {})
      }
    } catch {
      // ignore transient poll errors
    }
  }, [])

  const startPolling = useCallback((sid: string) => {
    if (pollRef.current) clearInterval(pollRef.current)
    pollRef.current = setInterval(() => pollHealth(sid), 2500)
  }, [pollHealth])

  useEffect(() => {
    // Reset state when switching live sessions
    setSession(null)
    setHealth(null)

    api.listPlayoutSessions().then(({ items }) => {
      const active = items.find(
        (s) =>
          (!liveSessionId || s.live_session_id === liveSessionId) &&
          !['stopped', 'failed'].includes(s.status),
      )
      if (active) {
        setSession(active)
        startPolling(active.session_id)
        pollHealth(active.session_id)
      }
    }).catch(() => {})
    return () => { pollRef.current && clearInterval(pollRef.current) }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [liveSessionId])

  async function startStream() {
    setBusy(true)
    clearError()
    try {
      const s = await api.createPlayoutSession(avatarId, liveSessionId ?? null, 'local_preview')
      setSession(s)
      setHealth(null)
      await api.startPlayoutSession(s.session_id)
      pushLog(`Stream started: ${s.session_id.slice(0, 8)}`)
      startPolling(s.session_id)
      await pollHealth(s.session_id)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to start stream')
    } finally {
      setBusy(false)
    }
  }

  async function stopSession(force: boolean) {
    if (!session) return
    setBusy(true)
    clearError()
    try {
      await api.stopPlayoutSession(session.session_id, force)
      pushLog(force ? 'Force stop requested' : 'Graceful stop requested')
      await pollHealth(session.session_id)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to stop')
    } finally {
      setBusy(false)
    }
  }

  async function submitScript() {
    if (!session || !scriptText.trim()) return
    setBusy(true)
    clearError()
    try {
      const result = await api.submitPlayoutScript(session.session_id, scriptText.trim())
      pushLog(`Script queued: job ${result.render_job_id.slice(0, 8)}`)
      setScriptText('')
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to submit script')
    } finally {
      setBusy(false)
    }
  }


  const status = health?.status ?? session?.status ?? 'stopped'
  const isRunning = ['starting', 'idle', 'playing_talking'].includes(status)
  // output_path is already the relative path to index.m3u8 (e.g. "playout/live/{id}/index.m3u8")
  const rawPath = health?.output_path ?? session?.output_path
  const hlsSrc = rawPath ? `${API_URL}/media/${rawPath}` : null

  return (
    <div className="flex flex-col gap-4 rounded-lg border border-line bg-white p-4">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold">Local Playout Preview</h2>
        <div className="flex items-center gap-2">
          <span className={`rounded-full px-2 py-0.5 text-xs font-semibold ${STATUS_COLORS[status] ?? 'bg-slate-100 text-slate-600'}`}>
            {status}
          </span>
          {session && (
            <button
              onClick={() => pollHealth(session.session_id)}
              title="Refresh health"
              className="text-slate-400 hover:text-slate-700"
            >
              <RefreshCcw size={13} />
            </button>
          )}
        </div>
      </div>

      {/* Error banner */}
      {error && (
        <div className="flex items-start gap-2 rounded-md bg-red-50 p-3 text-xs text-red-700">
          <AlertCircle size={14} className="mt-0.5 shrink-0" />
          <span className="flex-1">{error}</span>
          <button onClick={clearError} className="text-red-400 hover:text-red-700">✕</button>
        </div>
      )}

      {/* Session controls */}
      <div className="flex flex-wrap gap-2">
        <button
          disabled={busy || isRunning}
          onClick={startStream}
          className="flex items-center gap-1 rounded-md bg-ink px-3 py-1.5 text-xs font-semibold text-white disabled:opacity-40"
        >
          <Play size={12} /> Start Stream
        </button>
        <button
          disabled={busy || !isRunning}
          onClick={() => stopSession(true)}
          className="flex items-center gap-1 rounded-md border border-red-300 bg-red-50 px-3 py-1.5 text-xs font-semibold text-red-700 disabled:opacity-40"
        >
          <Square size={12} /> Stop
        </button>
      </div>

      {/* Stats row */}
      {health && (
        <div className="grid grid-cols-2 gap-2 text-xs">
          <div className="rounded-md bg-panel p-2">
            <div className="text-slate-500">Queued segments</div>
            <div className="mt-0.5 font-semibold">{health.queued_segments}</div>
          </div>
          <div className="rounded-md bg-panel p-2">
            <div className="text-slate-500">Active segment</div>
            <div className="mt-0.5 font-mono">{health.active_segment_id?.slice(0, 8) ?? '—'}</div>
          </div>
        </div>
      )}

      {/* HLS video player */}
      {hlsSrc ? (
        <HlsPlayer src={hlsSrc} />
      ) : (
        <div className="flex aspect-[9/16] w-full items-center justify-center rounded-md bg-slate-100 text-xs text-slate-400">
          {session ? 'Waiting for stream…' : 'No active session'}
        </div>
      )}

      {/* Script input */}
      {session && (
        <div className="flex flex-col gap-2">
          <label className="text-xs font-semibold text-slate-600">Submit Script</label>
          <textarea
            value={scriptText}
            onChange={(e) => setScriptText(e.target.value)}
            placeholder="Nhập văn bản để AI nói..."
            rows={3}
            className="w-full resize-none rounded-md border border-line px-3 py-2 text-xs focus:outline-none focus:ring-1 focus:ring-ink"
          />
          <button
            disabled={busy || !scriptText.trim() || !isRunning}
            onClick={submitScript}
            className="flex items-center justify-center gap-1 rounded-md bg-ink px-3 py-1.5 text-xs font-semibold text-white disabled:opacity-40"
          >
            <Send size={12} /> Send Script
          </button>
        </div>
      )}


      {/* Event log */}
      {log.length > 0 && (
        <div className="max-h-[120px] overflow-auto rounded-md bg-ink p-2 font-mono text-[10px] text-slate-300">
          {log.map((line, i) => <div key={i}>{line}</div>)}
        </div>
      )}

      {/* Session ID footer */}
      {session && (
        <p className="text-[10px] text-slate-400">
          Session: <span className="font-mono">{session.session_id}</span>
        </p>
      )}
    </div>
  )
}
