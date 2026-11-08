import { Monitor, RefreshCw } from 'lucide-react'
import { GazeButton } from '@/components/gaze-button'

/** Website name screen with the computer lock on: this computer has no approved names yet. */
export function ComputerNotApproved({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <div className="flex w-full max-w-2xl flex-col items-center gap-6 text-center">
      <Monitor className="text-primary size-16" aria-hidden />
      <p className="text-2xl">{message}</p>
      <p className="text-muted-foreground text-lg">
        A helper approves this computer once with a link from the PDAO office. After that, just pick your name.
      </p>
      <GazeButton variant="outline" onClick={onRetry}>
        <RefreshCw aria-hidden /> Try again
      </GazeButton>
    </div>
  )
}
