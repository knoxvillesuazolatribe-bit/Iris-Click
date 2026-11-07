import { Eye, ShieldCheck, UserRound } from 'lucide-react'
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
        <Eye className="text-primary mx-auto size-16" aria-hidden />
        <h1 className="text-5xl font-bold tracking-tight">Welcome to {appName}</h1>
        <p className="text-muted-foreground text-xl">Look at a button and wink your left eye to choose.</p>
      </header>
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
    </main>
  )
}
