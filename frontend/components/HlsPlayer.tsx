'use client'

import { useEffect, useRef, useState } from 'react'

interface Props {
  src: string
}

const RETRY_INTERVAL_MS = 5000
const MAX_RETRIES = 24

export function HlsPlayer({ src }: Props) {
  const videoRef = useRef<HTMLVideoElement>(null)
  const [status, setStatus] = useState<'connecting' | 'playing' | 'error'>('connecting')
  const [errorMsg, setErrorMsg] = useState('')
  const [retryCount, setRetryCount] = useState(0)
  const [muted, setMuted] = useState(true)
  const [volume, setVolume] = useState(80)
  const retryTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const retryRef = useRef(0)

  // Sync volume to video element whenever it changes
  useEffect(() => {
    const video = videoRef.current
    if (!video) return
    video.volume = volume / 100
  }, [volume])

  useEffect(() => {
    const video = videoRef.current
    if (!video || !src) return

    setStatus('connecting')
    setErrorMsg('')
    setRetryCount(0)
    retryRef.current = 0
    if (retryTimerRef.current) clearTimeout(retryTimerRef.current)

    let destroyed = false
    let hls: import('hls.js').default | null = null

    function scheduleRetry() {
      retryRef.current += 1
      if (destroyed || retryRef.current >= MAX_RETRIES) {
        setStatus('error')
        setErrorMsg('Stream unavailable after retries')
        return
      }
      setRetryCount(retryRef.current)
      retryTimerRef.current = setTimeout(() => {
        if (!destroyed) attach()
      }, RETRY_INTERVAL_MS)
    }

    function attach() {
      if (destroyed) return
      hls?.destroy()
      import('hls.js').then(({ default: Hls }) => {
        if (destroyed) return
        if (!Hls.isSupported()) {
          setStatus('error')
          setErrorMsg('HLS not supported in this browser')
          return
        }

        hls = new Hls({
          liveSyncDurationCount: 4,
          liveMaxLatencyDurationCount: 8,
          enableWorker: true,
        })
        hls.loadSource(src)
        hls.attachMedia(video!)

        hls.on(Hls.Events.MANIFEST_PARSED, () => {
          if (destroyed) return
          setStatus('playing')
          video!.volume = volume / 100
          video!.play().catch(() => {})
        })

        hls.on(Hls.Events.ERROR, (_evt, data) => {
          if (destroyed) return
          if (data.fatal) {
            if (data.type === Hls.ErrorTypes.MEDIA_ERROR) {
              hls?.recoverMediaError()
            } else {
              hls?.destroy()
              hls = null
              scheduleRetry()
            }
          }
        })
      })
    }

    attach()

    // Stall watchdog: if video is "playing" but currentTime hasn't advanced
    // for 4 seconds, seek to the live edge and resume.
    let lastTime = -1
    let stalledFor = 0
    const watchdog = setInterval(() => {
      if (destroyed || !hls || !video) return
      if (video.paused) {
        video.play().catch(() => {})
        stalledFor = 0
        return
      }
      if (video.currentTime === lastTime) {
        stalledFor += 1
        if (stalledFor >= 2) {
          hls.stopLoad()
          hls.startLoad(-1)
          video.play().catch(() => {})
          stalledFor = 0
        }
      } else {
        stalledFor = 0
      }
      lastTime = video.currentTime
    }, 2000)

    return () => {
      destroyed = true
      clearInterval(watchdog)
      if (retryTimerRef.current) clearTimeout(retryTimerRef.current)
      hls?.destroy()
      if (video) video.src = ''
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [src])

  function toggleMute() {
    if (muted) {
      // Unmuting: ensure volume is audible
      if (volume === 0) setVolume(80)
      setMuted(false)
    } else {
      setMuted(true)
    }
  }

  const volumeIcon = muted || volume === 0 ? '🔇' : volume < 50 ? '🔉' : '🔊'

  return (
    <div className="relative overflow-hidden rounded-md bg-black" style={{ aspectRatio: '9/16' }}>
      <video
        ref={videoRef}
        autoPlay
        muted={muted}
        playsInline
        className="h-full w-full object-cover"
      />

      {status === 'connecting' && (
        <div className="absolute inset-0 flex flex-col items-center justify-center gap-2 bg-black/80 text-white">
          <div className="h-5 w-5 animate-spin rounded-full border-2 border-white border-t-transparent" />
          <span className="text-xs">
            {retryCount > 0 ? `Waiting for stream… (retry ${retryCount}/${MAX_RETRIES})` : 'Connecting…'}
          </span>
        </div>
      )}

      {status === 'error' && (
        <div className="absolute inset-0 flex flex-col items-center justify-center gap-1 bg-black/90 p-4 text-center text-xs text-red-400">
          <span className="text-base">⚠</span>
          <span>{errorMsg || 'Stream unavailable'}</span>
        </div>
      )}

      {status === 'playing' && (
        <>
          <div className="absolute bottom-2 right-2 rounded bg-red-600 px-1.5 py-0.5 text-[10px] font-bold text-white">
            LIVE
          </div>

          {/* Volume controls */}
          <div className="absolute bottom-2 left-2 flex items-center gap-1.5 rounded bg-black/60 px-2 py-1">
            <button
              onClick={toggleMute}
              className="text-sm leading-none text-white"
              title={muted ? 'Bật tiếng' : 'Tắt tiếng'}
            >
              {volumeIcon}
            </button>
            <input
              type="range"
              min={0}
              max={100}
              value={muted ? 0 : volume}
              onChange={e => {
                const v = Number(e.target.value)
                setVolume(v)
                if (v > 0 && muted) setMuted(false)
                if (v === 0) setMuted(true)
              }}
              className="h-1 w-20 cursor-pointer accent-white"
            />
            <span className="w-6 text-right text-[10px] text-white/80">
              {muted ? 0 : volume}%
            </span>
          </div>
        </>
      )}
    </div>
  )
}
