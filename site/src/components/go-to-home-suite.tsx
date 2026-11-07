import { House } from 'lucide-react'
import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router'
import { GazeButton } from '@/components/gaze-button'
import { SilentBoundary } from '@/components/silent-boundary'
import { useSessionStore } from '@/store/session-store'

const AUTO_NAVIGATE_S = 5

/**
 * Shown on the calibration result card after a success (hook H2): takes a
 * signed-in assistive user to the Home Suite after a short, cancellable
 * countdown. Renders nothing when nobody is signed in, so the card stays as it was.
 */
export function GoToHomeSuite() {
  return (
    <SilentBoundary>
      <HomeSuiteCountdown />
    </SilentBoundary>
  )
}

function HomeSuiteCountdown() {
  const navigate = useNavigate()
  const status = useSessionStore((s) => s.status)
  const user = useSessionStore((s) => s.user)
  const load = useSessionStore((s) => s.load)
  const [secondsLeft, setSecondsLeft] = useState(AUTO_NAVIGATE_S)
  const [cancelled, setCancelled] = useState(false)
  const signedIn = status === 'signed-in' && user?.role === 'assistive_user'

  useEffect(() => {
    // Calibration may have been opened straight from a URL: ask the server.
    // Only on mount; later changes come from the store itself.
    if (status === 'unknown' || status === 'signed-out') void load()
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (!signedIn || cancelled) return
    if (secondsLeft <= 0) {
      void navigate('/home')
      return
    }
    const timer = window.setTimeout(() => setSecondsLeft((s) => s - 1), 1000)
    return () => window.clearTimeout(timer)
  }, [signedIn, cancelled, secondsLeft, navigate])

  if (!signedIn) return null
  return (
    <div className="border-primary/40 bg-muted/40 space-y-4 rounded-xl border-2 p-4">
      <p className="text-lg font-medium" aria-live="polite">
        {cancelled
          ? 'You can go to your Home Suite whenever you are ready.'
          : `Going to your Home Suite in ${secondsLeft}…`}
      </p>
      <div className="flex flex-wrap gap-6">
        <GazeButton onClick={() => void navigate('/home')}>
          <House aria-hidden />
          Go to Home Suite
        </GazeButton>
        {!cancelled && (
          <GazeButton variant="outline" onClick={() => setCancelled(true)}>
            Stay here
          </GazeButton>
        )}
      </div>
    </div>
  )
}
