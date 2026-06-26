'use client'

import { useEffect, useMemo, useState } from 'react'
import { Activity, MessageSquare, Play, Radio, RefreshCcw, Square, Wand2 } from 'lucide-react'
import { api, liveWsUrl, type LiveComment, type LiveSession, type OpsDashboard, type ResponseJob } from '@/lib/api'
import { LocalPlayoutPreview } from './LocalPlayoutPreview'
import { StatusPill } from './StatusPill'

type StreamEvent = {
  type: string
  comment?: LiveComment
  job?: ResponseJob
  live?: LiveSession
}

export function OperatorDashboard() {
  const [title, setTitle] = useState('DTP AI Live')
  const [lives, setLives] = useState<LiveSession[]>([])
  const [activeLive, setActiveLive] = useState<LiveSession | null>(null)
  const [comments, setComments] = useState<LiveComment[]>([])
  const [jobs, setJobs] = useState<ResponseJob[]>([])
  const [ops, setOps] = useState<OpsDashboard | null>(null)
  const [broadcasterRunning, setBroadcasterRunning] = useState(false)
  const [log, setLog] = useState<string[]>(['Dashboard ready'])
  const [busy, setBusy] = useState(false)

  const activeLiveId = activeLive?.id
  const queuedComments = useMemo(() => comments.filter((comment) => comment.status === 'queued'), [comments])

  const pushLog = (line: string) => {
    setLog((prev) => [`${new Date().toLocaleTimeString()} ${line}`, ...prev].slice(0, 80))
  }

  async function refresh() {
    const [list, opsDashboard] = await Promise.all([
      api.listLives(),
      api.opsDashboard(),
    ])
    setOps(opsDashboard)
    setLives(list.items)
    const selected = activeLiveId ? list.items.find((item) => item.id === activeLiveId) : list.items[0]
    if (selected) {
      const detail = await api.getLive(selected.id)
      setActiveLive(detail.live)
      setComments(detail.comments)
      setJobs(detail.jobs)
      setBroadcasterRunning(detail.broadcaster_running)
    }
  }

  async function createLive() {
    setBusy(true)
    try {
      const result = await api.createLive(title)
      setActiveLive(result.live)
      pushLog(`Created live ${result.live.id}`)
      await refresh()
    } finally {
      setBusy(false)
    }
  }

  async function runAction(action: 'start' | 'go-live' | 'stop') {
    if (!activeLive) return
    setBusy(true)
    try {
      const result =
        action === 'start'
          ? await api.startLive(activeLive.id)
          : action === 'go-live'
            ? await api.goLive(activeLive.id)
            : await api.stopLive(activeLive.id)
      setActiveLive(result.live)
      pushLog(`${action} -> ${result.live.status}`)
      await refresh()
    } catch (error) {
      pushLog(`Action failed: ${error instanceof Error ? error.message : 'unknown error'}`)
    } finally {
      setBusy(false)
    }
  }

  async function answer(comment: LiveComment) {
    setBusy(true)
    try {
      const result = await api.answerComment(comment.id)
      setJobs((prev) => [result.job, ...prev])
      pushLog(`Answered comment ${comment.id}`)
    } finally {
      setBusy(false)
    }
  }

  useEffect(() => {
    refresh().catch((error) => pushLog(`Refresh failed: ${error.message}`))
    const timer = setInterval(() => refresh().catch(() => undefined), 5000)
    return () => clearInterval(timer)
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    if (!activeLiveId) return
    const ws = new WebSocket(liveWsUrl(activeLiveId))
    ws.onopen = () => pushLog('Realtime connected')
    ws.onmessage = (event) => {
      const data = JSON.parse(event.data) as StreamEvent
      if (data.comment) setComments((prev) => [...prev, data.comment!])
      if (data.job) setJobs((prev) => [data.job!, ...prev])
      if (data.live) setActiveLive(data.live)
      pushLog(`Event: ${data.type}`)
    }
    ws.onclose = () => pushLog('Realtime disconnected')
    return () => ws.close()
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeLiveId])

  return (
    <main className="min-h-screen p-6">
      <div className="mx-auto flex max-w-7xl flex-col gap-5">
        <header className="flex flex-col gap-3 border-b border-line pb-5 md:flex-row md:items-center md:justify-between">
          <div>
            <h1 className="text-2xl font-bold tracking-tight">DTP AI Stream</h1>
            <p className="mt-1 text-sm text-slate-600">Facebook livestream operator dashboard</p>
          </div>
          <div className="flex items-center gap-2">
            {activeLive && <StatusPill status={activeLive.status} />}
            <button onClick={refresh} className="rounded-md border border-line bg-white px-3 py-2 text-sm font-medium">
              <RefreshCcw size={16} />
            </button>
          </div>
        </header>

        <section className="grid grid-cols-1 gap-4 lg:grid-cols-[360px_1fr]">
          <aside className="flex flex-col gap-4">
            <div className="rounded-lg border border-line bg-white p-4">
              <h2 className="mb-3 flex items-center gap-2 text-sm font-semibold">
                <Radio size={16} /> Live Control
              </h2>
              <input
                value={title}
                onChange={(event) => setTitle(event.target.value)}
                className="mb-3 w-full rounded-md border border-line px-3 py-2 text-sm"
                placeholder="Live title"
              />
              <div className="grid grid-cols-2 gap-2">
                <button disabled={busy} onClick={createLive} className="rounded-md bg-ink px-3 py-2 text-sm font-semibold text-white">
                  Create
                </button>
                <button disabled={busy || !activeLive} onClick={() => runAction('start')} className="rounded-md border border-line bg-white px-3 py-2 text-sm font-semibold">
                  <Play className="mr-1 inline" size={14} /> Preview
                </button>
                <button disabled={busy || !activeLive} onClick={() => runAction('go-live')} className="rounded-md bg-live px-3 py-2 text-sm font-semibold text-white">
                  Go Live
                </button>
                <button disabled={busy || !activeLive} onClick={() => runAction('stop')} className="rounded-md border border-line bg-white px-3 py-2 text-sm font-semibold">
                  <Square className="mr-1 inline" size={14} /> Stop
                </button>
              </div>
            </div>

            <div className="rounded-lg border border-line bg-white p-4">
              <h2 className="mb-3 text-sm font-semibold">Sessions</h2>
              <div className="flex flex-col gap-2">
                {lives.map((live) => (
                  <button
                    key={live.id}
                    onClick={async () => {
                      const detail = await api.getLive(live.id)
                      setActiveLive(detail.live)
                      setComments(detail.comments)
                      setJobs(detail.jobs)
                      setBroadcasterRunning(detail.broadcaster_running)
                    }}
                    className={`rounded-md border px-3 py-2 text-left text-sm ${activeLive?.id === live.id ? 'border-ink bg-slate-100' : 'border-line bg-white'}`}
                  >
                    <div className="font-semibold">{live.title}</div>
                    <div className="mt-1 text-xs text-slate-500">{live.status} · {live.id.slice(0, 8)}</div>
                  </button>
                ))}
                {lives.length === 0 && <p className="text-sm text-slate-500">No live sessions yet.</p>}
              </div>
            </div>
            {/* Playout preview + controls */}
            <LocalPlayoutPreview liveSessionId={activeLive?.id ?? null} />
          </aside>

          <section className="grid grid-cols-1 gap-4 xl:grid-cols-2">
            <div className="rounded-lg border border-line bg-white p-4">
              <h2 className="mb-3 flex items-center gap-2 text-sm font-semibold">
                <Activity size={16} /> Stream Status
              </h2>
              <div className="rounded-md bg-panel p-4 text-sm">
                <div className="flex items-center justify-between border-b border-line pb-2">
                  <span>Active Live</span>
                  <span className="font-mono text-xs">{activeLive?.id.slice(0, 8) || '-'}</span>
                </div>
                <div className="flex items-center justify-between border-b border-line py-2">
                  <span>Broadcaster</span>
                  <span className={broadcasterRunning ? 'font-semibold text-emerald-700' : 'font-semibold text-slate-500'}>
                    {broadcasterRunning ? 'running' : 'stopped'}
                  </span>
                </div>
                <div className="flex items-center justify-between pt-2">
                  <span>Queued Comments</span>
                  <span className="font-semibold">{queuedComments.length}</span>
                </div>
              </div>
            </div>

            <div className="rounded-lg border border-line bg-white p-4">
              <h2 className="mb-3 text-sm font-semibold">Commerce Ops</h2>
              <div className="grid grid-cols-2 gap-2 text-sm">
                <div className="rounded-md bg-panel p-3">
                  <div className="text-xs text-slate-500">Orders</div>
                  <div className="mt-1 text-lg font-semibold">{ops?.orders ?? 0}</div>
                </div>
                <div className="rounded-md bg-panel p-3">
                  <div className="text-xs text-slate-500">Reserved</div>
                  <div className="mt-1 text-lg font-semibold">{ops?.active_reservations ?? 0}</div>
                </div>
                <div className="rounded-md bg-panel p-3">
                  <div className="text-xs text-slate-500">Handover</div>
                  <div className="mt-1 text-lg font-semibold">{ops?.human_handover ?? 0}</div>
                </div>
                <div className="rounded-md bg-panel p-3">
                  <div className="text-xs text-slate-500">Speech</div>
                  <div className="mt-1 text-lg font-semibold">{ops?.speech_queue ?? 0}</div>
                </div>
              </div>
            </div>

            <div className="rounded-lg border border-line bg-white p-4">
              <h2 className="mb-3 flex items-center gap-2 text-sm font-semibold">
                <MessageSquare size={16} /> Comment Queue
              </h2>
              <div className="flex max-h-[420px] flex-col gap-2 overflow-auto">
                {comments.map((comment) => (
                  <div key={comment.id} className="rounded-md border border-line p-3">
                    <div className="flex items-center justify-between gap-2">
                      <span className="text-sm font-semibold">{comment.user_name}</span>
                      <span className="text-xs text-slate-500">priority {comment.priority}</span>
                    </div>
                    <p className="mt-1 text-sm text-slate-700">{comment.text}</p>
                    <button
                      disabled={busy}
                      onClick={() => answer(comment)}
                      className="mt-3 rounded-md border border-line bg-white px-2.5 py-1.5 text-xs font-semibold"
                    >
                      <Wand2 className="mr-1 inline" size={13} /> Answer
                    </button>
                  </div>
                ))}
                {comments.length === 0 && <p className="text-sm text-slate-500">No comments yet.</p>}
              </div>
            </div>

            <div className="rounded-lg border border-line bg-white p-4">
              <h2 className="mb-3 text-sm font-semibold">Response Jobs</h2>
              <div className="flex max-h-[360px] flex-col gap-2 overflow-auto">
                {jobs.map((job) => (
                  <div key={job.id} className="rounded-md bg-panel p-3 text-sm">
                    <div className="font-semibold">{job.status}</div>
                    <p className="mt-1 text-slate-700">{job.response_text || job.prompt}</p>
                  </div>
                ))}
                {jobs.length === 0 && <p className="text-sm text-slate-500">No response jobs yet.</p>}
              </div>
            </div>

            <div className="rounded-lg border border-line bg-white p-4">
              <h2 className="mb-3 text-sm font-semibold">Event Log</h2>
              <div className="max-h-[360px] overflow-auto rounded-md bg-ink p-3 font-mono text-xs text-slate-100">
                {log.map((line, index) => (
                  <div key={`${line}-${index}`}>{line}</div>
                ))}
              </div>
            </div>
          </section>
        </section>
      </div>
    </main>
  )
}
