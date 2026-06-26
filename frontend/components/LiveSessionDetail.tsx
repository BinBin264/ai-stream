'use client'

import { useCallback, useEffect, useMemo, useState } from 'react'
import Link from 'next/link'
import { useRouter } from 'next/navigation'
import {
  Activity,
  ArrowLeft,
  MessageSquare,
  Radio,
  RefreshCcw,
  Square,
  Trash2,
  Wand2,
} from 'lucide-react'
import { api, liveWsUrl, type LiveComment, type LiveSession, type ResponseJob } from '@/lib/api'
import { LocalPlayoutPreview } from './LocalPlayoutPreview'
import { StatusPill } from './StatusPill'

type StreamEvent = {
  type: string
  comment?: LiveComment
  job?: ResponseJob
  live?: LiveSession
}

interface Props {
  liveId: string
}

export function LiveSessionDetail({ liveId }: Props) {
  const router = useRouter()
  const [live, setLive] = useState<LiveSession | null>(null)
  const [comments, setComments] = useState<LiveComment[]>([])
  const [jobs, setJobs] = useState<ResponseJob[]>([])
  const [broadcasterRunning, setBroadcasterRunning] = useState(false)
  const [log, setLog] = useState<string[]>([])
  const [busy, setBusy] = useState(false)

  const queuedComments = useMemo(
    () => comments.filter((c) => c.status === 'queued'),
    [comments],
  )

  const pushLog = (line: string) =>
    setLog((prev) => [`${new Date().toLocaleTimeString()} ${line}`, ...prev].slice(0, 80))

  const refresh = useCallback(async () => {
    const detail = await api.getLive(liveId)
    setLive(detail.live)
    setComments(detail.comments)
    setJobs(detail.jobs)
    setBroadcasterRunning(detail.broadcaster_running)
  }, [liveId])

  useEffect(() => {
    refresh().catch((e) => pushLog(`Load failed: ${e.message}`))
    const timer = setInterval(() => refresh().catch(() => {}), 5000)
    return () => clearInterval(timer)
  }, [refresh])

  useEffect(() => {
    const ws = new WebSocket(liveWsUrl(liveId))
    ws.onopen = () => pushLog('Realtime connected')
    ws.onmessage = (event) => {
      const data = JSON.parse(event.data) as StreamEvent
      if (data.comment) setComments((prev) => [...prev, data.comment!])
      if (data.job) setJobs((prev) => [data.job!, ...prev])
      if (data.live) setLive(data.live)
      pushLog(`Event: ${data.type}`)
    }
    ws.onclose = () => pushLog('Realtime disconnected')
    return () => ws.close()
  }, [liveId])

  async function runAction(action: 'start' | 'go-live' | 'stop') {
    if (!live) return
    setBusy(true)
    try {
      const result =
        action === 'start'
          ? await api.startLive(live.id)
          : action === 'go-live'
            ? await api.goLive(live.id)
            : await api.stopLive(live.id)
      setLive(result.live)
      pushLog(`${action} → ${result.live.status}`)
    } catch (err) {
      pushLog(`Action failed: ${err instanceof Error ? err.message : 'unknown'}`)
    } finally {
      setBusy(false)
    }
  }

  async function answer(comment: LiveComment) {
    setBusy(true)
    try {
      const result = await api.answerComment(comment.id)
      setJobs((prev) => [result.job, ...prev])
      pushLog(`Answered comment ${comment.id.slice(0, 8)}`)
    } finally {
      setBusy(false)
    }
  }

  async function deleteSession() {
    if (!live || !window.confirm('Xóa phiên live này khỏi giao diện?')) return
    setBusy(true)
    try {
      await api.deleteLive(live.id)
      router.push('/')
    } catch (err) {
      pushLog(`Delete failed: ${err instanceof Error ? err.message : 'unknown'}`)
    } finally {
      setBusy(false)
    }
  }

  return (
    <main className="min-h-screen p-6">
      <div className="mx-auto flex max-w-7xl flex-col gap-5">
        {/* Header */}
        <header className="flex flex-col gap-3 border-b border-line pb-5 md:flex-row md:items-center md:justify-between">
          <div className="flex items-center gap-3">
            <Link
              href="/"
              className="rounded-md border border-line bg-white p-2 text-slate-500 hover:text-slate-800"
            >
              <ArrowLeft size={16} />
            </Link>
            <div>
              <h1 className="text-xl font-bold tracking-tight">
                {live?.title ?? 'Loading…'}
              </h1>
              <p className="mt-0.5 font-mono text-xs text-slate-400">{liveId.slice(0, 8)}</p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            {live && <StatusPill status={live.status} />}
            <button
              onClick={() => refresh().catch(() => {})}
              className="rounded-md border border-line bg-white p-2 text-slate-500 hover:text-slate-800"
            >
              <RefreshCcw size={15} />
            </button>
            <button
              disabled={busy || !live || ['preview', 'live'].includes(live.status)}
              onClick={deleteSession}
              title="Xóa phiên"
              className="rounded-md border border-red-300 bg-red-50 p-2 text-red-700 hover:bg-red-100 disabled:opacity-40"
            >
              <Trash2 size={15} />
            </button>
          </div>
        </header>

        <div className="grid grid-cols-1 gap-4 lg:grid-cols-[320px_1fr]">
          {/* Left: playout preview + live controls */}
          <aside className="flex flex-col gap-4">
            {/* Live session controls */}
            <div className="rounded-lg border border-line bg-white p-4">
              <h2 className="mb-3 flex items-center gap-2 text-sm font-semibold">
                <Radio size={15} /> Live Control
              </h2>
              <div className="grid grid-cols-2 gap-2">
                <button
                  disabled={busy || !live}
                  onClick={() => runAction('go-live')}
                  className="rounded-md bg-live px-2 py-2 text-xs font-semibold text-white disabled:opacity-40"
                >
                  Go Live
                </button>
                <button
                  disabled={busy || !live}
                  onClick={() => runAction('stop')}
                  className="flex items-center justify-center gap-1 rounded-md border border-line bg-white px-2 py-2 text-xs font-semibold disabled:opacity-40"
                >
                  <Square size={12} /> Stop
                </button>
              </div>
              <div className="mt-3 rounded-md bg-panel p-3 text-xs">
                <div className="flex justify-between py-1">
                  <span className="text-slate-500">Broadcaster</span>
                  <span
                    className={
                      broadcasterRunning
                        ? 'font-semibold text-emerald-700'
                        : 'text-slate-400'
                    }
                  >
                    {broadcasterRunning ? 'running' : 'stopped'}
                  </span>
                </div>
                <div className="flex justify-between py-1">
                  <span className="text-slate-500">Queued comments</span>
                  <span className="font-semibold">{queuedComments.length}</span>
                </div>
              </div>
            </div>

            {/* Playout preview */}
            <LocalPlayoutPreview liveSessionId={liveId} />
          </aside>

          {/* Right: comments, jobs, log */}
          <section className="grid grid-cols-1 gap-4 xl:grid-cols-2">
            {/* Comments */}
            <div className="rounded-lg border border-line bg-white p-4">
              <h2 className="mb-3 flex items-center gap-2 text-sm font-semibold">
                <MessageSquare size={15} /> Bình luận ({comments.length})
              </h2>
              <div className="flex max-h-[400px] flex-col gap-2 overflow-auto">
                {comments.map((comment) => (
                  <div key={comment.id} className="rounded-md border border-line p-3">
                    <div className="flex items-center justify-between gap-2">
                      <span className="text-sm font-semibold">{comment.user_name}</span>
                      <span className="text-xs text-slate-400">p{comment.priority}</span>
                    </div>
                    <p className="mt-1 text-sm text-slate-700">{comment.text}</p>
                    <button
                      disabled={busy}
                      onClick={() => answer(comment)}
                      className="mt-2 flex items-center gap-1 rounded-md border border-line bg-white px-2.5 py-1.5 text-xs font-semibold disabled:opacity-40"
                    >
                      <Wand2 size={12} /> Trả lời
                    </button>
                  </div>
                ))}
                {comments.length === 0 && (
                  <p className="text-sm text-slate-400">Chưa có bình luận.</p>
                )}
              </div>
            </div>

            {/* Response jobs */}
            <div className="rounded-lg border border-line bg-white p-4">
              <h2 className="mb-3 flex items-center gap-2 text-sm font-semibold">
                <Activity size={15} /> Response Jobs ({jobs.length})
              </h2>
              <div className="flex max-h-[400px] flex-col gap-2 overflow-auto">
                {jobs.map((job) => (
                  <div key={job.id} className="rounded-md bg-panel p-3 text-sm">
                    <div className="font-semibold">{job.status}</div>
                    <p className="mt-1 text-slate-600">{job.response_text || job.prompt}</p>
                  </div>
                ))}
                {jobs.length === 0 && (
                  <p className="text-sm text-slate-400">Chưa có job nào.</p>
                )}
              </div>
            </div>

            {/* Event log */}
            <div className="rounded-lg border border-line bg-white p-4 xl:col-span-2">
              <h2 className="mb-3 text-sm font-semibold">Event Log</h2>
              <div className="max-h-[240px] overflow-auto rounded-md bg-ink p-3 font-mono text-xs text-slate-300">
                {log.length === 0 ? (
                  <span className="text-slate-500">Waiting for events…</span>
                ) : (
                  log.map((line, i) => <div key={i}>{line}</div>)
                )}
              </div>
            </div>
          </section>
        </div>
      </div>
    </main>
  )
}
