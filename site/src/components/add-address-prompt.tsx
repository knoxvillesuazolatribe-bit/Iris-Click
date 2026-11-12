import { MapPin } from 'lucide-react'
import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router'
import { GazeButton } from '@/components/gaze-button'
import { signinMode } from '@/lib/signin-mode'

const LEGACY_TEXT = 'No address on file. Contacts will be asked to call you. Ask your administrator to add your address and barangay.'

/**
 * The SOS page's "no address" line. In legacy mode it is today's text, word for word;
 * with accounts on this computer the person adds the address themselves (build step 12).
 */
export function AddAddressPrompt() {
  const navigate = useNavigate()
  const [own, setOwn] = useState(false)

  useEffect(() => {
    let current = true
    void signinMode().then((m) => current && setOwn(m === 'device_accounts'))
    return () => {
      current = false
    }
  }, [])

  if (!own) return <p className="text-destructive text-xl">{LEGACY_TEXT}</p>
  return (
    <div className="flex flex-wrap items-center gap-6">
      <p className="text-destructive text-xl">No address on file. Contacts will be asked to call you.</p>
      <GazeButton onClick={() => void navigate('/sos/address')}>
        <MapPin aria-hidden /> Add your address
      </GazeButton>
    </div>
  )
}
