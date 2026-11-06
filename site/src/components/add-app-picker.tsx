import { AppWindow, Globe, LoaderCircle, Plus, RotateCcw, X } from 'lucide-react'
import { useEffect, useState } from 'react'
import { errorMessage } from '@/api/app-client'
import { tileIcon } from '@/components/app-tile-icon'
import { GazeButton } from '@/components/gaze-button'
import { GazeKeyboard } from '@/components/gaze-keyboard'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { typeKey } from '@/lib/typing'
import { cn } from '@/lib/utils'
import type { AppTiles, InstalledApp, TileAdd, TilesApi } from '@/services/user-apps-service'

type Tab = 'defaults' | 'installed' | 'website'
const MAX_NAME = 40
const MAX_URL = 300
const PAGE = 30

interface AddAppPickerProps {
  api: TilesApi
  data: AppTiles
  /** Called with the new tiles after an app was added. */
  onAdded: (data: AppTiles) => void
  onClose: () => void
}

/** "+ Add App": default apps to add back, Start Menu apps, or a website. */
export function AddAppPicker({ api, data, onAdded, onClose }: AddAppPickerProps) {
  const [tab, setTab] = useState<Tab>(data.hidden_defaults.length > 0 ? 'defaults' : 'installed')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  const run = async (action: () => Promise<AppTiles>) => {
    setBusy(true)
    setError(null)
    try {
      onAdded(await action())
    } catch (err) {
      setError(errorMessage(err, 'The app could not be added.'))
    } finally {
      setBusy(false)
    }
  }
  const add = (body: TileAdd) => run(() => api.add(body))

  const tabButton = (name: Tab, label: string) => (
    <GazeButton role="tab" aria-selected={tab === name} variant={tab === name ? 'default' : 'outline'}
      onClick={() => { setTab(name); setError(null) }}>
      {label}
    </GazeButton>
  )

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-black/40 p-6">
      <div role="dialog" aria-modal="true" aria-labelledby="add-app-title"
        className="bg-card text-card-foreground w-full max-w-5xl space-y-6 rounded-2xl border p-8 shadow-xl">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <h2 id="add-app-title" className="text-3xl font-bold">Add an app</h2>
          <GazeButton variant="outline" onClick={onClose}><X aria-hidden />Close</GazeButton>
        </div>
        <div role="tablist" aria-label="Kinds of apps" className="flex flex-wrap gap-6">
          {tabButton('defaults', 'Default apps')}
          {tabButton('installed', 'Installed apps')}
          {tabButton('website', 'Website')}
        </div>
        {error && (
          <Alert variant="destructive" role="alert"><AlertDescription className="text-lg">{error}</AlertDescription></Alert>
        )}

        {tab === 'defaults' && (
          data.hidden_defaults.length === 0 ? (
            <p className="text-muted-foreground text-xl">All the default apps are already on your Home screen.</p>
          ) : (
            <div className="grid grid-cols-[repeat(auto-fill,minmax(16rem,1fr))] gap-6">
              {data.hidden_defaults.map((d) => {
                const Icon = tileIcon(d.icon)
                return (
                  <GazeButton key={d.tile_id} variant="outline" disabled={busy}
                    onClick={() => void run(() => api.restore(d.tile_id))}>
                    <Icon aria-hidden /><RotateCcw aria-hidden />Add back {d.label}
                  </GazeButton>
                )
              })}
            </div>
          )
        )}
        {tab === 'installed' && <InstalledList api={api} busy={busy} onPick={(app) => void add({ kind: 'installed_app', path: app.path })} />}
        {tab === 'website' && <WebsiteForm data={data} busy={busy} onAdd={(label, url) => void add({ kind: 'website', label, url })} />}
      </div>
    </div>
  )
}

