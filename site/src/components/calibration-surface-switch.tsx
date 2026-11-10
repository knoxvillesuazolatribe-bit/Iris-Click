import { LoaderCircle } from 'lucide-react'
import { useEffect, useState, type ReactNode } from 'react'
import { DesktopCalibrationCard } from '@/components/desktop-calibration-card'
import { fetchCalibrationSurface, type CalibrationSurface } from '@/lib/calibration-surface'

/**
 * Desktop calibration hook for the /calibration route. IrisClick Desktop decides
 * (IRISCLICK_CALIBRATION_SURFACE): "web" — the default, or no answer — shows `web`,
 * today's calibration page, unchanged; "desktop" shows the live status card while
 * the calibration runs full screen in IrisClick Desktop.
 */
export function CalibrationSurfaceSwitch({ web }: { web: ReactNode }) {
  const [surface, setSurface] = useState<CalibrationSurface | null>(null)
  const [forceWeb, setForceWeb] = useState(false)

  useEffect(() => {
    let current = true
    void fetchCalibrationSurface().then((s) => current && setSurface(s))
    return () => {
      current = false
    }
  }, [])

  if (surface === null) {
    return (
      <main className="bg-background flex min-h-svh items-center justify-center">
        <LoaderCircle className="text-muted-foreground size-12 animate-spin" aria-label="Loading" />
      </main>
    )
  }
  if (surface === 'web' || forceWeb) return <>{web}</>
  return <DesktopCalibrationCard onUseWeb={() => setForceWeb(true)} />
}
