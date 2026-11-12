import { Check, Delete } from 'lucide-react'
import { useEffect } from 'react'
import { GazeButton } from '@/components/gaze-button'

interface NumberPadProps {
  onDigit: (digit: string) => void
  onDelete: () => void
  onOk: () => void
  okDisabled?: boolean
  disabled?: boolean
  okLabel?: string
}

const ROWS = [['1', '2', '3'], ['4', '5', '6'], ['7', '8', '9']]

/**
 * A large on-screen number pad (each key at least 80 px) for PINs and codes, picked by
 * looking and winking. A helper can also type digits, Backspace and Enter on a keyboard.
 */
export function NumberPad({ onDigit, onDelete, onOk, okDisabled, disabled, okLabel = 'OK' }: NumberPadProps) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (disabled || e.ctrlKey || e.metaKey || e.altKey) return
      if (/^[0-9]$/.test(e.key)) onDigit(e.key)
      else if (e.key === 'Backspace') onDelete()
      else if (e.key === 'Enter' && !okDisabled) onOk()
      else return
      e.preventDefault()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onDigit, onDelete, onOk, okDisabled, disabled])

  const key = 'min-h-20 min-w-24 text-3xl font-bold'
  return (
    <div role="group" aria-label="Number pad" className="grid grid-cols-3 gap-4">
      {ROWS.flat().map((digit) => (
        <GazeButton key={digit} variant="outline" className={key} disabled={disabled} onClick={() => onDigit(digit)}>
          {digit}
        </GazeButton>
      ))}
      <GazeButton variant="outline" className={key} disabled={disabled} onClick={onDelete} aria-label="Delete">
        <Delete aria-hidden className="size-8" />
      </GazeButton>
      <GazeButton variant="outline" className={key} disabled={disabled} onClick={() => onDigit('0')}>
        0
      </GazeButton>
      <GazeButton className={key} disabled={disabled || okDisabled} onClick={onOk}>
        <Check aria-hidden className="size-8" />
        {okLabel}
      </GazeButton>
    </div>
  )
}