function InstalledList({ api, busy, onPick }: { api: TilesApi; busy: boolean; onPick: (app: InstalledApp) => void }) {
  const [apps, setApps] = useState<InstalledApp[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [query, setQuery] = useState('')
  const [shown, setShown] = useState(PAGE)

  useEffect(() => {
    let current = true
    api.available()
      .then((list) => current && setApps(list))
      .catch((err) => current && setError(errorMessage(err, 'The installed apps could not be listed.')))
    return () => {
      current = false
    }
  }, [api])

  if (error) return <Alert variant="destructive" role="alert"><AlertDescription className="text-lg">{error}</AlertDescription></Alert>
  if (!apps) return <LoaderCircle className="text-muted-foreground mx-auto size-12 animate-spin" aria-label="Looking for apps" />
  if (apps.length === 0) return <p className="text-muted-foreground text-xl">No apps were found in this computer’s Start Menu.</p>
  const matches = apps.filter((a) => a.name.toLowerCase().includes(query.trim().toLowerCase()))
  return (
    <div className="space-y-6">
      <div className="grid max-w-md gap-2">
        <Label htmlFor="app-search" className="text-lg">Search (optional)</Label>
        <Input id="app-search" className="h-12 text-lg" value={query} onChange={(e) => { setQuery(e.target.value); setShown(PAGE) }} />
      </div>
      {matches.length === 0 && <p className="text-muted-foreground text-xl">No app matches “{query}”.</p>}
      <div className="grid grid-cols-[repeat(auto-fill,minmax(18rem,1fr))] gap-6">
        {matches.slice(0, shown).map((app) => (
          <GazeButton key={app.path} variant="outline" disabled={busy} title={app.name}
            className="justify-start" onClick={() => onPick(app)}>
            <AppWindow aria-hidden /><span className="truncate">{app.name}</span>
          </GazeButton>
        ))}
      </div>
      {matches.length > shown && (
        <GazeButton variant="outline" onClick={() => setShown((n) => n + PAGE)}>
          Show more apps ({matches.length - shown} more)
        </GazeButton>
      )}
    </div>
  )
}

function WebsiteForm({ data, busy, onAdd }: { data: AppTiles; busy: boolean; onAdd: (label: string, url: string) => void }) {
  const [label, setLabel] = useState('')
  const [url, setUrl] = useState('')
  const [field, setField] = useState<'label' | 'url'>('label')

  const onKey = (key: string) => {
    if (key === 'ENTER') return
    if (field === 'label') setLabel((t) => typeKey(t, key, MAX_NAME))
    else setUrl((t) => typeKey(t, key, MAX_URL).toLowerCase())
  }

  return (
    <div className="space-y-6">
      <div className="space-y-3">
        <p className="text-xl font-semibold">Suggestions</p>
        <div className="flex flex-wrap gap-6">
          {data.suggestions.map((s) => {
            const Icon = tileIcon(s.icon)
            return (
              <GazeButton key={s.url} variant="outline" disabled={busy} onClick={() => onAdd(s.label, s.url)}>
                <Icon aria-hidden />{s.label}
              </GazeButton>
            )
          })}
        </div>
      </div>
      <div className="grid gap-6 md:grid-cols-2">
        {([['label', 'Name', label, setLabel], ['url', 'Website address', url, setUrl]] as const).map(([key, title, value, set]) => (
          <div key={key} className="grid gap-2">
            <Label htmlFor={`site-${key}`} className="text-lg">{title}</Label>
            <div className="flex gap-3">
              <Input id={`site-${key}`} value={value} maxLength={key === 'label' ? MAX_NAME : MAX_URL}
                placeholder={key === 'url' ? 'example.com' : 'My website'}
                className={cn('h-14 text-xl', field === key && 'ring-ring ring-4')}
                onFocus={() => setField(key)} onChange={(e) => set(e.target.value)} />
              <GazeButton variant={field === key ? 'default' : 'outline'} className="px-4" onClick={() => setField(key)}
                aria-label={`Type the ${title.toLowerCase()} with the keyboard below`}>
                <Globe aria-hidden />Type here
              </GazeButton>
            </div>
          </div>
        ))}
      </div>
      <p className="text-muted-foreground text-lg">
        Typing into: <strong>{field === 'label' ? 'Name' : 'Website address'}</strong>. Only http:// and https:// websites can be added.
      </p>
      <GazeKeyboard onKey={onKey} disabled={busy} />
      <GazeButton disabled={busy || !label.trim() || !url.trim()} onClick={() => onAdd(label, url)}>
        {busy ? <LoaderCircle className="animate-spin" aria-hidden /> : <Plus aria-hidden />}
        Add website
      </GazeButton>
    </div>
  )
}
