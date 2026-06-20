import type { LiveStatus } from '@/lib/api'

const colors: Record<LiveStatus, string> = {
  draft: 'bg-zinc-200 text-zinc-700',
  preview: 'bg-amber-100 text-amber-800',
  live: 'bg-rose-600 text-white',
  stopped: 'bg-slate-200 text-slate-700',
  error: 'bg-red-100 text-red-800',
}

export function StatusPill({ status }: { status: LiveStatus }) {
  return (
    <span className={`inline-flex items-center rounded-full px-2.5 py-1 text-xs font-semibold ${colors[status]}`}>
      {status.toUpperCase()}
    </span>
  )
}
