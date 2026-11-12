import { LoaderCircle } from 'lucide-react'
import { type ReactNode, useEffect, useState } from 'react'
import { signinMode } from '@/lib/signin-mode'
import type { SigninMode } from '@/validators/accounts-validator'

interface Props {
  /** Today's screen, shown in "legacy" mode (the default) and whenever the mode cannot be read. */
  legacy: ReactNode
  /** Accounts on this computer, shown only in "device_accounts" mode. */
  deviceAccounts: ReactNode
}

/** Shows today's sign-in or the new one, as the server's ASSISTIVE_SIGNIN_MODE says. */
export function SigninModeSwitch({ legacy, deviceAccounts }: Props) {
  const [mode, setMode] = useState<SigninMode | null>(null)

  useEffect(() => {
    let current = true
    void signinMode().then((value) => current && setMode(value))
    return () => {
      current = false
    }
  }, [])

  if (mode === null) {
    return (
      <main className="bg-background flex min-h-svh items-center justify-center">
        <LoaderCircle className="text-muted-foreground size-12 animate-spin" aria-label="Loading" />
      </main>
    )
  }
  return <>{mode === 'device_accounts' ? deviceAccounts : legacy}</>
}
