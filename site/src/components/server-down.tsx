import { RefreshCw } from 'lucide-react'
import { GazeButton } from '@/components/gaze-button'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'

interface ServerDownProps {
  message: string
  onRetry: () => void
}

export function ServerDown({ message, onRetry }: ServerDownProps) {
  return (
    <div className="flex w-full max-w-2xl flex-col items-center gap-6">
      <Alert variant="destructive" role="alert">
        <AlertTitle className="text-lg">Something is not working</AlertTitle>
        <AlertDescription className="text-base">{message}</AlertDescription>
      </Alert>
      <GazeButton onClick={onRetry} autoFocus>
        <RefreshCw aria-hidden />
        Try again
      </GazeButton>
    </div>
  )
}
