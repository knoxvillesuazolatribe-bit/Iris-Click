import { CornerDownLeft, Delete, Space } from 'lucide-react'
import { useEffect, useRef, useState, type ReactNode } from 'react'
import type { KeyName } from '@/lib/typing'
import { cn } from '@/lib/utils'

// QWERTY: 10 keys per row fits a 1366 px screen at 80 px keys + 24 px gaps.
const ROWS: string[][] = [
  ['Q', 'W', 'E', 'R', 'T', 'Y', 'U', 'I', 'O', 'P'],
  ['A', 'S', 'D', 'F', 'G', 'H', 'J', 'K', 'L', '?'],
  ['Z', 'X', 'C', 'V', 'B', 'N', 'M', ',', '.', '!'],
]
const FLASH_MS = 250

interface GazeKeyboardProps {
  onKey: (key: KeyName) => void
  disabled?: boolean
}

/** On-page keyboard for gaze + wink: every key is at least 80 x 80 px. */
export function GazeKeyboard({ onKey, disabled }: GazeKeyboardProps) {
  const [flash, setFlash] = useState<KeyName | null>(null)
  const timer = useRef<number | undefined>(undefined)
  useEffect(() => () => window.clearTimeout(timer.current), [])

  const press = (key: KeyName) => {
    onKey(key)
    setFlash(key)
    window.clearTimeout(timer.current)
    timer.current = window.setTimeout(() => setFlash(null), FLASH_MS)
  }

  const key = (name: KeyName, label: ReactNode, aria: string, wide = '') => (
    <button
      key={name}
      type="button"
      disabled={disabled}
      aria-label={aria}
      onClick={() => press(name)}
      className={cn(
        'bg-card flex h-20 min-w-20 items-center justify-center gap-2 rounded-xl border-2 text-3xl font-bold',
        'transition-colors outline-none disabled:opacity-50',
        'hover:border-primary hover:ring-ring/70 focus-visible:ring-ring hover:ring-4 focus-visible:ring-4',
        flash === name && 'bg-primary text-primary-foreground border-primary',
        wide,
      )}
    >
      {label}
    </button>
  )

  return (
    <div className="flex flex-col items-center gap-6" role="group" aria-label="Keyboard">
      {ROWS.map((row) => (
        <div key={row.join('')} className="flex flex-wrap justify-center gap-6">
          {row.map((k) => key(k, k, k === '?' ? 'question mark' : k === '!' ? 'exclamation mark' : k === ',' ? 'comma' : k === '.' ? 'full stop' : k))}
        </div>
      ))}
      <div className="flex flex-wrap justify-center gap-6">
        {key('BACKSPACE', <><Delete className="size-8" aria-hidden /><span className="text-xl">Backspace</span></>, 'Backspace', 'px-6')}
        {key('SPACE', <><Space className="size-8" aria-hidden /><span className="text-xl">Space</span></>, 'Space', 'min-w-80')}
        {key('ENTER', <><CornerDownLeft className="size-8" aria-hidden /><span className="text-xl">Enter</span></>, 'Enter, new line', 'px-6')}
      </div>
    </div>
  )
}
