import { thisComputerId } from '@/lib/device'
import { signinMode } from '@/lib/signin-mode'
import { accountsService } from '@/services/accounts-service'
import { useSessionStore } from '@/store/session-store'

/**
 * Sign out for accounts on this computer (file 07, build step 9). Ends the session and
 * makes this computer ask for the PIN next time ("Remember me" is turned off here).
 * Returns false, doing nothing, in legacy mode or for an administrator, so the caller
 * signs out exactly as before.
 */
export async function signOutOnThisComputer(): Promise<boolean> {
  if (useSessionStore.getState().user?.role !== 'assistive_user') return false
  if ((await signinMode()) !== 'device_accounts') return false
  try {
    await accountsService.signOut(await thisComputerId())
  } catch {
    // Signed out on this page even if the server was unreachable, as today's sign-out does.
  }
  useSessionStore.setState({ status: 'signed-out', user: null })
  return true
}
