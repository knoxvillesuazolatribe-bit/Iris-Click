import { LoaderCircle } from 'lucide-react'
import { useEffect } from 'react'
import { GazeButton } from '@/components/gaze-button'

interface ConfirmDialogProps {
  title: string
  text?: string
  confirmLabel: string
  busy?: boolean
  onConfirm: () => void
  onCancel: () => void
}

/** A large Yes / Cancel question, so a stray wink cannot remove anything. */
export function ConfirmDialog({ title, text, confirmLabel, busy, onConfirm, onCancel }: ConfirmDialogProps) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onCancel()
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onCancel])

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-6">
      <div role="alertdialog" aria-modal="true" aria-labelledby="confirm-title"
        className="bg-card text-card-foreground w-full max-w-xl space-y-6 rounded-2xl border p-8 text-center shadow-xl">
        <h2 id="confirm-title" className="text-3xl font-bold break-words">{title}</h2>
        {text && <p className="text-muted-foreground text-lg">{text}</p>}
        <div className="flex flex-wrap justify-center gap-8">
          <GazeButton variant="destructive" disabled={busy} onClick={onConfirm} className="min-w-48">
            {busy && <LoaderCircle className="animate-spin" aria-hidden />}
            {confirmLabel}
          </GazeButton>
          <GazeButton variant="outline" disabled={busy} onClick={onCancel} className="min-w-48" autoFocus>
            Cancel
          </GazeButton>
        </div>
      </div>
    </div>
  )
}
