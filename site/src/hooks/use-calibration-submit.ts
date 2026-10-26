import { zodResolver } from '@hookform/resolvers/zod'
import { useEffect } from 'react'
import { useForm } from 'react-hook-form'
import { useFullscreen } from '@/hooks/use-fullscreen'
import { useCalibrationStore } from '@/store/calibration-store'
import { useCameraStore } from '@/store/camera-store'
import type { Camera } from '@/validators/camera-validator'
import {
  calibrationStartSchema,
  type CalibrationStartInput,
} from '@/validators/calibration-validator'

/** The remembered camera if it still works, else one that sees a face, else any working one. */
function defaultCamera(cameras: Camera[]): number | undefined {
  const usable = cameras.filter((c) => c.available || c.in_use)
  return (
    usable.find((c) => c.selected)?.index ??
    usable.find((c) => c.face_found)?.index ??
    usable[0]?.index
  )
}

export function useCalibrationSubmit() {
  const begin = useCalibrationStore((s) => s.begin)
  const cameras = useCameraStore((s) => s.cameras)
  const { enter } = useFullscreen()
  const form = useForm<CalibrationStartInput>({
    resolver: zodResolver(calibrationStartSchema),
    defaultValues: { profile_name: 'My calibration' },
  })

  useEffect(() => {
    const current = form.getValues('camera_index')
    const stillListed = cameras.some((c) => c.index === current && (c.available || c.in_use))
    const fallback = defaultCamera(cameras)
    if (!stillListed && fallback !== undefined) {
      form.setValue('camera_index', fallback, { shouldValidate: form.formState.isSubmitted })
    }
  }, [cameras, form])

  const onSubmit = form.handleSubmit(async (values) => {
    // Dot positions are viewport fractions; they only equal screen fractions
    // (what the cursor needs) when the page covers the whole screen.
    await enter()
    begin(values, {
      width: Math.round(window.screen.width * window.devicePixelRatio),
      height: Math.round(window.screen.height * window.devicePixelRatio),
    })
  })

  return { form, onSubmit }
}
