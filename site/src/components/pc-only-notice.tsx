import { House, Monitor } from 'lucide-react'
import { useNavigate } from 'react-router'
import { GazeButton } from '@/components/gaze-button'

/** Online copy: shown instead of the calibration page, which needs the PC's camera. */
export function PcOnlyNotice() {
  const navigate = useNavigate()
  return (
    <main className="bg-background text-foreground flex min-h-svh flex-col items-center justify-center gap-8 p-6 text-center">
      <Monitor className="text-primary size-16" aria-hidden />
      <h1 className="max-w-2xl text-4xl font-bold">Calibration and eye tracking only work on the IrisClick PC</h1>
      <p className="text-muted-foreground max-w-xl text-xl">
        This is the online copy. Voice Communication, SOS and Settings still work here.
      </p>
      <GazeButton onClick={() => void navigate('/home')} autoFocus>
        <House aria-hidden />
        Go to Home
      </GazeButton>
    </main>
  )
}
