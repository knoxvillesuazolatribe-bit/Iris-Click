import { useCallback, useSyncExternalStore } from 'react'

function subscribe(onChange: () => void) {
  document.addEventListener('fullscreenchange', onChange)
  return () => document.removeEventListener('fullscreenchange', onChange)
}

export function useFullscreen() {
  const isFullscreen = useSyncExternalStore(subscribe, () => document.fullscreenElement !== null)

  // Browsers only allow this from a user gesture (click, key press, submit).
  const enter = useCallback(async () => {
    if (document.fullscreenElement) return true
    try {
      await document.documentElement.requestFullscreen({ navigationUI: 'hide' })
      return true
    } catch {
      return false
    }
  }, [])

  const exit = useCallback(async () => {
    if (document.fullscreenElement) await document.exitFullscreen().catch(() => undefined)
  }, [])

  return { isFullscreen, enter, exit }
}
