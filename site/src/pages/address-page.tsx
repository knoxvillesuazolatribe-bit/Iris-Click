import { ArrowLeft, Check, Delete, LoaderCircle, MapPin, Space } from 'lucide-react'
import { useState } from 'react'
import { useNavigate } from 'react-router'
import { appClient, errorMessage } from '@/api/app-client'
import { GazeButton } from '@/components/gaze-button'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { cn } from '@/lib/utils'

type Field = 'address' | 'barangay'

const LIMITS: Record<Field, number> = { address: 255, barangay: 100 }
const ROWS = ['1234567890', 'QWERTYUIOP', 'ASDFGHJKL', 'ZXCVBNM-,.']

/** Capitals at the start of each word ("123 Purok Mangga"), as addresses are written. */
function typeAddress(text: string, key: string, max: number): string {
  if (key === 'BACKSPACE') return text.slice(0, -1)
  if (text.length >= max) return text
  if (key === 'SPACE') return text === '' || text.endsWith(' ') ? text : `${text} `
  if (!/^[A-Z]$/.test(key)) return text + key
  const newWord = text === '' || /[\s,-]$/.test(text)
  return text + (newWord ? key : key.toLowerCase())
}

/**
 * Add your address (file 07, build step 12): the person adds the address that an
 * Emergency SOS alert sends to their contacts, instead of asking the administrator.
 * Typed with large on-screen keys, including numbers for house and lot numbers.
 */
export function AddressPage() {
  const navigate = useNavigate()
  const [field, setField] = useState<Field>('address')
  const [values, setValues] = useState<Record<Field, string>>({ address: '', barangay: '' })
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const press = (key: string) => {
    setError(null)
    setValues((v) => ({ ...v, [field]: typeAddress(v[field], key, LIMITS[field]) }))
  }

  const save = async () => {
    if (!values.address.trim()) return setError('Type your address first.')
    setBusy(true)
    try {
      await appClient.put('/accounts/me/address', { address: values.address.trim(), barangay: values.barangay.trim() })
      void navigate('/sos', { replace: true })
    } catch (err) {
      setError(errorMessage(err, 'Could not save your address. Please try again.'))
    } finally {
      setBusy(false)
    }
  }

  const fieldButton = (name: Field, label: string) => (
    <button type="button" onClick={() => setField(name)} aria-pressed={field === name}
      aria-label={`${label}: ${values[name] || 'empty'}`}
      className={cn('bg-card w-full rounded-2xl border-2 p-4 text-left outline-none',
        'hover:ring-ring/70 focus-visible:ring-ring hover:ring-4 focus-visible:ring-4',
        field === name ? 'border-primary ring-primary/30 ring-4' : 'border-muted')}>
      <span className="text-muted-foreground block text-lg">{label}</span>
      <span className="block min-h-9 text-2xl font-semibold break-words">
        {values[name] || <span className="text-muted-foreground font-normal">{name === 'address' ? 'House no., street, purok' : 'Optional'}</span>}
      </span>
    </button>
  )

  const key = 'min-h-16 min-w-16 px-2 text-2xl font-bold'
  return (
    <main className="bg-background text-foreground mx-auto flex min-h-svh max-w-5xl flex-col items-center gap-6 p-6">
      <div className="top-band flex w-full justify-start">
        <GazeButton variant="outline" disabled={busy} onClick={() => void navigate('/sos')}>
          <ArrowLeft aria-hidden /> Back
        </GazeButton>
      </div>
      <h1 className="flex items-center gap-3 text-4xl font-bold"><MapPin className="text-primary size-10" aria-hidden /> Add your address</h1>
      <p className="text-muted-foreground text-center text-xl">Sent with an Emergency SOS so your contacts can find you.</p>
      {error && (
        <Alert variant="destructive" role="alert" className="w-full">
          <AlertDescription className="text-lg">{error}</AlertDescription>
        </Alert>
      )}
      <div className="grid w-full gap-4 sm:grid-cols-2">
        {fieldButton('address', 'Address')}
        {fieldButton('barangay', 'Barangay')}
      </div>
      <div role="group" aria-label="Address keyboard" className="flex w-full flex-col items-center gap-3">
        {ROWS.map((row) => (
          <div key={row} className="flex flex-wrap justify-center gap-3">
            {[...row].map((c) => (
              <GazeButton key={c} variant="outline" className={key} disabled={busy} onClick={() => press(c)}>{c}</GazeButton>
            ))}
          </div>
        ))}
        <div className="flex flex-wrap justify-center gap-3">
          <GazeButton variant="outline" className={`${key} min-w-40`} disabled={busy} onClick={() => press('SPACE')}>
            <Space aria-hidden className="size-7" /> Space
          </GazeButton>
          <GazeButton variant="outline" className={key} disabled={busy} aria-label="Delete" onClick={() => press('BACKSPACE')}>
            <Delete aria-hidden className="size-7" />
          </GazeButton>
          <GazeButton className={`${key} min-w-40`} disabled={busy || !values.address.trim()} onClick={() => void save()}>
            {busy ? <LoaderCircle className="animate-spin" aria-hidden /> : <Check aria-hidden className="size-7" />} Save
          </GazeButton>
        </div>
      </div>
    </main>
  )
}
