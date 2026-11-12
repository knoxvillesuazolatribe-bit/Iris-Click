import { Check, Delete } from 'lucide-react'
import { GazeButton } from '@/components/gaze-button'

export const USERNAME_MAX = 20

interface UsernameKeysProps {
  value: string
  onChange: (value: string) => void
  onOk: () => void
  okDisabled?: boolean
  disabled?: boolean
}

const ROWS = ['1234567890', 'qwertyuiop', 'asdfghjkl', 'zxcvbnm']

/**
 * The username keyboard (screen B3): letters, 0-9, "_" and "." only, so a username
 * can never hold a character the server refuses. Keys are large enough to pick by gaze.
 */
export function UsernameKeys({ value, onChange, onOk, okDisabled, disabled }: UsernameKeysProps) {
  const add = (c: string) => value.length < USERNAME_MAX && onChange(value + c)
  const key = 'min-h-20 min-w-20 px-2 text-2xl font-bold'
  return (
    <div role="group" aria-label="Username keyboard" className="flex w-full flex-col items-center gap-2">
      {ROWS.map((row) => (
        <div key={row} className="flex flex-wrap justify-center gap-2">
          {[...row].map((c) => (
            <GazeButton key={c} variant="outline" className={key} disabled={disabled} onClick={() => add(c)}>
              {c}
            </GazeButton>
          ))}
        </div>
      ))}
      <div className="flex flex-wrap justify-center gap-2">
        <GazeButton variant="outline" className={key} disabled={disabled} onClick={() => add('_')}>_</GazeButton>
        <GazeButton variant="outline" className={key} disabled={disabled} onClick={() => add('.')}>.</GazeButton>
        <GazeButton variant="outline" className={key} disabled={disabled || !value} aria-label="Delete"
          onClick={() => onChange(value.slice(0, -1))}>
          <Delete aria-hidden className="size-7" />
        </GazeButton>
        <GazeButton className={`${key} min-w-32`} disabled={disabled || okDisabled} onClick={onOk}>
          <Check aria-hidden className="size-7" />
          OK
        </GazeButton>
      </div>
    </div>
  )
}
