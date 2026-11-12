import type { ReactNode } from 'react'
import { Navigate } from 'react-router'
import { useAccountsMode } from '@/lib/use-signin-mode'

/** A page that only exists with today's name tiles; with accounts on this computer it goes to `to`. */
export function LegacyOnly({ to, children }: { to: string; children: ReactNode }) {
  return useAccountsMode() ? <Navigate to={to} replace /> : <>{children}</>
}
