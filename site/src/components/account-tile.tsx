import { Crosshair, KeyRound, UserRound, X } from 'lucide-react'
import { cn } from '@/lib/utils'
import type { AccountTile as Tile } from '@/validators/accounts-validator'

interface AccountTileProps {
  tile: Tile
  onSelect: (tile: Tile) => void
  /** Remove mode: the tile is marked in red and picking it asks to remove the account. */
  removing?: boolean
  disabled?: boolean
}

/** A large account tile (at least 200 x 160 px) picked by looking at it and winking. */
export function AccountTile({ tile, onSelect, removing, disabled }: AccountTileProps) {
  const Icon = removing ? X : UserRound
  return (
    <button
      type="button"
      disabled={disabled}
      onClick={() => onSelect(tile)}
      aria-label={removing ? `Remove ${tile.username}` : tile.username}
      className={cn(
        'bg-card text-card-foreground flex min-h-40 min-w-50 flex-col items-center justify-center',
        'gap-3 rounded-2xl border-2 p-6 text-center shadow-sm transition-shadow outline-none',
        'hover:ring-ring/70 focus-visible:ring-ring hover:ring-4 focus-visible:ring-4 disabled:opacity-50',
        removing ? 'border-destructive' : 'border-primary',
      )}
    >
      <Icon className={cn('size-10', removing ? 'text-destructive' : 'text-primary')} aria-hidden />
      <span className="text-2xl font-bold break-all">{tile.username}</span>
      {!removing && (
        <span className="text-muted-foreground flex items-center gap-2 text-base">
          {tile.needs_pin ? <><KeyRound className="size-4" aria-hidden /> PIN needed</> : 'Remembered on this computer'}
        </span>
      )}
      {!removing && tile.accuracy != null && (
        <span className="text-muted-foreground flex items-center gap-2 text-base">
          <Crosshair className="size-4" aria-hidden /> Accuracy {Math.round(tile.accuracy)}%
        </span>
      )}
    </button>
  )
}
