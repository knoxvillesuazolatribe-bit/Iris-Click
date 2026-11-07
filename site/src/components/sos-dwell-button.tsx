import { Siren } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { cn } from '@/lib/utils'

const DWELL_MS = 1500
const RING_RADIUS = 46
const RING_LENGTH = 2 * Math.PI * RING_RADIUS

interface SosDwellButtonProps {
  onActivate: () => void
  disabled?: boolean
}

/**
 * The big SOS button. A left wink (click) presses it at once; resting the
 * gaze cursor on it for 1.5 s also presses it, with a ring showing progress.
 * Dwell works on this button only (the worker's own dwell stays off).
 */
export function SosDwellButton({ onActivate, disabled }: SosDwellButtonProps) {
  const [progress, setProgress] = useState(0)
  const frame = useRef<number | null>(null)
  const startedAt = useRef<number | null>(null)
  const fired = useRef(false)

  const stop = () => {
    if (frame.current !== null) cancelAnimationFrame(frame.current)
    frame.current = null
    startedAt.current = null
    setProgress(0)
  }
  useEffect(() => () => {
    if (frame.current !== null) cancelAnimationFrame(frame.current)
  }, [])

  const activate = () => {
    if (fired.current || disabled) return
    fired.current = true
    stop()
    onActivate()
  }

  const tick = (now: number) => {
    startedAt.current ??= now
    const value = Math.min((now - startedAt.current) / DWELL_MS, 1)
    setProgress(value)
    if (value >= 1) {
      activate()
      return
    }
    frame.current = requestAnimationFrame(tick)
  }

  const startDwell = () => {
    if (disabled || fired.current || frame.current !== null) return
    frame.current = requestAnimationFrame(tick)
  }

  return (
    <button
      type="button"
      disabled={disabled}
      onClick={activate}
      onPointerEnter={startDwell}
      onPointerLeave={stop}
      aria-label="SOS. Wink, or keep looking for 1.5 seconds, to ask for help"
      className={cn(
        'bg-destructive relative mx-auto flex size-72 flex-col items-center justify-center rounded-full text-white',
        'shadow-xl outline-none focus-visible:ring-8 focus-visible:ring-red-300 disabled:opacity-50',
        'hover:ring-8 hover:ring-red-300',
      )}
    >
      <svg viewBox="0 0 100 100" className="absolute inset-0 size-full -rotate-90" aria-hidden>
        <circle
          cx="50"
          cy="50"
          r={RING_RADIUS}
          fill="none"
          stroke="white"
          strokeWidth="5"
          strokeLinecap="round"
          strokeDasharray={RING_LENGTH}
          strokeDashoffset={RING_LENGTH * (1 - progress)}
          opacity={progress > 0 ? 1 : 0}
        />
      </svg>
      <Siren className="size-20" aria-hidden />
      <span className="text-6xl font-black tracking-widest">SOS</span>
      <span className="mt-1 text-lg font-semibold">{progress > 0 ? 'Keep looking…' : 'Look here or wink'}</span>
    </button>
  )
}
