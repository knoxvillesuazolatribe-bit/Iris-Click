import { AppWindow, Check, ChevronLeft, ChevronRight, LoaderCircle, Pencil, Plus, RotateCcw, X } from 'lucide-react'
import { Component, useCallback, useEffect, useRef, useState, type ReactNode } from 'react'
import { errorMessage } from '@/api/app-client'
import { AddAppPicker } from '@/components/add-app-picker'
import { tileIcon } from '@/components/app-tile-icon'
import { ConfirmDialog } from '@/components/confirm-dialog'
import { GazeButton } from '@/components/gaze-button'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { ONLINE_COPY } from '@/lib/online-copy'
import { cn } from '@/lib/utils'
import type { AppTile, AppTiles, TilesApi } from '@/services/user-apps-service'

const FLASH_MS = 2000
const LONG_NAME = 18

/** Online copy: tiles the server answers with a web address (websites, Browser, Calendar website). */
const mayBeWebsite = (tile: AppTile) =>
  tile.kind === 'website' || (tile.kind === 'builtin' && (tile.icon === 'browser' || tile.icon === 'calendar'))

type Flash = { tileId: number; kind: 'ok' | 'error'; text: string }
type Ask = { kind: 'remove'; tile: AppTile } | { kind: 'reset' } | null

interface UserAppTilesProps {
  api: TilesApi
  /** Home: tiles open apps and "Edit Apps" switches to edit mode. Admin: always editing. */
  variant?: 'home' | 'admin'
  /** Shown instead when the tiles cannot load (the Phase 9 tiles on Home). */
  fallback?: ReactNode
}

/** Customizable Apps section (extension): open, remove, move, add and reset tiles. */
export function UserAppTiles(props: UserAppTilesProps) {
  return (
    <TilesBoundary fallback={props.fallback ?? null}>
      <Tiles {...props} />
    </TilesBoundary>
  )
}

class TilesBoundary extends Component<{ fallback: ReactNode; children: ReactNode }, { failed: boolean }> {
  state = { failed: false }
  static getDerivedStateFromError() {
    return { failed: true }
  }
  render() {
    return this.state.failed ? this.props.fallback : this.props.children
  }
}

