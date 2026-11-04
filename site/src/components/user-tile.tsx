import { UserRound } from 'lucide-react'
import { cn } from '@/lib/utils'
import type { AssistiveTile } from '@/validators/auth-validator'

const DATE_FORMAT = new Intl.DateTimeFormat(undefined, { dateStyle: 'medium' })

function calibrationLine(tile: AssistiveTile) {
  if (!tile.last_calibrated_at) return 'Not calibrated yet'
  const date = DATE_FORMAT.format(new Date(tile.last_calibrated_at))
  const accuracy = tile.accuracy_score === null ? '' : ` · ${tile.accuracy_score.toFixed(2)}%`
  return `Calibrated ${date}${accuracy}`
}

interface UserTileProps {
  tile: AssistiveTile
  onSelect: (tile: AssistiveTile) => void
  disabled?: boolean
}

/** A large name tile (at least 200 x 160 px) picked by looking at it and winking. */
export function UserTile({ tile, onSelect, disabled }: UserTileProps) {
  return (
    <button
      type="button"
      disabled={disabled}
      onClick={() => onSelect(tile)}
      className={cn(
        'bg-card text-card-foreground flex min-h-40 min-w-50 flex-col items-center justify-center',
        'gap-3 rounded-2xl border-2 p-6 text-center shadow-sm transition-shadow outline-none',
        'hover:border-primary hover:ring-ring/70 focus-visible:ring-ring hover:ring-4 focus-visible:ring-4',
        'disabled:opacity-50',
      )}
    >
      <UserRound className="size-10" aria-hidden />
      <span className="text-2xl font-semibold">{tile.full_name}</span>
      <span className="text-muted-foreground text-base">{calibrationLine(tile)}</span>
    </button>
  )
}
