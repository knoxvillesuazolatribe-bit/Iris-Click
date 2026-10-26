import { CircleCheck, RotateCcw, TriangleAlert } from 'lucide-react'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import type { CalibrationResult } from '@/validators/calibration-validator'

const SOURCE_LABELS: Record<string, string> = {
  iris_ring_v1: 'Iris landmarks',
  pupil_ellipse_v2: 'Fitted pupils',
  eye_midpoint_v1: 'Eye midpoint',
  eye_midpoint_pupil_v1: 'Eye midpoint (pupils)',
  gazefollower_mgazenet_v1: 'GazeFollower network',
  nose_eye_v1: 'Nose-eye pyramid',
  nose_eye_pupil_v1: 'Nose-eye pyramid (pupils)',
}

const CONTROLS = [
  ['Look', 'moves the cursor (yellow ring)'],
  ['Hold your gaze', 'left click'],
  ['Wink left eye', 'right click'],
  ['Wink right eye', 'go back'],
] as const

interface CalibrationResultCardProps {
  result: CalibrationResult | null
  error: string | null
  onRetry: () => void
}

export function CalibrationResultCard({ result, error, onRetry }: CalibrationResultCardProps) {
  const profile = result?.status === 'success' ? result.profile : null

  if (!profile) {
    return (
      <Card className="w-full max-w-xl">
        <CardHeader>
          <CardTitle className="flex items-center gap-3 text-3xl">
            <TriangleAlert className="text-destructive size-8" aria-hidden />
            Calibration did not finish
          </CardTitle>
        </CardHeader>
        <CardContent>
          <Alert variant="destructive">
            <AlertDescription className="text-base">
              {error ?? result?.message ?? 'Something went wrong.'}
            </AlertDescription>
          </Alert>
        </CardContent>
        <CardFooter>
          <Button size="lg" className="h-14 w-full text-lg" onClick={onRetry} autoFocus>
            <RotateCcw aria-hidden />
            Try again
          </Button>
        </CardFooter>
      </Card>
    )
  }

  const accuracy = Math.round(profile.accuracy_fraction * 100)
  return (
    <Card className="w-full max-w-xl">
      <CardHeader>
        <CardTitle className="flex items-center gap-3 text-3xl" aria-live="polite">
          <CircleCheck className="text-primary size-8" aria-hidden />
          Calibration complete
        </CardTitle>
        <CardDescription className="text-lg">{result?.message}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-5">
        {result?.worker_started ? (
          <Alert>
            <AlertTitle>Eye tracking is running</AlertTitle>
            <AlertDescription>
              Look for the IrisClick eye icon in the system tray. Use it to pause, recalibrate or quit.
            </AlertDescription>
          </Alert>
        ) : (
          <Alert variant="destructive">
            <AlertTitle>Eye tracking did not start</AlertTitle>
            <AlertDescription>The calibration is saved. Start tracking again from the server.</AlertDescription>
          </Alert>
        )}
        <div className="flex flex-wrap gap-2">
          <Badge variant={profile.low_accuracy ? 'destructive' : 'secondary'}>
            Accuracy: about {accuracy}% of the screen
          </Badge>
          <Badge variant="outline">
            Engine: {SOURCE_LABELS[profile.feature_source] ?? profile.feature_source}
          </Badge>
        </div>
        {profile.low_accuracy && (
          <p className="text-muted-foreground text-sm">
            Accuracy is low. Large buttons work best; recalibrate with brighter front light for more precision.
          </p>
        )}
        <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-base">
          {CONTROLS.map(([gesture, action]) => (
            <div key={gesture} className="contents">
              <dt className="font-semibold">{gesture}</dt>
              <dd className="text-muted-foreground">{action}</dd>
            </div>
          ))}
        </dl>
      </CardContent>
      <CardFooter>
        <Button variant="outline" size="lg" className="h-12 w-full" onClick={onRetry}>
          <RotateCcw aria-hidden />
          Calibrate again
        </Button>
      </CardFooter>
    </Card>
  )
}
