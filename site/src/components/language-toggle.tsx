import { Languages } from 'lucide-react'
import { GazeButton } from '@/components/gaze-button'
import type { SpeechLang } from '@/lib/voices'

const OPTIONS: { value: SpeechLang; label: string }[] = [
  { value: 'en', label: 'ENGLISH' },
  { value: 'fil', label: 'FILIPINO' },
]

interface LanguageToggleProps {
  value: SpeechLang
  onChange: (language: SpeechLang) => void
  disabled?: boolean
}

/** Large [ENGLISH] [FILIPINO] switch for speaking and listening (extension). */
export function LanguageToggle({ value, onChange, disabled }: LanguageToggleProps) {
  return (
    <div className="flex flex-wrap items-center gap-6" role="group" aria-label="Speech language">
      <span className="flex items-center gap-2 text-2xl font-bold"><Languages className="size-8" aria-hidden />Language:</span>
      {OPTIONS.map((option) => (
        <GazeButton
          key={option.value}
          variant={value === option.value ? 'default' : 'outline'}
          aria-pressed={value === option.value}
          disabled={disabled}
          className="min-h-20 min-w-56 text-2xl tracking-wide"
          onClick={() => value !== option.value && onChange(option.value)}
        >
          {option.label}
        </GazeButton>
      ))}
    </div>
  )
}
