import { Badge } from '@/components/ui/badge'
import { Progress } from '@/components/ui/progress'

interface ProgressIndicatorProps {
  completed: number
  total: number
  faceFound: boolean
  pupilsDetected: boolean
  deepGazeAvailable: boolean
}

export function ProgressIndicator({
  completed,
  total,
  faceFound,
  pupilsDetected,
  deepGazeAvailable,
}: ProgressIndicatorProps) {
  const percent = total > 0 ? Math.round((completed / total) * 100) : 0
  return (
    <div className="flex w-[min(90vw,640px)] flex-col gap-3">
      <div className="flex items-center justify-between text-base">
        <span>
          Dots done: {completed} of {total}
        </span>
        <span className="flex gap-2">
          <Badge variant={faceFound ? 'secondary' : 'destructive'}>
            {faceFound ? 'Face found' : 'No face'}
          </Badge>
          <Badge variant={pupilsDetected ? 'secondary' : 'outline'}>
            {pupilsDetected ? 'Pupils clear' : 'Pupils unclear'}
          </Badge>
          <Badge variant="outline">GazeFollower {deepGazeAvailable ? 'on' : 'off'}</Badge>
        </span>
      </div>
      <Progress value={percent} aria-label="Calibration progress" />
    </div>
  )
}
