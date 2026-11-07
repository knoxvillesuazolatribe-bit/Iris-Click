import { Crosshair, Pause, Play, Power } from 'lucide-react'
import { useEffect } from 'react'
import { useNavigate } from 'react-router'
import { GazeButton } from '@/components/gaze-button'
import { TwoPressButton } from '@/components/two-press-button'
import { useSessionStore } from '@/store/session-store'
import { gaze, GUIDANCE_TEXT, useGaze } from './engine'

const POINTER = 'oklch(0.86 0.18 95)' // the PC's yellow pointer

/**
 * Online copy: the gaze pointer and the small control bar, shown while eye
 * tracking runs in this browser. Stops the camera when the user signs out.
 */
export function GazeLayer() {
  const snap = useGaze()
  const user = useSessionStore((s) => s.user)
  const status = useSessionStore((s) => s.status)

  useEffect(() => {
    if (status !== 'loading' && status !== 'unknown' && user?.role !== 'assistive_user') gaze.stop()
  }, [user, status])

  if (snap.status !== 'tracking' && snap.status !== 'paused') return null
  return (
    <>
      <ControlBar />
      {snap.status === 'tracking' && snap.target && (
        <div aria-hidden data-gaze-ignore
          className="pointer-events-none fixed z-[90] rounded-xl ring-4 ring-amber-400 transition-all duration-75"
          style={{ left: snap.target.left - 4, top: snap.target.top - 4,
            width: snap.target.width + 8, height: snap.target.height + 8 }} />
      )}
      {snap.status === 'tracking' && snap.pointer && <Pointer />}
    </>
  )
}

function Pointer() {
  const { pointer, dwell, closing, flash } = useGaze()
  if (!pointer) return null
  const r = 22
  const circumference = 2 * Math.PI * r
  return (
    <svg aria-hidden data-gaze-ignore width="64" height="64" viewBox="-32 -32 64 64"
      className="pointer-events-none fixed z-[100]"
      style={{ left: pointer.x - 32, top: pointer.y - 32, opacity: closing ? 0.6 : 1,
        transform: flash ? 'scale(1.3)' : undefined, transition: 'transform 120ms' }}>
      {/* The "V" pyramid; its tip is the pointer. */}
      <path d="M -14 -22 L 0 0 L 14 -22" fill="none" stroke="black" strokeWidth="7" strokeLinejoin="round" strokeLinecap="round" />
      <path d="M -14 -22 L 0 0 L 14 -22" fill="none" stroke={POINTER} strokeWidth="4" strokeLinejoin="round" strokeLinecap="round" />
      <circle r="3.5" fill={POINTER} stroke="black" strokeWidth="1.5" />
      {dwell > 0 && (
        <circle r={r} fill="none" stroke={POINTER} strokeWidth="4" strokeDasharray={circumference}
          strokeDashoffset={circumference * (1 - dwell)} transform="rotate(-90)" />
      )}
    </svg>
  )
}

function ControlBar() {
  const navigate = useNavigate()
  const { status, guidance, faceVisible } = useGaze()
  const paused = status === 'paused'
  const text = guidance ? GUIDANCE_TEXT[guidance] : paused ? 'Eye tracking is paused.'
    : faceVisible ? 'Eye tracking is on. Look at a button and wink your left eye.' : 'Looking for your face…'
  return (
    <div data-gaze-bar role="region" aria-label="Eye tracking controls"
      className="bg-card/95 text-card-foreground fixed top-10 left-1/2 z-[80] flex max-w-[calc(100vw-2rem)] -translate-x-1/2 flex-wrap items-center justify-center gap-2 rounded-2xl border p-2 shadow-lg">
      <p role="status" className={`max-w-xs px-2 text-sm font-medium ${guidance ? 'text-destructive' : ''}`}>{text}</p>
      <GazeButton variant="outline" className="min-h-14 px-4 text-base" onClick={() => (paused ? gaze.resume() : gaze.pause())}>
        {paused ? <Play aria-hidden /> : <Pause aria-hidden />}
        {paused ? 'Resume' : 'Pause'}
      </GazeButton>
      <GazeButton variant="outline" className="min-h-14 px-4 text-base" onClick={() => void navigate('/calibration')}>
        <Crosshair aria-hidden />
        Recalibrate
      </GazeButton>
      <TwoPressButton icon={Power} label="Stop" confirmLabel="Press again to stop" className="min-h-14 px-4 text-base"
        onConfirm={() => gaze.stop()} />
    </div>
  )
}
