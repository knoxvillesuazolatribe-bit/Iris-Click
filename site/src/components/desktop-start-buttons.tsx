import { isAxiosError } from 'axios'
import { Crosshair, House, LoaderCircle, Play } from 'lucide-react'
import { useState } from 'react'
import { useNavigate } from 'react-router'
import { apiClient } from '@/api/api-client'
import { GazeButton } from '@/components/gaze-button'
import { linkDesktop } from '@/lib/desktop-link'
import { checkDesktop } from '@/lib/desktop-status'

const READY_RETRIES = 4
const READY_WAIT_MS = 1500

interface Props {
  /** Signs the chosen user in on the website; resolves true on success. */
  signIn: () => Promise<boolean>
  onError: (message: string) => void
}

/**
 * Hosted website, after choosing a name: start eye tracking on this PC (IrisClick
 * Desktop, with the user's own calibration), calibrate, or continue without it.
 */
export function DesktopStartButtons({ signIn, onError }: Props) {
  const navigate = useNavigate()
  const [busy, setBusy] = useState<'start' | 'calibrate' | 'home' | null>(null)

  const go = async (kind: 'calibrate' | 'home') => {
    setBusy(kind)
    try {
      if (await signIn()) void navigate(kind === 'home' ? '/home' : '/calibration')
    } finally {
      setBusy(null)
    }
  }

  const start = async () => {
    setBusy('start')
    try {
      if (!(await signIn())) return
      if (!(await checkDesktop()).running) return void navigate('/desktop')
      await linkDesktop()
      // Right after linking, IrisClick Desktop may still be copying the user's details.
      for (let attempt = 0; ; attempt++) {
        try {
          await apiClient.post('/desktop/tracking/start')
          return void navigate('/home')
        } catch (err) {
          const status = isAxiosError(err) ? err.response?.status : undefined
          const message = isAxiosError(err) ? err.response?.data?.detail : undefined
          if (status === 409 && typeof message === 'string' && /calibrat/i.test(message)) {
            return void navigate('/calibration') // no calibration on this computer yet
          }
          if (status === 409 && attempt < READY_RETRIES) {
            await new Promise((r) => setTimeout(r, READY_WAIT_MS))
            continue
          }
          onError(typeof message === 'string' ? message : 'Eye tracking could not start.')
          return
        }
      }
    } finally {
      setBusy(null)
    }
  }

  return (
    <div className="flex w-full flex-col gap-6">
      <GazeButton className="min-h-28 w-full text-2xl" disabled={busy !== null} onClick={() => void start()}>
        {busy === 'start' ? <LoaderCircle className="animate-spin" aria-hidden /> : <Play aria-hidden />}
        Start eye tracking
      </GazeButton>
      <GazeButton variant="outline" className="min-h-28 w-full text-2xl" disabled={busy !== null} onClick={() => void go('calibrate')}>
        {busy === 'calibrate' ? <LoaderCircle className="animate-spin" aria-hidden /> : <Crosshair aria-hidden />}
        Calibrate
      </GazeButton>
      <GazeButton variant="outline" className="min-h-20 w-full text-xl" disabled={busy !== null} onClick={() => void go('home')}>
        {busy === 'home' ? <LoaderCircle className="animate-spin" aria-hidden /> : <House aria-hidden />}
        Continue without eye tracking
      </GazeButton>
    </div>
  )
}
