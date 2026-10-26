import { create } from 'zustand'
import { cameraService } from '@/services/camera-service'
import type { Camera } from '@/validators/camera-validator'

interface CameraState {
  cameras: Camera[]
  isScanning: boolean
  error: string | null
  scanCount: number
  scan: () => Promise<void>
}

export const useCameraStore = create<CameraState>((set, get) => ({
  cameras: [],
  isScanning: false,
  error: null,
  scanCount: 0,

  scan: async () => {
    if (get().isScanning) return
    set({ isScanning: true, error: null })
    try {
      const cameras = await cameraService.getCameras()
      set((state) => ({ cameras, scanCount: state.scanCount + 1 }))
    } catch {
      set({ error: 'Could not look for cameras. Make sure the IrisClick server is running.' })
    } finally {
      set({ isScanning: false })
    }
  },
}))
