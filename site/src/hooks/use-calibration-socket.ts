import { useEffect } from 'react'
import { useCalibrationStore } from '@/store/calibration-store'

/** Closes the calibration session (releasing the server's camera) when the page goes away. */
export function useCalibrationSocket() {
  const reset = useCalibrationStore((s) => s.reset)

  useEffect(() => {
    window.addEventListener('pagehide', reset)
    return () => {
      window.removeEventListener('pagehide', reset)
      reset()
    }
  }, [reset])
}
