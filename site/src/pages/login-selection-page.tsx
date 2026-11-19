import { ShieldCheck, UserRound } from 'lucide-react'
import { useNavigate } from 'react-router'
import { GazeButton } from '@/components/gaze-button'
import { useAppName } from '@/lib/use-app-name'

/** Screen 1: choose Assistive User or Administrator. */
export function LoginSelectionPage() {
  const navigate = useNavigate()
  const appName = useAppName()
  return (
    <main className="bg-background text-foreground flex min-h-svh flex-col items-center justify-center gap-12 p-6">
      <header className="space-y-3 text-center">
        <img src="/irisclick-logo.png" alt="" className="mx-auto h-28 w-auto" />
        <h1 className="text-5xl font-bold tracking-tight">Welcome to {appName}</h1>
        <p className="text-muted-foreground text-xl">Choose who is signing in.</p>
      </header>
      <div className="flex flex-col items-center gap-7">
        <nav className="flex flex-wrap items-stretch justify-center gap-10" aria-label="Sign in as">
          <GazeButton className="min-h-40 min-w-72 flex-col text-3xl" onClick={() => void navigate('/user/select')}>
            <UserRound className="size-12" aria-hidden />
            Assistive User
          </GazeButton>
          <GazeButton
            variant="outline"
            className="min-h-40 min-w-72 flex-col text-3xl"
            onClick={() => void navigate('/admin/login')}
          >
            <ShieldCheck className="size-12" aria-hidden />
            Administrator
          </GazeButton>
        </nav>
        {/* Help footer (adviser request) */}
        <p className="max-w-xl text-center text-lg leading-relaxed text-slate-700">
          <strong className="font-semibold">Need help?</strong> Ask a Persons with Disability Affairs Office (PDAO)
          staff member or someone you trust to assist you, or email{' '}
          <a
            href="mailto:irisclick@gmail.com"
            className="text-primary focus-visible:ring-primary rounded-sm font-medium underline underline-offset-4 hover:opacity-80 focus-visible:ring-2 focus-visible:outline-none"
          >
            irisclick@gmail.com
          </a>{' '}
          for support.
        </p>
      </div>
    </main>
  )
}
