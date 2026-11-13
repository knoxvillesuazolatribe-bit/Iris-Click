import { Hand } from 'lucide-react'
import { type ReactNode, useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router'
import { GazeButton } from '@/components/gaze-button'
import { signOutOnThisComputer } from '@/lib/account-signout'
import { thisComputerId } from '@/lib/device'
import { signinMode } from '@/lib/signin-mode'
import { accountsService } from '@/services/accounts-service'
import { useSessionStore } from '@/store/session-store'

const WARNING_S = 60
const ACTIVITY = ['mousemove', 'pointerdown', 'keydown', 'wheel', 'touchstart'] as const

/**
 * Shared computers only (file 07, build step 10, screen S1): after the admin's idle time
 * with no movement (the eye-tracking cursor counts), ask "Are you still here?" for 60
 * seconds, then sign out so the next person cannot use the account. Does nothing in
 * legacy mode, on a personal computer, or when nobody is signed in.
 */
export function IdleSignOut({ children }: { children: ReactNode }) {
  const navigate = useNavigate()
  const userId = useSessionStore((s) => (s.user?.role === 'assistive_user' ? s.user.user_id : null))
  const [idleMs, setIdleMs] = useState<number | null>(null)
  const [countdown, setCountdown] = useState<number | null>(null)
  const lastActivity = useRef(Date.now())

  useEffect(() => {
    setIdleMs(null)
    setCountdown(null)
    if (userId === null) return
    let current = true
    void (async () => {
      if ((await signinMode()) !== 'device_accounts') return
      const deviceId = await thisComputerId()
      if (!deviceId) return
      try {
        const computer = await accountsService.thisComputer(deviceId)
        if (current && computer.is_shared) setIdleMs(computer.idle_minutes * 60_000)
      } catch {
        // Not known: behave like a personal computer.
      }
    })()
    return () => {
      current = false
    }
  }, [userId])

  useEffect(() => {
    if (idleMs === null) return
    lastActivity.current = Date.now()
    const seen = () => {
      lastActivity.current = Date.now()
    }
    for (const name of ACTIVITY) window.addEventListener(name, seen, { passive: true })
    const timer = window.setInterval(() => {
      setCountdown((left) => {
        if (left === null) return Date.now() - lastActivity.current >= idleMs ? WARNING_S : null
        return left - 1
      })
    }, 1000)
    return () => {
      for (const name of ACTIVITY) window.removeEventListener(name, seen)
      window.clearInterval(timer)
    }
  }, [idleMs])

  useEffect(() => {
    if (countdown === null || countdown > 0) return
    setCountdown(null)
    setIdleMs(null)
    void signOutOnThisComputer().then(() => navigate('/user/select', { replace: true }))
  }, [countdown, navigate])

  const stillHere = () => {
    lastActivity.current = Date.now()
    setCountdown(null)
  }

  return (
    <>
      {children}
      {countdown !== null && countdown > 0 && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-6">
          <div role="alertdialog" aria-modal="true" aria-labelledby="idle-title"
            className="bg-card text-card-foreground w-full max-w-2xl space-y-8 rounded-2xl border p-10 text-center shadow-xl">
            <h2 id="idle-title" className="text-4xl font-bold">Are you still here?</h2>
            <p className="text-muted-foreground text-2xl" aria-live="polite">
              Signing out in <span className="text-foreground font-bold tabular-nums">{countdown}</span>
            </p>
            <GazeButton autoFocus className="min-h-28 w-full text-3xl" onClick={stillHere}>
              <Hand aria-hidden className="size-8" />
              I'm here
            </GazeButton>
          </div>
        </div>
      )}
    </>
  )
}
