import { useEffect, useState } from 'react'
import { appInfoService } from '@/services/admin-service'

const FALLBACK = 'IrisClick'
let cached: string | null = null

/** The app name the admin set (Phase 8); also used as the browser tab title. */
export function useAppName(): string {
  const [name, setName] = useState(cached ?? FALLBACK)
  useEffect(() => {
    let current = true
    appInfoService
      .get()
      .then(({ app_name }) => {
        cached = app_name
        document.title = app_name
        if (current) setName(app_name)
      })
      .catch(() => undefined) // keep the fallback; the server may be starting
    return () => {
      current = false
    }
  }, [])
  return name
}
