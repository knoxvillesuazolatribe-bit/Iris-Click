import { useCallback, useEffect, useRef } from 'react'
import { useFullscreen } from '@/hooks/use-fullscreen'
import { useCalibrationStore } from '@/store/calibration-store'

// Timings carried over from the desktop calibration: both eyes must stay
// registered for a second, but a user is never trapped on that step.
const REGISTRATION_STEADY_MS = 1000
const REGISTRATION_MAX_MS = 12000
const FIRST_DOT_SETTLE_MS = 900
const DOT_SETTLE_MS = 500
const RETRY_REST_MS = 1900
// Long enough to register as confirmation, short enough not to slow 13 dots down.
const ACCEPTED_FLASH_MS = 600

const ACTIVE_PHASES: readonly string[] = ['connecting', 'registering', 'dots', 'fitting']

/** Drives registration, dot timing, retries and pause from the store state. */
export function useCalibrationFlow() {
  const phase = useCalibrationStore((s) => s.phase)
  const registered = useCalibrationStore((s) => s.frame?.registered ?? false)
  const pointIndex = useCalibrationStore((s) => s.pointIndex)
  const isCollecting = useCalibrationStore((s) => s.isCollecting)
  const isAccepted = useCalibrationStore((s) => s.isAccepted)
  const paused = useCalibrationStore((s) => s.paused)
  const restMessage = useCalibrationStore((s) => s.restMessage)
  const finishRegistration = useCalibrationStore((s) => s.finishRegistration)
  const collectCurrentPoint = useCalibrationStore((s) => s.collectCurrentPoint)
  const advancePoint = useCalibrationStore((s) => s.advancePoint)
  const endRest = useCalibrationStore((s) => s.endRest)
  const setPaused = useCalibrationStore((s) => s.setPaused)
  const cancel = useCalibrationStore((s) => s.cancel)
  const { isFullscreen, enter, exit } = useFullscreen()
  const steadySince = useRef<number | null>(null)

  const active = ACTIVE_PHASES.includes(phase)

  useEffect(() => {
    if (phase !== 'registering' || paused) return
    const timer = window.setTimeout(finishRegistration, REGISTRATION_MAX_MS)
    return () => window.clearTimeout(timer)
  }, [phase, paused, finishRegistration])

  useEffect(() => {
    if (phase !== 'registering' || paused || !registered) {
      steadySince.current = null
      return
    }
    steadySince.current ??= performance.now()
    const remaining = REGISTRATION_STEADY_MS - (performance.now() - steadySince.current)
    const timer = window.setTimeout(finishRegistration, Math.max(0, remaining))
    return () => window.clearTimeout(timer)
  }, [phase, paused, registered, finishRegistration])

  useEffect(() => {
    if (phase !== 'dots' || paused || isCollecting || isAccepted || restMessage) return
    const settle = pointIndex === 0 ? FIRST_DOT_SETTLE_MS : DOT_SETTLE_MS
    const timer = window.setTimeout(collectCurrentPoint, settle)
    return () => window.clearTimeout(timer)
  }, [phase, paused, isCollecting, isAccepted, restMessage, pointIndex, collectCurrentPoint])

  useEffect(() => {
    if (!isAccepted || paused) return
    const timer = window.setTimeout(advancePoint, ACCEPTED_FLASH_MS)
    return () => window.clearTimeout(timer)
  }, [isAccepted, paused, advancePoint])

  useEffect(() => {
    if (!restMessage || paused) return
    const timer = window.setTimeout(endRest, RETRY_REST_MS)
    return () => window.clearTimeout(timer)
  }, [restMessage, paused, endRest])

  // Leaving fullscreen (Esc) breaks the viewport-equals-screen assumption.
  useEffect(() => {
    if (active && phase !== 'connecting' && !isFullscreen) setPaused(true)
  }, [active, phase, isFullscreen, setPaused])

  useEffect(() => {
    if (!active) void exit()
  }, [active, exit])

  const resume = useCallback(async () => {
    // Runs from a click or key press, so fullscreen may be requested again.
    if (await enter()) setPaused(false)
  }, [enter, setPaused])

  useEffect(() => {
    if (!active) return
    const onKey = (event: KeyboardEvent) => {
      if (event.key !== ' ' && event.key.toLowerCase() !== 'p') return
      event.preventDefault()
      if (useCalibrationStore.getState().paused) void resume()
      else setPaused(true)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [active, resume, setPaused])

  return {
    pause: () => setPaused(true),
    resume,
    cancel,
    needsFullscreen: active && !isFullscreen,
  }
}
