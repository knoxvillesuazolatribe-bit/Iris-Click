import { Maximize, Pause, Play, X } from 'lucide-react'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { CalibrationTarget } from '@/components/calibration-target'
import { GazePreview } from '@/components/gaze-preview'
import { ProgressIndicator } from '@/components/progress-indicator'
import { cn } from '@/lib/utils'
import type { CalibrationPhase } from '@/store/calibration-store'
import type { CalibrationPoint, FrameStatus } from '@/validators/calibration-validator'

interface CalibrationStageProps {
  phase: CalibrationPhase
  points: CalibrationPoint[]
  pointIndex: number
  isCollecting: boolean
  isAccepted: boolean
  paused: boolean
  restMessage: string | null
  frame: FrameStatus | null
  error: string | null
  deepGazeAvailable: boolean
  needsFullscreen: boolean
  onPause: () => void
  onResume: () => void
  onCancel: () => void
}

function headline({ phase, paused, restMessage, isCollecting, isAccepted, pointIndex, points }: CalibrationStageProps) {
  if (paused) return ['Calibration paused', 'Take your time. Choose Resume when you are comfortable. No progress is lost.']
  if (phase === 'connecting') return ['Starting the camera…', 'This takes a few seconds.']
  if (phase === 'registering')
    return ['Eye registration', 'Sit comfortably and look at the centre of the screen. Calibration starts when both eyes are registered.']
  if (phase === 'fitting') return ['Checking your calibration…', 'Please wait a moment.']
  if (restMessage) return ['Rest for a moment', restMessage]
  const step = `${Math.min(pointIndex + 1, points.length)}/${points.length}`
  if (isAccepted) return [`Got it (${step})`, 'Get ready for the next dot.']
  return isCollecting
    ? [`Hold your gaze gently (${step})`, 'Only move your eyes. Blink normally; unclear frames are ignored.']
    : [`Look at the dot (${step})`, 'Only move your eyes. Press Space for a rest.']
}

export function CalibrationStage(props: CalibrationStageProps) {
  const { phase, points, pointIndex, isCollecting, isAccepted, paused, restMessage, frame, error } = props
  const [title, guide] = headline(props)
  const point = phase === 'dots' ? points[pointIndex] : undefined
  const advice = frame?.guidance ?? (frame && !frame.eyes_open ? 'Waiting for both eyes to open.' : null)
  // Edge dots sit 4% from the screen border, under where the text and buttons
  // would be; while a dot shows, keep everything on the opposite edge.
  const hudEdge = point && !paused ? (point.y < 0.5 ? 'bottom' : 'top') : null

  const heading = (
    <div className="flex flex-col items-center gap-2 text-center">
      <h1 className="text-3xl font-bold" aria-live="polite">{title}</h1>
      <p className="text-muted-foreground max-w-3xl text-lg">{guide}</p>
    </div>
  )

  const controls = (
    <div className="flex gap-3">
      {paused ? (
        <Button size="lg" className="h-12 text-base" onClick={props.onResume}>
          {props.needsFullscreen ? <Maximize aria-hidden /> : <Play aria-hidden />}
          {props.needsFullscreen ? 'Resume in full screen' : 'Resume'}
        </Button>
      ) : (
        <Button size="lg" variant="secondary" className="h-12 text-base" onClick={props.onPause}>
          <Pause aria-hidden />
          Pause for a rest
        </Button>
      )}
      <Button size="lg" variant="outline" className="h-12 text-base" onClick={props.onCancel}>
        <X aria-hidden />
        Cancel
      </Button>
    </div>
  )

  const status = (
    <>
      {(error || advice) && (
        <Alert variant={error ? 'destructive' : 'default'} className="w-[min(90vw,640px)]">
          <AlertDescription className="text-base">{error ?? advice}</AlertDescription>
        </Alert>
      )}
      <ProgressIndicator
        completed={Math.min(pointIndex + (isAccepted ? 1 : 0), points.length)}
        total={points.length || 13}
        faceFound={frame?.face_found ?? false}
        pupilsDetected={frame?.pupils_detected ?? false}
        deepGazeAvailable={props.deepGazeAvailable}
      />
    </>
  )

  return (
    <div className="dark bg-background text-foreground fixed inset-0 overflow-hidden">
      {hudEdge ? (
        <div
          className={cn(
            'absolute inset-x-0 flex flex-col items-center gap-3 px-6',
            hudEdge === 'top' ? 'top-0 pt-6' : 'bottom-0 pb-6',
          )}
        >
          {heading}
          {controls}
          {status}
        </div>
      ) : (
        <>
          <header className="absolute inset-x-0 top-0 px-6 pt-6">{heading}</header>
          <div className="absolute top-6 right-6">{controls}</div>
          <footer className="absolute inset-x-0 bottom-0 flex flex-col items-center gap-3 px-6 pb-6">
            {status}
          </footer>
        </>
      )}

      {phase === 'registering' && !paused && (
        <div className="absolute inset-0 flex items-center justify-center">
          <GazePreview eyeLine={frame?.eye_line ?? null} />
        </div>
      )}

      {point && !paused && (
        <CalibrationTarget
          x={point.x}
          y={point.y}
          collecting={isCollecting}
          accepted={isAccepted}
          dimmed={restMessage !== null}
        />
      )}
    </div>
  )
}
