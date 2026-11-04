import { LoaderCircle } from 'lucide-react'
import { useEffect, type ReactNode } from 'react'
import { Navigate } from 'react-router'
import { SERVER_DOWN_MESSAGE } from '@/api/app-client'
import { ServerDown } from '@/components/server-down'
import { useSessionStore } from '@/store/session-store'
import type { SessionUser } from '@/validators/auth-validator'

interface RequireRoleProps {
  role: SessionUser['role']
  children: ReactNode
}

/** Shows ``children`` only to a signed-in user of ``role``; others go back to sign-in. */
export function RequireRole({ role, children }: RequireRoleProps) {
  const status = useSessionStore((s) => s.status)
  const user = useSessionStore((s) => s.user)
  const load = useSessionStore((s) => s.load)

  useEffect(() => {
    if (status === 'unknown') void load()
  }, [status, load])

  if (status === 'unknown' || status === 'loading') {
    return (
      <main className="flex min-h-svh items-center justify-center" aria-busy>
        <LoaderCircle className="text-muted-foreground size-12 animate-spin" aria-label="Loading" />
      </main>
    )
  }
  if (status === 'offline') {
    return (
      <main className="flex min-h-svh items-center justify-center p-6">
        <ServerDown message={SERVER_DOWN_MESSAGE} onRetry={() => void load()} />
      </main>
    )
  }
  if (user?.role !== role) {
    return <Navigate to={role === 'admin' ? '/admin/login' : '/'} replace />
  }
  return children
}
