import { ArrowLeft, LoaderCircle } from 'lucide-react'
import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router'
import { errorMessage } from '@/api/app-client'
import { ContactsManager } from '@/components/contacts-manager'
import { GazeButton } from '@/components/gaze-button'
import { ServerDown } from '@/components/server-down'
import { sosService } from '@/services/sos-service'
import type { SosContact } from '@/validators/sos-validator'

type Load = { state: 'loading' } | { state: 'error'; message: string } | { state: 'ready'; contacts: SosContact[] }

/** Screen 15a: emergency contacts, usually filled in by a caregiver. */
export function SosContactsPage() {
  const navigate = useNavigate()
  const [load, setLoad] = useState<Load>({ state: 'loading' })
  const [attempt, setAttempt] = useState(0)

  useEffect(() => {
    let current = true
    sosService
      .getOverview()
      .then((o) => current && setLoad({ state: 'ready', contacts: o.contacts }))
      .catch((err) => current && setLoad({ state: 'error', message: errorMessage(err, 'Could not load contacts.') }))
    return () => {
      current = false
    }
  }, [attempt])

  const reload = () => setAttempt((n) => n + 1)

  return (
    <main className="bg-background text-foreground mx-auto flex min-h-svh max-w-5xl flex-col gap-8 p-6">
      <header className="flex flex-wrap items-center justify-between gap-6">
        <div>
          <h1 className="text-4xl font-bold">Emergency contacts</h1>
          <p className="text-muted-foreground mt-2 text-xl">A caregiver can fill this in with a keyboard.</p>
        </div>
        <GazeButton variant="outline" onClick={() => void navigate('/sos')}>
          <ArrowLeft aria-hidden />
          Back to SOS
        </GazeButton>
      </header>

      {load.state === 'loading' && <LoaderCircle className="text-muted-foreground mx-auto size-12 animate-spin" aria-label="Loading" />}
      {load.state === 'error' && (
        <div className="flex justify-center">
          <ServerDown message={load.message} onRetry={() => { setLoad({ state: 'loading' }); reload() }} />
        </div>
      )}
      {load.state === 'ready' && (
        <ContactsManager
          contacts={load.contacts}
          onAdd={sosService.addContact}
          onUpdate={sosService.updateContact}
          onDelete={sosService.deleteContact}
          onChanged={reload}
        />
      )}
    </main>
  )
}
