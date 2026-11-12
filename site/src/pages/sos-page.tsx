import { ArrowLeft, LoaderCircle, MapPin, UsersRound } from 'lucide-react'
import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router'
import { errorMessage } from '@/api/app-client'
import { GazeButton } from '@/components/gaze-button'
import { ServerDown } from '@/components/server-down'
import { SosDwellButton } from '@/components/sos-dwell-button'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { sosService } from '@/services/sos-service'
import type { SosOverview } from '@/validators/sos-validator'
import { AddAddressPrompt } from '@/components/add-address-prompt'

type Load = { state: 'loading' } | { state: 'error'; message: string } | { state: 'ready'; overview: SosOverview }

/** Screen 15: the big SOS button, who will be alerted, and the location shared. */
export function SosPage() {
  const navigate = useNavigate()
  const [load, setLoad] = useState<Load>({ state: 'loading' })
  const [attempt, setAttempt] = useState(0)

  useEffect(() => {
    let current = true
    sosService
      .getOverview()
      .then((overview) => current && setLoad({ state: 'ready', overview }))
      .catch((err) => current && setLoad({ state: 'error', message: errorMessage(err, 'Could not load Emergency SOS.') }))
    return () => {
      current = false
    }
  }, [attempt])

  const header = (
    <header className="top-band flex flex-wrap items-center justify-between gap-6">
      <h1 className="text-destructive text-4xl font-black">Emergency SOS</h1>
      <GazeButton variant="outline" onClick={() => void navigate('/home')}>
        <ArrowLeft aria-hidden />
        Home
      </GazeButton>
    </header>
  )

  if (load.state !== 'ready') {
    return (
      <main className="bg-background text-foreground mx-auto flex min-h-svh max-w-5xl flex-col gap-8 p-6">
        {header}
        {load.state === 'loading' ? (
          <LoaderCircle className="text-muted-foreground mx-auto size-12 animate-spin" aria-label="Loading" />
        ) : (
          <div className="flex justify-center">
            <ServerDown
              message={load.message}
              onRetry={() => {
                setLoad({ state: 'loading' })
                setAttempt((n) => n + 1)
              }}
            />
          </div>
        )}
      </main>
    )
  }

  const { contacts, location_text: location, email_configured: emailReady } = load.overview
  const hasContacts = contacts.length > 0
  const emailContacts = contacts.filter((c) => c.email_address).length

  return (
    <main className="bg-background text-foreground mx-auto flex min-h-svh max-w-5xl flex-col gap-8 p-6">
      {header}

      {!hasContacts ? (
        <Alert variant="destructive" role="alert">
          <AlertTitle className="text-xl">No emergency contacts yet</AlertTitle>
          <AlertDescription className="text-lg">
            SOS cannot alert anyone until a caregiver adds at least one contact.
          </AlertDescription>
        </Alert>
      ) : (
        <>
          {!emailReady && (
            <Alert variant="destructive" role="alert">
              <AlertTitle className="text-xl">Email is not set up on this computer</AlertTitle>
              <AlertDescription className="text-lg">
                If you press SOS now, the alerts will fail. Ask your administrator to add the email (SMTP) details.
              </AlertDescription>
            </Alert>
          )}
          {emailContacts === 0 && (
            <Alert variant="destructive" role="alert">
              <AlertTitle className="text-xl">None of your contacts has an email</AlertTitle>
              <AlertDescription className="text-lg">
                SMS is not set up yet, so add an email to at least one contact.
              </AlertDescription>
            </Alert>
          )}
          <SosDwellButton onActivate={() => void navigate('/sos/confirm')} />
          <p className="text-muted-foreground text-center text-xl">
            Pressing SOS starts a 4-second countdown. You can still cancel.
          </p>
        </>
      )}

      <section aria-labelledby="sos-contacts" className="bg-card rounded-2xl border-2 p-6">
        <h2 id="sos-contacts" className="mb-4 flex items-center gap-3 text-2xl font-bold">
          <UsersRound className="size-8" aria-hidden />
          Who will be alerted
        </h2>
        {hasContacts ? (
          <ul className="space-y-2 text-xl">
            {contacts.map((c) => (
              <li key={c.contact_id}>
                <span className="font-semibold">{c.contact_name}</span>
                {c.relationship && <span className="text-muted-foreground"> ({c.relationship})</span>}
                <span className="text-muted-foreground"> · {c.email_address ?? `${c.contact_number} (SMS not set up)`}</span>
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-muted-foreground text-xl">Nobody yet.</p>
        )}
        <GazeButton variant="outline" className="mt-6" onClick={() => void navigate('/sos/contacts')}>
          <UsersRound aria-hidden />
          {hasContacts ? 'Manage contacts' : 'Set up contacts'}
        </GazeButton>
      </section>

      <section aria-labelledby="sos-location" className="bg-card rounded-2xl border-2 p-6">
        <h2 id="sos-location" className="mb-4 flex items-center gap-3 text-2xl font-bold">
          <MapPin className="size-8" aria-hidden />
          Location shared
        </h2>
        {location ? (
          <p className="text-xl">{location}</p>
        ) : (
          <AddAddressPrompt />
        )}
      </section>
    </main>
  )
}
