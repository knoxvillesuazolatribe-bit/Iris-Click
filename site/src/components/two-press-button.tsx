import type { LucideIcon } from 'lucide-react'
import { useState } from 'react'
import { GazeButton } from '@/components/gaze-button'
import { cn } from '@/lib/utils'

interface TwoPressButtonProps {
  icon: LucideIcon
  label: string
  confirmLabel: string
  onConfirm: () => void
  disabled?: boolean
  className?: string
}

/**
 * A destructive action that needs a second press, so a stray wink cannot
 * erase anything. The first press shows "Yes, …" and Cancel.
 */
export function TwoPressButton({ icon: Icon, label, confirmLabel, onConfirm, disabled, className }: TwoPressButtonProps) {
  const [confirming, setConfirming] = useState(false)
  if (!confirming) {
    return (
      <GazeButton variant="outline" disabled={disabled} onClick={() => setConfirming(true)} className={className}>
        <Icon aria-hidden />
        {label}
      </GazeButton>
    )
  }
  return (
    <div className={cn('flex flex-wrap items-center gap-6', className)} role="group" aria-label={confirmLabel}>
      <GazeButton
        variant="destructive"
        autoFocus
        onClick={() => {
          setConfirming(false)
          onConfirm()
        }}
      >
        <Icon aria-hidden />
        {confirmLabel}
      </GazeButton>
      <GazeButton variant="outline" onClick={() => setConfirming(false)}>
        Cancel
      </GazeButton>
    </div>
  )
}
