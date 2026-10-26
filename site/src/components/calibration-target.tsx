import { Check } from 'lucide-react'
import { cn } from '@/lib/utils'

interface CalibrationTargetProps {
  x: number
  y: number
  collecting: boolean
  accepted: boolean
  dimmed: boolean
}

/** Custom (no shadcn equivalent): the fullscreen fixation dot at viewport fractions x, y. */
export function CalibrationTarget({ x, y, collecting, accepted, dimmed }: CalibrationTargetProps) {
  return (
    <span
      aria-hidden
      className={cn(
        'border-background absolute -translate-x-1/2 -translate-y-1/2 rounded-full border-4 transition-colors duration-200',
        'size-[clamp(28px,4.2vh,96px)]',
        accepted
          ? 'bg-success ring-success/40 ring-8'
          : collecting
            ? 'bg-primary ring-ring/60 animate-pulse ring-8'
            : 'bg-primary/80',
        dimmed && 'opacity-30',
      )}
      style={{ left: `${x * 100}%`, top: `${y * 100}%` }}
    >
      {accepted ? (
        <Check
          strokeWidth={4}
          className="text-background absolute top-1/2 left-1/2 size-3/5 -translate-x-1/2 -translate-y-1/2"
        />
      ) : (
        <span className="bg-background absolute top-1/2 left-1/2 size-1/4 -translate-x-1/2 -translate-y-1/2 rounded-full" />
      )}
    </span>
  )
}
