import { Eye, EyeOff } from 'lucide-react'
import { useCallback, useState } from 'react'
import { GazeButton } from '@/components/gaze-button'
import { NumberPad } from '@/components/number-pad'
import { cn } from '@/lib/utils'

export const PIN_LENGTH = 6

interface PinEntryProps {
  /** Called with the six digits when OK is picked. */
  onSubmit: (pin: string) => void
  disabled?: boolean
  okLabel?: string
}

/**
 * Six PIN dots, a Show button and the number pad (screens B5, B6, C1). The PIN lives only
 * in this component's memory: it is never put in a URL, browser storage or the page title.
 */
export function PinEntry({ onSubmit, disabled, okLabel }: PinEntryProps) {
  const [pin, setPin] = useState('')
  const [shown, setShown] = useState(false)

  const digit = useCallback((d: string) => setPin((p) => (p.length < PIN_LENGTH ? p + d : p)), [])
  const erase = useCallback(() => setPin((p) => p.slice(0, -1)), [])
  const ok = useCallback(() => {
    if (pin.length !== PIN_LENGTH) return
    onSubmit(pin)
    setPin('')
    setShown(false)
  }, [pin, onSubmit])

  return (
    <div className="flex flex-col items-center gap-6">
      <div className="flex items-center gap-6">
        <div aria-label={`${pin.length} of ${PIN_LENGTH} digits entered`} role="status" className="flex gap-4">
          {Array.from({ length: PIN_LENGTH }, (_, i) => (
            <span key={i} aria-hidden
              className={cn('flex size-12 items-center justify-center rounded-full border-2 text-2xl font-bold',
                i < pin.length ? 'border-primary bg-primary text-primary-foreground' : 'border-muted-foreground/50')}>
              {shown && i < pin.length ? pin[i] : ''}
            </span>
          ))}
        </div>
        <GazeButton variant="outline" disabled={disabled || pin.length === 0} onClick={() => setShown((s) => !s)}>
          {shown ? <EyeOff aria-hidden /> : <Eye aria-hidden />}
          {shown ? 'Hide' : 'Show'}
        </GazeButton>
      </div>
      <NumberPad onDigit={digit} onDelete={erase} onOk={ok} okDisabled={pin.length !== PIN_LENGTH}
        disabled={disabled} okLabel={okLabel} />
    </div>
  )
}
