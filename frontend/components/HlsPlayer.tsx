'use client'

import { useEffect, useRef, useState } from 'react'

interface Props {
  src: string
}

export function HlsPlayer({ src }: Props) {
  const videoRef = useRef<HTMLVideoElement>(null)
  const [status, setStatus] = useState<'connecting' | 'playing' | 'error'>('connecting')
  const [errorMsg, setErrorMsg] = useState('')

  useEffect(() => {
    const video = videoRef.current
    if (!video || !src) return

    setStatus('connecting')
    setErrorMsg('')

    // Safari has native HLS support
    if (video.canPlayType('application/vnd.apple.mpegurl')) {
      video.src = src
      video.onloadeddata = () => setStatus('playing')
      video.onerror = () => { setStatus('error'); setErrorMsg('Stream unavailable') }
      return () => { video.src = '' }
    }

    let hls: import('hls.js').default | null = null

    import('hls.js').then(({ default: Hls }) => {
      if (!Hls.isSupported()) {
        setStatus('error')
        setErrorMsg('HLS not supported in this browser')
        return
      }

      hls = new Hls({ liveSyncDurationCount: 3, enableWorker: true })
      hls.loadSource(src)
      hls.attachMedia(video)

      hls.on(Hls.Events.MANIFEST_PARSED, () => {
        setStatus('playing')
        video.play().catch(() => {})
      })

      hls.on(Hls.Events.ERROR, (_evt, data) => {
        if (data.fatal) {
          setStatus('error')
          setErrorMsg(`${data.type} — ${data.details}`)
        }
      })
    })

    return () => {
      hls?.destroy()
      video.src = ''
    }
  }, [src])

  return (
    <div className="relative overflow-hidden rounded-md bg-black" style={{ aspectRatio: '9/16' }}>
      <video
        ref={videoRef}
        autoPlay
        muted
        playsInline
        className="h-full w-full object-cover"
      />

      {status === 'connecting' && (
        <div className="absolute inset-0 flex flex-col items-center justify-center gap-2 bg-black/80 text-white">
          <div className="h-5 w-5 animate-spin rounded-full border-2 border-white border-t-transparent" />
          <span className="text-xs">Connecting to stream…</span>
        </div>
      )}

      {status === 'error' && (
        <div className="absolute inset-0 flex flex-col items-center justify-center gap-1 bg-black/90 p-4 text-center text-xs text-red-400">
          <span className="text-base">⚠</span>
          <span>{errorMsg || 'Stream unavailable'}</span>
        </div>
      )}

      {status === 'playing' && (
        <div className="absolute bottom-2 right-2 rounded bg-red-600 px-1.5 py-0.5 text-[10px] font-bold text-white">
          LIVE
        </div>
      )}
    </div>
  )
}
