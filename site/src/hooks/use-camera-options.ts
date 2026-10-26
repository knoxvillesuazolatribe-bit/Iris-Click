import { useCallback, useEffect } from 'react'
import { cameraService } from '@/services/camera-service'
import { useCameraStore } from '@/store/camera-store'

/** Scans for cameras once when the page opens; `rescan` after plugging one in. */
export function useCameraOptions() {
  const cameras = useCameraStore((s) => s.cameras)
  const isScanning = useCameraStore((s) => s.isScanning)
  const error = useCameraStore((s) => s.error)
  const scanCount = useCameraStore((s) => s.scanCount)
  const scan = useCameraStore((s) => s.scan)

  useEffect(() => {
    void scan()
  }, [scan])

  const snapshotUrl = useCallback(
    (index: number) => cameraService.snapshotUrl(index, scanCount),
    [scanCount],
  )

  return { cameras, isScanning, error, rescan: scan, snapshotUrl }
}
