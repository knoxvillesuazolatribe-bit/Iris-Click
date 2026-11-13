import { useEffect, useState } from 'react'
import { signinMode } from '@/lib/signin-mode'

/**
 * True when the server uses accounts on this computer (file 07). Admin pages use it to
 * hide what people now do themselves (plan section 3, H1-H11). Until the answer arrives,
 * and whenever anything goes wrong, it is false, so the pages look exactly as before.
 */
export function useAccountsMode(): boolean {
  const [on, setOn] = useState(false)
  useEffect(() => {
    let alive = true
    void signinMode().then((mode) => {
      if (alive) setOn(mode === 'device_accounts')
    })
    return () => {
      alive = false
    }
  }, [])
  return on
}
