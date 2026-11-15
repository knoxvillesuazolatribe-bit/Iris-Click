import { useEffect, useRef } from 'react'
import { useLocation, useNavigate } from 'react-router'
import { openJsonSocket } from '@/api/websocket-client'
import { goesHome, type DesktopNotice } from '@/lib/web-home'
import { useSessionStore } from '@/store/session-store'

/** Waits this long before listening again when IrisClick Desktop is not answering. */
const RETRY_MS = 15000

/**
 * Listens to IrisClick Desktop on the local channel the calibration pages already use and
 * takes a signed-in person to the Home Suite after a successful calibration or when the
 * control bar's Home is pressed (lib/web-home.ts). Renders nothing.
 */
export function DesktopHomeRouter() {
  const navigate = useNavigate()
  const { pathname } = useLocation()
  const signedIn = useSessionStore((s) => s.status === 'signed-in' && s.user?.role === 'assistive_user')
  // The socket outlives page changes; it reads the latest page and session from here.
  const latest = useRef({ pathname, signedIn })
  latest.current = { pathname, signedIn }

  useEffect(() => {
    if (!signedIn) return
    let stopped = false
    let retry: number | undefined
    let close = () => {}
    const listen = () => {
      const socket = openJsonSocket('/ws/desktop-calibration', {
        onMessage: (data) => {
          if (!data || typeof data !== 'object') return
          const now = latest.current
          if (goesHome(data as DesktopNotice, now.pathname, now.signedIn)) void navigate('/home')
        },
        onClose: () => {
          if (!stopped) retry = window.setTimeout(listen, RETRY_MS)
        },
      })
      close = socket.close
    }
    listen()
    return () => {
      stopped = true
      window.clearTimeout(retry)
      close()
    }
  }, [signedIn, navigate])

  return null
}
