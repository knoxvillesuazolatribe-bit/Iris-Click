import { CircleCheck } from 'lucide-react'
import { useEffect } from 'react'
import { Button } from '@/components/ui/button'

interface ExportSuccessDialogProps {
  fileName: string
  bytes: number
  onClose: () => void
}

/**
 * Screen 36: "Export Successful" with the file name; Close returns to
 * Generate Reports. Shown only after the PDF has really been received.
 */
export function ExportSuccessDialog({ fileName, bytes, onClose }: ExportSuccessDialogProps) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-6">
      <div role="dialog" aria-modal="true" aria-labelledby="export-success-title"
        className="bg-card text-card-foreground w-full max-w-md space-y-5 rounded-2xl border p-8 text-center shadow-xl">
        <CircleCheck className="text-primary mx-auto size-14" aria-hidden />
        <h2 id="export-success-title" className="text-2xl font-bold">Export Successful</h2>
        <p className="text-muted-foreground">
          <span className="text-foreground font-semibold break-all">{fileName}</span>
          {' '}({Math.max(1, Math.round(bytes / 1024))} KB) was created and handed to your browser.
          Check your browser’s downloads.
        </p>
        <Button size="lg" className="h-12 w-full text-base" autoFocus onClick={onClose}>
          Close
        </Button>
      </div>
    </div>
  )
}