function Tiles({ api, variant = 'home', fallback }: UserAppTilesProps) {
  const home = variant === 'home'
  const [data, setData] = useState<AppTiles | null>(null)
  const [loadFailed, setLoadFailed] = useState(false)
  const [editing, setEditing] = useState(!home)
  const [picking, setPicking] = useState(false)
  const [ask, setAsk] = useState<Ask>(null)
  const [busy, setBusy] = useState(false)
  const [flash, setFlash] = useState<Flash | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const timer = useRef<number | undefined>(undefined)
  useEffect(() => () => window.clearTimeout(timer.current), [])

  useEffect(() => {
    let current = true
    api.overview()
      .then((d) => current && setData(d))
      .catch(() => current && setLoadFailed(true))
    return () => {
      current = false
    }
  }, [api])

  const change = async (action: () => Promise<AppTiles | void>) => {
    setBusy(true)
    setNotice(null)
    try {
      const next = await action()
      setData(next ?? (await api.overview()))
      return true
    } catch (err) {
      setNotice(errorMessage(err, 'That change was not saved.'))
      return false
    } finally {
      setBusy(false)
    }
  }

  const open = async (tile: AppTile) => {
    if (!api.launch) return
    window.clearTimeout(timer.current)
    setFlash({ tileId: tile.tile_id, kind: 'ok', text: `Opening ${tile.label}…` })
    setNotice(null)
    // Online copy hook: websites open in a new tab on this device. The tab is opened
    // during the click (pop-up blockers allow that) and filled once the address arrives.
    const tab = ONLINE_COPY && mayBeWebsite(tile) ? window.open('', '_blank') : null
    try {
      const result = await api.launch(tile.tile_id)
      if (tab) {
        if (result.url) {
          tab.opener = null
          tab.location.href = result.url
        } else tab.close()
      } else if (ONLINE_COPY && result.url) {
        // The browser blocked the new tab: open it here; Back returns to IrisClick.
        window.location.assign(result.url)
      }
      timer.current = window.setTimeout(() => setFlash(null), FLASH_MS)
    } catch (err) {
      tab?.close()
      setFlash({ tileId: tile.tile_id, kind: 'error', text: errorMessage(err, `${tile.label} could not be opened.`) })
    }
  }

  const closePicker = useCallback(() => setPicking(false), [])
  const cancelAsk = useCallback(() => setAsk(null), [])

  if (loadFailed) return <>{fallback}</>
  if (!data) {
    return home ? null : <LoaderCircle className="text-muted-foreground size-10 animate-spin" aria-label="Loading apps" />
  }

  const full = data.tiles.length >= data.max_tiles
  const showAdd = editing || data.tiles.length === 0
  return (
    <section aria-labelledby={`apps-${variant}`} className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <h2 id={`apps-${variant}`} className="flex items-center gap-3 text-2xl font-bold">
          <AppWindow className="size-8" aria-hidden />
          Apps
        </h2>
        <div className="flex flex-wrap gap-6">
          {editing && (
            <GazeButton variant="outline" disabled={busy} onClick={() => setAsk({ kind: 'reset' })}>
              <RotateCcw aria-hidden />Reset to default
            </GazeButton>
          )}
          {home && (editing ? (
            <GazeButton onClick={() => { setEditing(false); setNotice(null) }}><Check aria-hidden />Done</GazeButton>
          ) : (
            <GazeButton variant="outline" onClick={() => { setEditing(true); setFlash(null) }}><Pencil aria-hidden />Edit Apps</GazeButton>
          ))}
        </div>
      </div>

      {notice && (
        <Alert variant="destructive" role="alert"><AlertDescription className="text-lg">{notice}</AlertDescription></Alert>
      )}
      {editing && full && (
        <Alert role="status">
          <AlertDescription className="text-lg">
            You have {data.max_tiles} apps, the most allowed. Remove one to add another.
          </AlertDescription>
        </Alert>
      )}

      <ul className="grid grid-cols-[repeat(auto-fill,minmax(13rem,1fr))] gap-6">
        {data.tiles.map((tile, index) => {
          const Icon = tileIcon(tile.icon)
          const tileFlash = flash?.tileId === tile.tile_id ? flash : null
          const problem = tileFlash?.kind === 'error' ? tileFlash.text : tile.problem
          return (
            <li key={tile.tile_id} className="flex flex-col gap-3">
              <button
                type="button"
                title={tile.label}
                disabled={editing || !home || flash?.kind === 'ok'}
                onClick={() => void open(tile)}
                className={cn(
                  'bg-card border-primary flex min-h-28 flex-1 flex-col items-center justify-center gap-2 rounded-2xl border-2 p-4 text-center',
                  'outline-none disabled:cursor-default',
                  !editing && home && 'hover:ring-ring/70 focus-visible:ring-ring hover:ring-4 focus-visible:ring-4',
                  (problem || !tile.available) && 'border-destructive',
                )}
              >
                {tileFlash?.kind === 'ok'
                  ? <LoaderCircle className="text-primary size-10 animate-spin" aria-hidden />
                  : <Icon className="text-primary size-10" aria-hidden />}
                <span className="line-clamp-2 text-xl font-semibold break-words" aria-live="polite">
                  {tileFlash?.kind === 'ok' ? tileFlash.text : tile.label}
                </span>
                {tile.note && !tileFlash && <span className="text-muted-foreground text-sm">{tile.note}</span>}
              </button>
              {tile.label.length > LONG_NAME && <p className="text-center text-base break-words">{tile.label}</p>}
              {problem && (
                <p role="alert" className="text-destructive text-center text-base font-semibold">{problem}</p>
              )}
              {(editing || problem) && (
                <GazeButton variant="destructive" disabled={busy} onClick={() => setAsk({ kind: 'remove', tile })}>
                  <X aria-hidden />Remove
                </GazeButton>
              )}
              {editing && (
                <div className="grid grid-cols-2 gap-3">
                  <GazeButton variant="outline" className="px-2 text-lg" disabled={busy || index === 0}
                    aria-label={`Move ${tile.label} left`}
                    onClick={() => void change(() => api.move(tile.tile_id, index - 1))}>
                    <ChevronLeft aria-hidden />Move
                  </GazeButton>
                  <GazeButton variant="outline" className="px-2 text-lg" disabled={busy || index === data.tiles.length - 1}
                    aria-label={`Move ${tile.label} right`}
                    onClick={() => void change(() => api.move(tile.tile_id, index + 1))}>
                    Move<ChevronRight aria-hidden />
                  </GazeButton>
                </div>
              )}
            </li>
          )
        })}
        {showAdd && (
          <li>
            <button
              type="button"
              disabled={full || busy}
              onClick={() => setPicking(true)}
              className={cn(
                'border-primary text-primary flex min-h-28 w-full flex-col items-center justify-center gap-2 rounded-2xl border-2 border-dashed p-4',
                'hover:ring-ring/70 focus-visible:ring-ring outline-none hover:ring-4 focus-visible:ring-4 disabled:opacity-50',
              )}
            >
              <Plus className="size-10" aria-hidden />
              <span className="text-xl font-semibold">Add App</span>
            </button>
          </li>
        )}
      </ul>

      {picking && (
        <AddAppPicker api={api} data={data} onClose={closePicker}
          onAdded={(next) => { setData(next); setPicking(false) }} />
      )}
      {ask?.kind === 'remove' && (
        <ConfirmDialog
          title={`Remove ${ask.tile.label} from ${home ? 'your' : 'their'} apps?`}
          text={ask.tile.kind === 'builtin' ? 'You can add it back later with Add App.' : undefined}
          confirmLabel="Yes, remove"
          busy={busy}
          onCancel={cancelAsk}
          onConfirm={() => void change(() => api.remove(ask.tile.tile_id)).then(() => { setAsk(null); setFlash(null) })}
        />
      )}
      {ask?.kind === 'reset' && (
        <ConfirmDialog
          title="Reset to the default apps?"
          text="The original apps come back. Apps and websites you added are removed."
          confirmLabel="Yes, reset"
          busy={busy}
          onCancel={cancelAsk}
          onConfirm={() => void change(() => api.reset()).then(() => setAsk(null))}
        />
      )}
    </section>
  )
}
