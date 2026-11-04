import type { LucideIcon } from 'lucide-react'
import { cn } from '@/lib/utils'

interface HomeCardProps {
  icon: LucideIcon
  title: string
  description: string
  onSelect: () => void
  /** Shown instead of the description when the feature is not built yet. */
  unavailable?: string
  emergency?: boolean
}

/**
 * A Home Suite card, at least 160 px tall, picked by looking at it and
 * winking. Emergency cards are red; unavailable ones say why, plainly.
 */
export function HomeCard({ icon: Icon, title, description, onSelect, unavailable, emergency }: HomeCardProps) {
  return (
    <button
      type="button"
      disabled={Boolean(unavailable)}
      onClick={onSelect}
      className={cn(
        'flex min-h-44 flex-col items-start justify-center gap-3 rounded-2xl border-4 p-6 text-left',
        'shadow-sm transition-shadow outline-none',
        'hover:ring-ring/70 focus-visible:ring-ring hover:ring-4 focus-visible:ring-4',
        emergency
          ? 'border-destructive bg-destructive text-white'
          : 'bg-card text-card-foreground hover:border-primary',
        unavailable && 'cursor-not-allowed hover:ring-0',
        unavailable && !emergency && 'opacity-60',
      )}
    >
      <Icon className="size-12 shrink-0" aria-hidden />
      <span className="text-3xl font-bold">{title}</span>
      <span className={cn('text-lg', emergency ? 'text-white' : 'text-muted-foreground')}>
        {unavailable ?? description}
      </span>
    </button>
  )
}
