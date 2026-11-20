import { Check, Copy, type LucideIcon } from 'lucide-react'
import { useState } from 'react'
import { Button } from '@/components/ui/button'

/**
 * Below the download button: why Windows may warn about the installer (it is not code-signed
 * yet), how to continue safely, and the SHA-256 to check the file is the real, untouched one.
 */
export function InstallerNote({ sha256, icon: Icon }: { sha256?: string; icon: LucideIcon }) {
  const [copied, setCopied] = useState(false)
  const copy = async () => {
    if (!sha256) return
    try {
      await navigator.clipboard.writeText(sha256.toUpperCase())
      setCopied(true)
      window.setTimeout(() => setCopied(false), 2000)
    } catch {
      setCopied(false)
    }
  }

  return (
    <section aria-labelledby="windows-note" className="space-y-3 rounded-xl border border-teal-200 bg-teal-50 p-5 text-slate-800">
      <h2 id="windows-note" className="flex items-center gap-2 text-xl font-semibold text-teal-800">
        <Icon aria-hidden /> Windows installation note
      </h2>
      <p>
        IrisClick Desktop is not code-signed yet, so Windows may say <strong>"Windows protected your PC"</strong>.
        This is normal for new apps from small teams. Choose <strong>More info</strong>, check that the app is
        <strong> IrisClick-Desktop-Setup.exe</strong>, then choose <strong>Run anyway</strong>.
      </p>
      <p>
        If Windows only offers <strong>OK</strong> (Smart App Control is on), this PC blocks every unsigned app.
        Ask PDAO staff for a computer where IrisClick is already installed.
      </p>
      {sha256 && (
        <div className="space-y-2">
          <p>
            <strong>Check the file</strong> (optional): its SHA-256 must be exactly this. In PowerShell, in your
            Downloads folder, run <code className="rounded bg-white px-1.5 py-0.5 text-sm">Get-FileHash .\IrisClick-Desktop-Setup.exe</code>.
          </p>
          <div className="flex flex-wrap items-center gap-3">
            <code aria-label="SHA-256 of the installer" className="rounded-lg border bg-white px-3 py-2 text-sm break-all">{sha256.toUpperCase()}</code>
            <Button variant="outline" size="sm" onClick={() => void copy()}>
              {copied ? <Check aria-hidden /> : <Copy aria-hidden />} {copied ? 'Copied' : 'Copy'}
            </Button>
          </div>
        </div>
      )}
    </section>
  )
}
