import { ArrowLeft, Camera, Check, LoaderCircle, RotateCcw, ShieldCheck } from 'lucide-react'
import { useCallback, useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router'
import { errorMessage } from '@/api/app-client'
import { GazeButton } from '@/components/gaze-button'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { onlineCalibrationService } from '@/services/online-calibration-service'
import { CALIBRATION_POINTS, dotFinished, dotHasEnough, finishCalibration, MAX_POINT_RETRIES,
  SETTLE_MS, type CalibrationOutcome } from './calibration'
import { gaze, GUIDANCE_TEXT, useGaze } from './engine'
import type { EyeReading } from './features'
import { accuracyPercent, type Vec2 } from './regression'
import { loadTrackerSettings } from './start'

// Frames with an eye this closed are blinks, not gaze (the PC's reading gate).
const MIN_EAR = 0.12

type Step = { kind: 'intro' } | { kind: 'dots'; index: number; attempt: number }
  | { kind: 'result'; outcome: CalibrationOutcome | { ok: false; reason: 'dot_not_clear'; error: null; sampleCount: number } }

const FAILURE_TEXT = {
  dot_not_clear: 'Not enough clear eye images at a calibration dot. Keep your face in view and look at each dot.',
  fit_failed: 'The calibration did not work this time.',
  not_accurate_enough: 'The calibration was not accurate enough. Sit still, keep your head steady and follow each dot with your eyes.',
} as const

/** Collects one dot's eye readings: waits for the eyes to settle, then until enough clean frames. */
function collectDot(cancelled: () => boolean): Promise<Vec2[]> {
  return new Promise((resolve) => {
    const rows: Vec2[] = []
    let start: number | null = null
    const off = gaze.onReading((reading: EyeReading | null, now: number) => {
      start ??= now
      if (cancelled()) {
        off()
        resolve(rows)
        return
      }
      const elapsed = now - start - SETTLE_MS
      if (elapsed < 0) return
      if (reading && Math.min(reading.leftEar, reading.rightEar) >= MIN_EAR) rows.push([reading.ex, reading.ey])
      if (dotFinished(rows, elapsed)) {
        off()
        resolve(rows)
      }
    })
  })
}

/** Online copy: 13-dot eye calibration in the browser (replaces the PC-only notice). */
export function OnlineCalibrationPage() {
  const navigate = useNavigate()
  const { status, error, faceVisible, guidance } = useGaze()
  const [step, setStep] = useState<Step>({ kind: 'intro' })
  const [saveError, setSaveError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)
  const cancelRef = useRef(false)
  const previewRef = useRef<HTMLVideoElement>(null)

  // Camera on (tracking paused) while this page is open.
  useEffect(() => {
    gaze.stopTracking()
    gaze.startCamera().catch(() => undefined)
    return () => {
      cancelRef.current = true
    }
  }, [])

  useEffect(() => {
    const video = previewRef.current
    if (video && gaze.stream && video.srcObject !== gaze.stream) {
      video.srcObject = gaze.stream
      void video.play().catch(() => undefined)
    }
  })

  const run = useCallback(async () => {
    cancelRef.current = false
    const dots: { target: Vec2; rows: Vec2[] }[] = []
    for (let index = 0; index < CALIBRATION_POINTS.length; index++) {
      let rows: Vec2[] = []
      for (let attempt = 0; attempt <= MAX_POINT_RETRIES; attempt++) {
        setStep({ kind: 'dots', index, attempt })
        rows = await collectDot(() => cancelRef.current)
        if (cancelRef.current) return
        if (dotHasEnough(rows)) break
      }
      if (!dotHasEnough(rows)) {
        const sampleCount = dots.reduce((n, d) => n + d.rows.length, 0)
        setStep({ kind: 'result', outcome: { ok: false, reason: 'dot_not_clear', error: null, sampleCount } })
        void onlineCalibrationService.save({ status: 'Failed', reason: 'dot_not_clear', error_fraction: null,
          sample_count: sampleCount }).catch(() => undefined)
        return
      }
      dots.push({ target: CALIBRATION_POINTS[index], rows })
    }
    const outcome = finishCalibration(dots)
    setStep({ kind: 'result', outcome })
    if (!outcome.ok) {
      void onlineCalibrationService.save({ status: 'Failed', reason: outcome.reason, error_fraction: outcome.error,
        sample_count: outcome.sampleCount }).catch(() => undefined)
    }
  }, [])

  const cancel = () => {
    cancelRef.current = true
    setStep({ kind: 'intro' })
  }

  const saveAndStart = async () => {
    if (step.kind !== 'result' || !step.outcome.ok) return
    const { model, error: errorFraction, sampleCount } = step.outcome
    setSaving(true)
    setSaveError(null)
    try {
      await onlineCalibrationService.save({ status: 'Successful', error_fraction: errorFraction, sample_count: sampleCount,
        model, viewport: { w: window.innerWidth, h: window.innerHeight } })
      await gaze.startTracking(model, await loadTrackerSettings())
      void navigate('/home')
    } catch (err) {
      setSaveError(errorMessage(err, 'The calibration could not be saved.'))
    } finally {
      setSaving(false)
    }
  }

  useEffect(() => {
    if (step.kind !== 'dots') return
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && cancel()
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [step.kind])

  if (step.kind === 'dots') {
    const [x, y] = CALIBRATION_POINTS[step.index]
    return (
      <div className="bg-background fixed inset-0 z-[200] cursor-none" data-gaze-ignore>
        <p className="text-muted-foreground absolute top-4 left-1/2 -translate-x-1/2 text-lg">
          Look at the dot · {step.index + 1} of {CALIBRATION_POINTS.length}
          {step.attempt > 0 && ' · again'}
          {!faceVisible && ' · I cannot see your face'}
        </p>
        <button type="button" onClick={cancel} className="text-muted-foreground absolute right-4 bottom-4 cursor-pointer text-sm underline">
          Stop (Esc)
        </button>
        <span key={`${step.index}-${step.attempt}`} aria-hidden
          className="bg-primary/25 absolute size-12 -translate-x-1/2 -translate-y-1/2 animate-pulse rounded-full"
          style={{ left: `${x * 100}%`, top: `${y * 100}%` }}>
          <span className="bg-primary absolute top-1/2 left-1/2 size-3 -translate-x-1/2 -translate-y-1/2 rounded-full" />
        </span>
      </div>
    )
  }

  return (
    <main className="bg-background text-foreground flex min-h-svh flex-col items-center justify-center gap-6 p-6">
      <Card className="w-full max-w-2xl">
        <CardHeader>
          <CardTitle className="text-3xl font-bold">
            {step.kind === 'result' ? (step.outcome.ok ? 'Calibration finished' : 'Calibration did not work') : 'Calibrate eye tracking'}
          </CardTitle>
          {step.kind === 'intro' && (
            <CardDescription className="text-lg">
              13 dots appear one at a time. Keep your head still and look at each dot until it moves. It takes about 30 seconds.
            </CardDescription>
          )}
        </CardHeader>
        <CardContent className="space-y-5">
          {step.kind === 'intro' && (
            <>
              <div className="bg-muted relative aspect-video w-full overflow-hidden rounded-xl">
                <video ref={previewRef} muted playsInline className="size-full -scale-x-100 object-cover" />
                {status === 'starting' && (
                  <p className="absolute inset-0 flex items-center justify-center gap-2 text-lg">
                    <LoaderCircle className="animate-spin" aria-hidden /> Starting the camera…
                  </p>
                )}
              </div>
              {status === 'error' && error && (
                <Alert variant="destructive" role="alert"><AlertDescription className="text-base">{error}</AlertDescription></Alert>
              )}
              {status === 'camera' && (
                <p role="status" className={`text-lg ${faceVisible && !guidance ? 'text-green-700' : 'text-destructive'}`}>
                  {guidance ? GUIDANCE_TEXT[guidance] : faceVisible ? 'Your face is in view. Ready.' : 'Looking for your face…'}
                </p>
              )}
              <p className="text-muted-foreground flex items-start gap-2 text-sm">
                <ShieldCheck className="mt-0.5 size-4 shrink-0" aria-hidden />
                The camera picture stays on this device; only the finished calibration numbers are saved.
                Eye tracking here works inside this website only.
              </p>
              <div className="flex flex-wrap gap-4">
                {status === 'error' ? (
                  <GazeButton onClick={() => void gaze.startCamera().catch(() => undefined)}>
                    <Camera aria-hidden /> Try the camera again
                  </GazeButton>
                ) : (
                  <GazeButton disabled={status !== 'camera' || !faceVisible} onClick={() => void run()}>
                    <Check aria-hidden /> Start calibration
                  </GazeButton>
                )}
                <GazeButton variant="outline" onClick={() => void navigate('/home')}>
                  <ArrowLeft aria-hidden /> Back to Home
                </GazeButton>
              </div>
            </>
          )}

          {step.kind === 'result' && step.outcome.ok && (
            <>
              <p className="text-2xl">Accuracy: <strong>{accuracyPercent(step.outcome.error).toFixed(2)}%</strong></p>
              {step.outcome.lowAccuracy && (
                <p className="text-muted-foreground text-lg">
                  The aim is rough: large buttons will work. For better aim, sit still and calibrate again.
                </p>
              )}
              {saveError && (
                <Alert variant="destructive" role="alert"><AlertDescription className="text-base">{saveError}</AlertDescription></Alert>
              )}
              <div className="flex flex-wrap gap-4">
                <GazeButton disabled={saving} onClick={() => void saveAndStart()}>
                  {saving ? <LoaderCircle className="animate-spin" aria-hidden /> : <Check aria-hidden />}
                  Save and start eye tracking
                </GazeButton>
                <GazeButton variant="outline" disabled={saving} onClick={() => void run()}>
                  <RotateCcw aria-hidden /> Calibrate again
                </GazeButton>
              </div>
            </>
          )}

          {step.kind === 'result' && !step.outcome.ok && (
            <>
              <Alert variant="destructive" role="alert">
                <AlertDescription className="text-base">
                  {FAILURE_TEXT[step.outcome.reason]}
                  {step.outcome.error !== null && ` Accuracy ${accuracyPercent(step.outcome.error).toFixed(2)}%.`}
                </AlertDescription>
              </Alert>
              <div className="flex flex-wrap gap-4">
                <GazeButton onClick={() => void run()}><RotateCcw aria-hidden /> Try again</GazeButton>
                <GazeButton variant="outline" onClick={() => void navigate('/home')}><ArrowLeft aria-hidden /> Back to Home</GazeButton>
              </div>
            </>
          )}
        </CardContent>
      </Card>
    </main>
  )
}
