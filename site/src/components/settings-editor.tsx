import { LoaderCircle, RotateCcw, Save } from 'lucide-react'
import { useState } from 'react'
import { errorMessage } from '@/api/app-client'
import { AccessibilityFields } from '@/components/accessibility-fields'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { SETTING_KEYS as KEYS } from '@/lib/settings'
import type { AccessibilityValues } from '@/validators/settings-validator'

interface SettingsEditorProps {
  saved: AccessibilityValues
  isDefault: boolean
  resetLabel: string
  savedMessage?: string
  onSave: (values: AccessibilityValues) => Promise<AccessibilityValues>
  onReset: () => Promise<AccessibilityValues>
  /** Called after a successful save or reset, e.g. to refresh the rest of the page. */
  onSaved?: () => void
}

type Confirm = 'save' | 'reset' | null
type Notice = { kind: 'ok' | 'error'; text: string } | null

/** Admin settings editor: Save / Reset → confirm → real result. */
export function SettingsEditor({ saved, isDefault, resetLabel, savedMessage, onSave, onReset, onSaved }: SettingsEditorProps) {
  const [base, setBase] = useState(saved)
  const [draft, setDraft] = useState(saved)
  const [confirm, setConfirm] = useState<Confirm>(null)
  const [busy, setBusy] = useState(false)
  const [notice, setNotice] = useState<Notice>(null)
  const [atDefault, setAtDefault] = useState(isDefault)

  const changed = KEYS.some((k) => draft[k] !== base[k])
  const set = <K extends keyof AccessibilityValues>(key: K, value: AccessibilityValues[K]) => {
    setDraft((d) => ({ ...d, [key]: value }))
    setConfirm(null)
    setNotice(null)
  }

  const run = async (action: 'save' | 'reset') => {
    setBusy(true)
    setConfirm(null)
    try {
      const next = action === 'save' ? await onSave(draft) : await onReset()
      setBase(next)
      setDraft(next)
      setAtDefault(action === 'reset')
      setNotice({ kind: 'ok', text: savedMessage ?? 'Settings updated and saved successfully.' })
      onSaved?.()
    } catch (err) {
      setNotice({ kind: 'error', text: errorMessage(err, 'The settings were not saved.') })
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="flex flex-col gap-4">
      {notice && (
        <Alert variant={notice.kind === 'error' ? 'destructive' : 'default'} role="status">
          <AlertDescription>{notice.text}</AlertDescription>
        </Alert>
      )}
      <AccessibilityFields draft={draft} set={set} />
      <div className="flex flex-wrap items-center justify-between gap-4 border-t pt-4">
        {confirm ? (
          <div className="flex flex-wrap items-center gap-3" role="group" aria-label="Confirm">
            <span className="font-semibold">
              {confirm === 'save' ? 'Save these settings?' : `${resetLabel}?`}
            </span>
            <Button disabled={busy} variant={confirm === 'reset' ? 'destructive' : 'default'}
              onClick={() => void run(confirm)}>
              {busy && <LoaderCircle className="animate-spin" aria-hidden />}
              Yes, {confirm === 'save' ? 'save' : 'reset'}
            </Button>
            <Button variant="outline" onClick={() => setConfirm(null)}>Cancel</Button>
          </div>
        ) : (
          <>
            <Button size="lg" disabled={!changed || busy} onClick={() => setConfirm('save')}>
              <Save aria-hidden />
              {changed ? 'Save Settings' : 'No changes'}
            </Button>
            <Button size="lg" variant="outline" disabled={busy || (atDefault && !changed)}
              onClick={() => setConfirm('reset')}>
              <RotateCcw aria-hidden />
              {resetLabel}
            </Button>
          </>
        )}
      </div>
    </div>
  )
}
