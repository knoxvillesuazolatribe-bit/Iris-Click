import { ArrowRight, ShieldCheck, UserRound } from 'lucide-react'
import { useEffect } from 'react'
import { useNavigate } from 'react-router'
import { GazeButton } from '@/components/gaze-button'
import { SignOutButton } from '@/components/sign-out-button'
import { useSessionStore } from '@/store/session-store'

/**
 * Welcome page: when someone is still signed in (Back only shows this page; a
 * session lasts until Sign out or it expires), say who, and offer Continue or
 * Sign out, so the next person on a shared PC is not taken into their account.
 */
export function SignedInNote() {
  const navigate = useNavigate()
  const status = useSessionStore((s) => s.status)
  const user = useSessionStore((s) => s.user)
  const load = useSessionStore((s) => s.load)

  useEffect(() => {
    if (status === 'unknown') void load()
  }, [status, load])

  if (status !== 'signed-in' || !user) return null
  const admin = user.role === 'admin'
  const Icon = admin ? ShieldCheck : UserRound
  return (
    <section aria-label="Signed in" role="status"
      className="bg-card text-card-foreground flex w-full max-w-3xl flex-col items-center gap-5 rounded-2xl border p-6 text-center shadow-sm">
      <p className="flex items-center gap-3 text-2xl">
        <Icon className="text-primary size-8" aria-hidden />
        <span>Signed in as <strong>{user.full_name}</strong>{admin ? ' (Administrator)' : ''}</span>
      </p>
      <div className="flex flex-wrap items-center justify-center gap-6">
        <GazeButton onClick={() => void navigate(admin ? '/admin' : '/home')}>
          <ArrowRight aria-hidden />
          Continue
        </GazeButton>
        <SignOutButton />
      </div>
    </section>
  )
}
