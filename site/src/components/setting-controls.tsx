import { Minus, Plus } from 'lucide-react'
import type { ReactNode } from 'react'
import { GazeButton } from '@/components/gaze-button'

interface SettingRowProps {
  title: string
  description: string
  note?: ReactNode
  children: ReactNode
}

/** One setting: what it is on the left, a large control on the right. */
export function SettingRow({ title, description, note, children }: SettingRowProps) {
  return (
    <section className="bg-card flex flex-wrap items-center justify-between gap-6 rounded-2xl border-2 p-6">
      <div className="min-w-64 flex-1 space-y-1">
        <h2 className="text-2xl font-bold">{title}</h2>
        <p className="text-muted-foreground text-lg">{description}</p>
        {note && <p className="text-lg font-semibold text-amber-700 dark:text-amber-400">{note}</p>}
      </div>
      <div className="flex flex-wrap items-center gap-6">{children}</div>
    </section>
  )
}

interface ChoiceProps<T extends string> {
  value: T
  options: { value: T; label: string; disabled?: boolean }[]
  onChange: (value: T) => void
  label: string
}

/** Big buttons, one per option; the chosen one is filled (no hover-only state). */
export function Choice<T extends string>({ value, options, onChange, label }: ChoiceProps<T>) {
  return (
    <div role="radiogroup" aria-label={label} className="flex flex-wrap gap-6">
      {options.map((option) => (
        <GazeButton
          key={option.value}
          role="radio"
          aria-checked={value === option.value}
          variant={value === option.value ? 'default' : 'outline'}
          disabled={option.disabled}
          className="min-w-32"
          onClick={() => onChange(option.value)}
        >
          {option.label}
        </GazeButton>
      ))}
    </div>
  )
}

interface OnOffProps {
  value: boolean
  onChange: (value: boolean) => void
  label: string
  offDisabled?: boolean
  onDisabled?: boolean
}

export function OnOff({ value, onChange, label, offDisabled, onDisabled }: OnOffProps) {
  return (
    <Choice
      label={label}
      value={value ? 'on' : 'off'}
      options={[
        { value: 'on', label: 'On', disabled: onDisabled },
        { value: 'off', label: 'Off', disabled: offDisabled },
      ]}
      onChange={(v) => onChange(v === 'on')}
    />
  )
}

interface StepperProps {
  value: number
  min: number
  max: number
  step?: number
  onChange: (value: number) => void
  format: (value: number) => string
  label: string
  disabled?: boolean
}

/** − value + with 80 px buttons: easier by gaze than a slider. */
export function Stepper({ value, min, max, step = 1, onChange, format, label, disabled }: StepperProps) {
  const set = (next: number) => onChange(Math.min(max, Math.max(min, next)))
  return (
    <div className="flex items-center gap-6" role="group" aria-label={label}>
      <GazeButton variant="outline" aria-label={`Less ${label}`} disabled={disabled || value <= min} onClick={() => set(value - step)}>
        <Minus aria-hidden />
      </GazeButton>
      <output className="min-w-40 text-center text-3xl font-bold tabular-nums" aria-live="polite">
        {format(value)}
      </output>
      <GazeButton variant="outline" aria-label={`More ${label}`} disabled={disabled || value >= max} onClick={() => set(value + step)}>
        <Plus aria-hidden />
      </GazeButton>
    </div>
  )
}
