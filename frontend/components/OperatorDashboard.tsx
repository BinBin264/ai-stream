'use client'

import { useCallback, useEffect, useState } from 'react'
import { Plus, RefreshCcw } from 'lucide-react'
import { useRouter } from 'next/navigation'
import { api, type LiveSession, type PlayoutSession } from '@/lib/api'
import { LiveSessionCard } from './LiveSessionCard'

function isPlayoutActive(p: PlayoutSession) {
  return ['idle', 'playing_talking', 'starting'].includes(p.status)
}

export function OperatorDashboard() {
  const router = useRouter()
  const [lives, setLives] = useState<LiveSession[]>([])
  const [playouts, setPlayouts] = useState<PlayoutSession[]>([])
  const [showCreate, setShowCreate] = useState(false)
  const [title, setTitle] = useState('DTP AI Live')
  const [busy, setBusy] = useState(false)

  const refresh = useCallback(async () => {
    const [livesData, playoutsData] = await Promise.all([
      api.listLives(),
      api.listPlayoutSessions(),
    ])
    setLives(livesData.items)
    setPlayouts(playoutsData.items)
  }, [])

  useEffect(() => {
    refresh().catch(() => {})
    const timer = setInterval(() => refresh().catch(() => {}), 5000)
    return () => clearInterval(timer)
  }, [refresh])

  async function createLive() {
    setBusy(true)
    try {
      const result = await api.createLive(title)
      router.push(`/sessions/${result.live.id}`)
    } finally {
      setBusy(false)
      setShowCreate(false)
    }
  }

  async function handleStop(liveId: string, force: boolean) {
    const playout = playouts.find(
      (p) => p.live_session_id === liveId && isPlayoutActive(p),
    )
    if (!playout) return
    await api.stopPlayoutSession(playout.session_id, force)
    await refresh()
  }

  async function handleDelete(liveId: string) {
    if (!window.confirm('Xóa phiên live này khỏi giao diện?')) return
    await api.deleteLive(liveId)
    await refresh()
  }

  function getPlayout(liveId: string): PlayoutSession | null {
    return (
      playouts.find((p) => p.live_session_id === liveId && isPlayoutActive(p)) ?? null
    )
  }

  return (
    <main className="min-h-screen p-6">
      <div className="mx-auto max-w-7xl">
        {/* Header */}
        <header className="mb-6 flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold tracking-tight">DTP AI Stream</h1>
            <p className="mt-0.5 text-sm text-slate-500">{lives.length} phiên live</p>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={() => refresh().catch(() => {})}
              className="rounded-md border border-line bg-white p-2 text-slate-500 hover:text-slate-800"
            >
              <RefreshCcw size={15} />
            </button>
            <button
              onClick={() => setShowCreate(true)}
              className="flex items-center gap-1.5 rounded-md bg-ink px-3 py-2 text-sm font-semibold text-white"
            >
              <Plus size={15} /> Tạo phiên
            </button>
          </div>
        </header>

        {/* Create session inline form */}
        {showCreate && (
          <div className="mb-6 rounded-xl border border-line bg-white p-4 shadow-sm">
            <h2 className="mb-3 text-sm font-semibold">Phiên live mới</h2>
            <div className="flex gap-2">
              <input
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                className="flex-1 rounded-md border border-line px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-ink"
                placeholder="Tên phiên live"
                autoFocus
                onKeyDown={(e) => e.key === 'Enter' && createLive()}
              />
              <button
                disabled={busy || !title.trim()}
                onClick={createLive}
                className="rounded-md bg-ink px-4 py-2 text-sm font-semibold text-white disabled:opacity-40"
              >
                Tạo
              </button>
              <button
                onClick={() => setShowCreate(false)}
                className="rounded-md border border-line bg-white px-3 py-2 text-sm"
              >
                Hủy
              </button>
            </div>
          </div>
        )}

        {/* Sessions grid */}
        {lives.length === 0 ? (
          <div className="flex flex-col items-center justify-center rounded-xl border-2 border-dashed border-line py-32 text-center">
            <p className="text-slate-400">Chưa có phiên live nào</p>
            <button
              onClick={() => setShowCreate(true)}
              className="mt-4 flex items-center gap-1.5 rounded-md bg-ink px-4 py-2 text-sm font-semibold text-white"
            >
              <Plus size={15} /> Tạo phiên đầu tiên
            </button>
          </div>
        ) : (
          <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5">
            {lives.map((live) => (
              <LiveSessionCard
                key={live.id}
                live={live}
                playout={getPlayout(live.id)}
                onStop={(force) => handleStop(live.id, force)}
                onDelete={() => handleDelete(live.id)}
              />
            ))}
          </div>
        )}
      </div>
    </main>
  )
}
