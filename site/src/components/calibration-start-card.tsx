import { Eye } from 'lucide-react'
import { Controller, type UseFormReturn } from 'react-hook-form'
import { CameraPicker } from '@/components/camera-picker'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import { Field, FieldDescription, FieldError, FieldLabel, FieldSet, FieldLegend } from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import type { Camera } from '@/validators/camera-validator'
import type { CalibrationStartInput } from '@/validators/calibration-validator'

export interface CameraOptions {
  cameras: Camera[]
  isScanning: boolean
  error: string | null
  rescan: () => void
  snapshotUrl: (index: number) => string
}

interface CalibrationStartCardProps {
  form: UseFormReturn<CalibrationStartInput>
  onSubmit: () => void
  error: string | null
  cameraOptions: CameraOptions
}

export function CalibrationStartCard({ form, onSubmit, error, cameraOptions }: CalibrationStartCardProps) {
  return (
    <Card className="w-full max-w-2xl">
      <CardHeader>
        <CardTitle className="flex items-center gap-3 text-3xl">
          <Eye className="size-8" aria-hidden />
          Eye calibration
        </CardTitle>
        <CardDescription className="text-base">
          The screen goes full screen and shows 13 dots. Follow each dot with your eyes only.
          When it finishes, eye tracking starts in the background and you can close this page.
        </CardDescription>
      </CardHeader>
      <form onSubmit={onSubmit} noValidate>
        <CardContent className="space-y-6">
          {error && (
            <Alert variant="destructive">
              <AlertTitle>Last calibration did not finish</AlertTitle>
              <AlertDescription>{error}</AlertDescription>
            </Alert>
          )}
          <Controller
            control={form.control}
            name="profile_name"
            render={({ field, fieldState }) => (
              <Field data-invalid={fieldState.invalid}>
                <FieldLabel htmlFor="profile-name" className="text-base">
                  Calibration name
                </FieldLabel>
                <Input
                  id="profile-name"
                  className="h-12 text-lg"
                  autoComplete="off"
                  aria-invalid={fieldState.invalid}
                  {...field}
                />
                <FieldDescription>For example where you sit: "Desk" or "Bed".</FieldDescription>
                {fieldState.invalid && <FieldError errors={[fieldState.error]} />}
              </Field>
            )}
          />
          <Controller
            control={form.control}
            name="camera_index"
            render={({ field, fieldState }) => (
              <FieldSet data-invalid={fieldState.invalid}>
                <FieldLegend className="text-base">Camera</FieldLegend>
                <CameraPicker
                  cameras={cameraOptions.cameras}
                  value={field.value}
                  onChange={field.onChange}
                  isScanning={cameraOptions.isScanning}
                  error={cameraOptions.error}
                  onRescan={cameraOptions.rescan}
                  snapshotUrl={cameraOptions.snapshotUrl}
                  invalid={fieldState.invalid}
                />
                {fieldState.invalid && <FieldError errors={[fieldState.error]} />}
              </FieldSet>
            )}
          />
          <ul className="text-muted-foreground list-disc space-y-1 pl-5 text-sm">
            <li>Sit comfortably, about an arm's length from the screen and camera.</li>
            <li>Use soft light in front of you; avoid a bright window behind you.</li>
            <li>Press Space at any time to pause for a rest.</li>
          </ul>
        </CardContent>
        <CardFooter className="pt-6">
          <Button type="submit" size="lg" className="h-14 w-full text-lg" disabled={form.formState.isSubmitting}>
            Start calibration
          </Button>
        </CardFooter>
      </form>
    </Card>
  )
}
