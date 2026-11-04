import { Crosshair } from 'lucide-react'
import { useNavigate } from 'react-router'
import { GazeButton } from '@/components/gaze-button'
import { SignOutButton } from '@/components/sign-out-button'
import { useSessionStore } from '@/store/session-store'

/** Placeholder Home Suite for a signed-in assistive user (full dashboard: Phase 3). */
export function HomePage() {
  const navigate = useNavigate()
  const user = useSessionStore((s) => s.user)
  return (
    <main className="bg-background text-foreground flex min-h-svh flex-col items-center justify-center gap-10 p-6 text-center">
      <header className="space-y-3">
        <h1 className="text-5xl font-bold">Hello, {user?.full_name}</h1>
        <p className="text-muted-foreground text-xl">
          Your full Home Suite is coming in the next update.
        </p>
      </header>
      <div className="flex flex-wrap justify-center gap-8">
        <GazeButton onClick={() => void navigate('/calibration')}>
          <Crosshair aria-hidden />
          Calibrate again
        </GazeButton>
        <SignOutButton />
      </div>
    </main>
  )
}
