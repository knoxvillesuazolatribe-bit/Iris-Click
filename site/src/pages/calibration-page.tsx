import { CalibrationResultCard } from '@/components/calibration-result-card'
import { CalibrationStage } from '@/components/calibration-stage'
import { CalibrationStartCard } from '@/components/calibration-start-card'
import { useCalibrationFlow } from '@/hooks/use-calibration-flow'
import { useCalibrationSocket } from '@/hooks/use-calibration-socket'
import { useCalibrationSubmit } from '@/hooks/use-calibration-submit'
import { useCameraOptions } from '@/hooks/use-camera-options'
import { useVoiceGuidance } from '@/hooks/use-voice-guidance'
import { useCalibrationStore } from '@/store/calibration-store'

export function CalibrationPage() {
  const state = useCalibrationStore()
  const { form, onSubmit } = useCalibrationSubmit()
  const cameraOptions = useCameraOptions()
  const flow = useCalibrationFlow()
  useCalibrationSocket()
  useVoiceGuidance()

  if (state.phase === 'idle' || state.phase === 'success' || state.phase === 'failed') {
    return (
      <main className="bg-background text-foreground flex min-h-svh items-center justify-center p-6">
        {state.phase === 'idle' ? (
          <CalibrationStartCard
            form={form}
            onSubmit={onSubmit}
            error={state.error}
            cameraOptions={cameraOptions}
          />
        ) : (
          <CalibrationResultCard result={state.result} error={state.error} onRetry={state.reset} />
        )}
      </main>
    )
  }

  return (
    <CalibrationStage
      phase={state.phase}
      points={state.points}
      pointIndex={state.pointIndex}
      isCollecting={state.isCollecting}
      isAccepted={state.isAccepted}
      paused={state.paused}
      restMessage={state.restMessage}
      frame={state.frame}
      error={state.error}
      deepGazeAvailable={state.deepGazeAvailable}
      needsFullscreen={flow.needsFullscreen}
      onPause={flow.pause}
      onResume={flow.resume}
      onCancel={flow.cancel}
    />
  )
}
