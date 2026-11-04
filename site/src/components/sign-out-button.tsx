import { LogOut } from 'lucide-react'
import { useState } from 'react'
import { useNavigate } from 'react-router'
import { GazeButton } from '@/components/gaze-button'
import { useSessionStore } from '@/store/session-store'

/**
 * Sign out in two presses (like the control bar's Quit), so a stray wink
 * does not sign the user out. Eye tracking keeps running afterwards.
 */
export function SignOutButton() {
  const navigate = useNavigate()
  const logout = useSessionStore((s) => s.logout)
  const [confirming, setConfirming] = useState(false)

  const signOut = async () => {
    await logout().catch(() => undefined)
    void navigate('/', { replace: true })
  }

  if (!confirming) {
    return (
      <GazeButton variant="outline" onClick={() => setConfirming(true)}>
        <LogOut aria-hidden />
        Sign out
      </GazeButton>
    )
  }
  return (
    <div className="flex flex-wrap items-center gap-6" role="group" aria-label="Confirm sign out">
      <GazeButton variant="destructive" onClick={() => void signOut()} autoFocus>
        <LogOut aria-hidden />
        Yes, sign out
      </GazeButton>
      <GazeButton variant="outline" onClick={() => setConfirming(false)}>
        Cancel
      </GazeButton>
    </div>
  )
}
