'use client'

import Link from 'next/link'
import { Trash2 } from 'lucide-react'
import { type LiveSession, type PlayoutSession } from '@/lib/api'
import { HlsPlayer } from './HlsPlayer'

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8100'

const LIVE_STATUS_COLORS: Record<string, string> = {
  draft: 'bg-slate-100 text-slate-600',
  preview: 'bg-blue-100 text-blue-700',
  live: 'bg-red-100 text-red-700',
  stopped: 'bg-slate-100 text-slate-500',
  error: 'bg-red-200 text-red-800',
}

interface Props {
  live: LiveSession
  playout: PlayoutSession | null
  onStop: (force: boolean) => Promise<void>
  onDelete: () => Promise<void>
}

export function LiveSessionCard({ live, playout, onStop, onDelete }: Props) {
  const isActive = playout && ['idle', 'playing_talking', 'starting'].includes(playout.status)
  const canDelete = !isActive && !['preview', 'live'].includes(live.status)
  const hlsSrc =
    isActive && playout?.output_path ? `${API_URL}/media/${playout.output_path}` : null

  return (
    <div className="flex flex-col overflow-hidden rounded-xl border border-line bg-white shadow-sm">
      {/* Mini preview — portrait 9:16 */}
      <Link href={`/sessions/${live.id}`} className="block bg-black" style={{ aspectRatio: '9/16' }}>
        {hlsSrc ? (
          <HlsPlayer src={hlsSrc} />
        ) : (
          <div className="flex h-full items-center justify-center text-xs text-slate-500">
            No stream
          </div>
        )}
      </Link>

      {/* Card info */}
      <div className="flex flex-col gap-2 p-3">
        <div className="flex items-start justify-between gap-1">
          <div className="min-w-0">
            <div className="truncate text-sm font-semibold">{live.title}</div>
            <div className="mt-0.5 font-mono text-[10px] text-slate-400">{live.id.slice(0, 8)}</div>
          </div>
          <span
            className={`shrink-0 rounded-full px-2 py-0.5 text-[10px] font-semibold ${LIVE_STATUS_COLORS[live.status] ?? 'bg-slate-100 text-slate-600'}`}
          >
            {live.status}
          </span>
        </div>

        <div className="flex gap-1.5">
          <Link
            href={`/sessions/${live.id}`}
            className="flex-1 rounded-md bg-ink py-1.5 text-center text-[11px] font-semibold text-white"
          >
            Open
          </Link>
          {isActive && (
            <button
              onClick={() => onStop(true)}
              className="rounded-md border border-red-300 bg-red-50 px-2.5 py-1.5 text-[11px] font-semibold text-red-700"
            >
              Stop
            </button>
          )}
          {canDelete && (
            <button
              onClick={onDelete}
              title="Xóa phiên"
              className="rounded-md border border-red-300 bg-red-50 px-2.5 py-1.5 text-red-700 hover:bg-red-100"
            >
              <Trash2 size={13} />
            </button>
          )}
        </div>
      </div>
    </div>
  )
}
