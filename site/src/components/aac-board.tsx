import { Volume2 } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { GazeButton } from '@/components/gaze-button'
import { BOARD } from '@/lib/aac-board'
import { player } from '@/lib/natural-voice'
import { cn } from '@/lib/utils'
import { filterText } from '@/lib/word-filter'

const FLASH_MS = 600

interface AacBoardProps {
  volume: number
  /** Reports a problem (e.g. the browser cannot speak). */
  onError: (message: string) => void
}

/** Communication board: pick a category, then a tile to speak it at once (two winks). */
export function AacBoard({ volume, onError }: AacBoardProps) {
  const [categoryId, setCategoryId] = useState(BOARD[0].id)
  const [spoken, setSpoken] = useState<string | null>(null)
  const timer = useRef<number | undefined>(undefined)
  useEffect(() => () => window.clearTimeout(timer.current), [])
  const category = BOARD.find((c) => c.id === categoryId) ?? BOARD[0]

  const say = async (text: string) => {
    const { speak: words } = await filterText(text) // extension: word filter
    const result = await player.speak(words, 'en', volume) // clearer TTS; falls back to the old voice
    if (!result.ok) {
      onError(result.error)
      return
    }
    setSpoken(text)
    window.clearTimeout(timer.current)
    timer.current = window.setTimeout(() => setSpoken(null), FLASH_MS)
  }

  return (
    <div className="flex flex-col gap-8">
      <div role="tablist" aria-label="Board categories" className="flex flex-wrap gap-6">
        {BOARD.map(({ id, label, icon: Icon }) => (
          <GazeButton key={id} role="tab" aria-selected={id === categoryId}
            variant={id === categoryId ? 'default' : 'outline'} className="min-w-44"
            onClick={() => setCategoryId(id)}>
            <Icon aria-hidden />
            {label}
          </GazeButton>
        ))}
      </div>

      <div role="tabpanel" aria-label={category.label}
        className="grid grid-cols-[repeat(auto-fill,minmax(15rem,1fr))] gap-6">
        {category.tiles.map(({ text, icon: Icon }) => (
          <button
            key={text}
            type="button"
            onClick={() => void say(text)}
            className={cn(
              'bg-card border-primary flex min-h-32 flex-col items-center justify-center gap-3 rounded-2xl border-2 p-4 text-center',
              'text-2xl font-semibold transition-colors outline-none',
              'hover:border-primary hover:ring-ring/70 focus-visible:ring-ring hover:ring-4 focus-visible:ring-4',
              spoken === text && 'bg-primary text-primary-foreground border-primary',
            )}
          >
            <Icon className={cn('size-10', spoken !== text && 'text-primary')} aria-hidden />
            {text}
          </button>
        ))}
      </div>

      <p aria-live="polite" className="text-muted-foreground flex items-center gap-2 text-lg">
        <Volume2 className="size-5" aria-hidden />
        {spoken ? `Speaking: “${spoken}”` : 'Look at a tile and wink to say it out loud.'}
      </p>
    </div>
  )
}
