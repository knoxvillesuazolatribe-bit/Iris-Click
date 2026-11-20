import { LogOut } from 'lucide-react'
import { useState } from 'react'
import { useNavigate } from 'react-router'
import { GazeButton } from '@/components/gaze-button'
import { Button } from '@/components/ui/button'
import { useSessionStore } from '@/store/session-store'
import { signOutOnThisComputer } from '@/lib/account-signout'

/**
 * Sign out in two presses (like the control bar's Quit), so a stray wink
 * does not sign the user out. Eye tracking keeps running afterwards.
 * ``compact``: normal-sized buttons on one row, for the admin header (mouse and keyboard).
 */
export function SignOutButton({ compact = false }: { compact?: boolean }) {
  const navigate = useNavigate()
  const logout = useSessionStore((s) => s.logout)
  const [confirming, setConfirming] = useState(false)

  const signOut = async () => {
    if (await signOutOnThisComputer()) return void navigate('/user/select', { replace: true }) // accounts on this computer
    await logout().catch(() => undefined)
    void navigate('/', { replace: true })
  }

  if (compact) {
    return confirming ? (
      <div className="flex flex-nowrap items-center gap-2" role="group" aria-label="Confirm sign out">
        <Button variant="destructive" onClick={() => void signOut()} autoFocus>
          <LogOut aria-hidden />
          Yes, sign out
        </Button>
        <Button variant="outline" onClick={() => setConfirming(false)}>
          Cancel
        </Button>
      </div>
    ) : (
      <Button variant="outline" onClick={() => setConfirming(true)}>
        <LogOut aria-hidden />
        Sign out
      </Button>
    )
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
