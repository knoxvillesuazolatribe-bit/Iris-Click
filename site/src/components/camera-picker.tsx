import { CameraOff, RefreshCw } from 'lucide-react'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  Field,
  FieldContent,
  FieldDescription,
  FieldLabel,
  FieldTitle,
} from '@/components/ui/field'
import { RadioGroup, RadioGroupItem } from '@/components/ui/radio-group'
import { Skeleton } from '@/components/ui/skeleton'
import type { Camera } from '@/validators/camera-validator'

interface CameraPickerProps {
  cameras: Camera[]
  value: number | undefined
  onChange: (index: number) => void
  isScanning: boolean
  error: string | null
  onRescan: () => void
  snapshotUrl: (index: number) => string
  invalid?: boolean
}

// Below this mean grey level a face is usually too dark to track reliably.
const DARK_BRIGHTNESS = 60

function cameraNote(camera: Camera) {
  if (camera.in_use) return 'In use by eye tracking (it will pause during calibration)'
  if (!camera.available) return 'Connected but sends no picture'
  if (camera.face_found) return `${camera.width}×${camera.height} · your face is visible`
  if (camera.brightness < DARK_BRIGHTNESS) return `${camera.width}×${camera.height} · too dark, no face seen`
  return `${camera.width}×${camera.height} · no face seen: point it at you`
}

export function CameraPicker(props: CameraPickerProps) {
  const { cameras, value, onChange, isScanning, error, onRescan, snapshotUrl, invalid } = props

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between gap-3">
        <p className="text-muted-foreground text-sm">
          Pick the camera that faces you: built-in webcam, USB camera or phone.
        </p>
        <Button type="button" variant="outline" size="sm" onClick={onRescan} disabled={isScanning}>
          <RefreshCw className={isScanning ? 'animate-spin' : undefined} aria-hidden />
          {isScanning ? 'Scanning…' : 'Scan again'}
        </Button>
      </div>

      {error && (
        <Alert variant="destructive">
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}

      {isScanning && cameras.length === 0 ? (
        <div className="grid gap-3 sm:grid-cols-2" aria-busy>
          <Skeleton className="h-36" />
          <Skeleton className="h-36" />
        </div>
      ) : cameras.length === 0 && !error ? (
        <Alert>
          <CameraOff aria-hidden />
          <AlertDescription>
            No camera found. Connect a camera (or start your phone camera app), then choose Scan again.
          </AlertDescription>
        </Alert>
      ) : (
        <RadioGroup
          value={value === undefined ? '' : String(value)}
          onValueChange={(next) => onChange(Number(next))}
          className="grid gap-3 sm:grid-cols-2"
          aria-invalid={invalid}
          aria-label="Camera"
        >
          {cameras.map((camera) => {
            const id = `camera-${camera.index}`
            const disabled = !camera.available && !camera.in_use
            return (
              <FieldLabel key={camera.index} htmlFor={id}>
                <Field orientation="horizontal" data-disabled={disabled}>
                  <RadioGroupItem value={String(camera.index)} id={id} disabled={disabled} />
                  <FieldContent className="gap-2">
                    {camera.has_snapshot ? (
                      <img
                        src={snapshotUrl(camera.index)}
                        alt={`What camera ${camera.index + 1} sees`}
                        className="aspect-video w-full rounded-md object-cover"
                      />
                    ) : (
                      <div className="bg-muted text-muted-foreground flex aspect-video w-full items-center justify-center rounded-md text-sm">
                        No preview
                      </div>
                    )}
                    <FieldTitle>
                      Camera {camera.index + 1}
                      {camera.face_found && <Badge variant="secondary">Face found</Badge>}
                      {camera.selected && <Badge variant="outline">Last used</Badge>}
                    </FieldTitle>
                    <FieldDescription>{cameraNote(camera)}</FieldDescription>
                  </FieldContent>
                </Field>
              </FieldLabel>
            )
          })}
        </RadioGroup>
      )}
    </div>
  )
}
