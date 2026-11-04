import { Crosshair, Eye, LoaderCircle, Mic, Settings, Siren } from 'lucide-react'
import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router'
import { errorMessage } from '@/api/app-client'
import { GazeButton } from '@/components/gaze-button'
import { GestureGuide } from '@/components/gesture-guide'
import { HomeCard } from '@/components/home-card'
import { ServerDown } from '@/components/server-down'
import { SignOutButton } from '@/components/sign-out-button'
import { homeService } from '@/services/home-service'
import { useSessionStore } from '@/store/session-store'
import type { Home } from '@/validators/home-validator'

type Load = { state: 'loading' } | { state: 'error'; message: string } | { state: 'ready'; home: Home }

const LATER = 'Coming in a later update.'

/** Screen 5: the Home Suite for a signed-in assistive user. */
export function HomePage() {
  const navigate = useNavigate()
  const user = useSessionStore((s) => s.user)
  const [load, setLoad] = useState<Load>({ state: 'loading' })
  const [attempt, setAttempt] = useState(0)

  useEffect(() => {
    let current = true
    homeService
      .getHome()
      .then((home) => current && setLoad({ state: 'ready', home }))
      .catch((err) => current && setLoad({ state: 'error', message: errorMessage(err, 'Could not load your Home Suite.') }))
    return () => {
      current = false
    }
  }, [attempt])

  const retry = () => {
    setLoad({ state: 'loading' })
    setAttempt((n) => n + 1)
  }

  return (
    <main className="bg-background text-foreground mx-auto flex min-h-svh max-w-6xl flex-col gap-10 p-6">
      <header className="flex flex-wrap items-center justify-between gap-6">
        <div>
          <h1 className="text-5xl font-bold">Hello, {user?.full_name}</h1>
          <p className="text-muted-foreground mt-2 text-xl">Look at a card and wink your left eye to open it.</p>
        </div>
        <SignOutButton />
      </header>

      <nav aria-label="Home Suite" className="grid gap-8 md:grid-cols-2">
        <HomeCard
          icon={Eye}
          title="Gaze Tracking"
          description="Start or stop eye tracking and see how it is working."
          onSelect={() => void navigate('/tracking')}
        />
        <HomeCard
          icon={Siren}
          title="Emergency SOS"
          description="Ask for help."
          unavailable="Not set up yet. It cannot send help."
          emergency
          onSelect={() => undefined}
        />
        <HomeCard
          icon={Mic}
          title="Voice Communication"
          description="Type or pick a phrase to speak it aloud, or turn speech into text."
          onSelect={() => void navigate('/voice')}
        />
        <HomeCard
          icon={Settings}
          title="Accessibility Settings"
          description="Dwell time, blink sensitivity and voice volume."
          unavailable={LATER}
          onSelect={() => undefined}
        />
      </nav>

      {load.state === 'loading' && (
        <LoaderCircle className="text-muted-foreground mx-auto size-12 animate-spin" aria-label="Loading gestures" />
      )}
      {load.state === 'error' && (
        <div className="flex justify-center">
          <ServerDown message={load.message} onRetry={retry} />
        </div>
      )}
      {load.state === 'ready' && <GestureGuide gestures={load.home.gestures} />}

      <footer className="flex flex-wrap gap-8">
        <GazeButton variant="outline" onClick={() => void navigate('/calibration')}>
          <Crosshair aria-hidden />
          Calibrate again
        </GazeButton>
      </footer>
    </main>
  )
}
