import { Download, LoaderCircle, Plus, RotateCcw, Search, Trash2, Upload } from 'lucide-react'
import { useCallback, useEffect, useRef, useState, type FormEvent } from 'react'
import { Link } from 'react-router'
import { errorMessage } from '@/api/app-client'
import { AdminLayout } from '@/components/admin-layout'
import { ConfirmDialog } from '@/components/confirm-dialog'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  wordFilterService, WORD_LANGUAGES, type FilterSettings, type FilterWord, type WordLanguage, type WordQuery, type WordType,
} from '@/services/word-filter-service'

const LANGUAGE_NAMES: Record<WordLanguage, string> = { en: 'English', fil: 'Filipino', other: 'Other' }
const SELECT = 'border-input bg-background h-10 rounded-md border px-3'
const MAX_FILE_BYTES = 1_000_000
type Notice = { kind: 'ok' | 'error'; text: string } | null

/** Extension of Screens 25–28: the word filter for Voice Communication. */
export function AdminWordFilterPage() {
  const [settings, setSettings] = useState<FilterSettings | null>(null)
  const [query, setQuery] = useState<WordQuery>({ q: '', language: '', type: '', status: 'active' })
  const [words, setWords] = useState<FilterWord[] | null>(null)
  const [notice, setNotice] = useState<Notice>(null)
  const [busy, setBusy] = useState(false)
  const [removing, setRemoving] = useState<FilterWord | null>(null)
  const [newWord, setNewWord] = useState('')
  const [newLanguage, setNewLanguage] = useState<WordLanguage>('en')
  const [newType, setNewType] = useState<WordType>('blocked')
  const fileInput = useRef<HTMLInputElement>(null)

  const reload = useCallback((q: WordQuery) => {
    wordFilterService.words(q)
      .then(setWords)
      .catch((err) => setNotice({ kind: 'error', text: errorMessage(err, 'The word list could not be loaded.') }))
  }, [])

  useEffect(() => {
    wordFilterService.settings()
      .then(setSettings)
      .catch((err) => setNotice({ kind: 'error', text: errorMessage(err, 'The filter settings could not be loaded.') }))
  }, [])
  useEffect(() => reload(query), [reload, query])

  const run = async (action: () => Promise<string>, failText: string) => {
    setBusy(true)
    setNotice(null)
    try {
      setNotice({ kind: 'ok', text: await action() })
      reload(query)
      return true
    } catch (err) {
      setNotice({ kind: 'error', text: errorMessage(err, failText) })
      return false
    } finally {
      setBusy(false)
    }
  }

  const saveSettings = (change: Partial<FilterSettings>) =>
    void run(async () => {
      const next = await wordFilterService.saveSettings(change)
      setSettings(next)
      return `Word filter is ${next.enabled ? 'on' : 'off'}; masked words are ${next.tts_mode === 'beep' ? 'spoken as “beep”' : 'skipped'}.`
    }, 'The setting was not saved.')

  const addWord = (e: FormEvent) => {
    e.preventDefault()
    void run(async () => {
      const added = await wordFilterService.add(newWord, newLanguage, newType)
      setNewWord('')
      return `Added word #${added.word_id} as ${added.type}.`
    }, 'The word was not added.')
  }

  const importFile = (file: File | undefined) => {
    if (!file) return
    if (file.size > MAX_FILE_BYTES) {
      setNotice({ kind: 'error', text: 'That file is too large. Import up to 1 MB at a time.' })
      return
    }
    void run(async () => {
      const r = await wordFilterService.importText(await file.text())
      return `Import finished: ${r.added} added, ${r.restored} restored, ${r.skipped} skipped (already listed or not a word).`
    }, 'The file could not be imported.').finally(() => {
      if (fileInput.current) fileInput.current.value = ''
    })
  }

  const exportFile = (format: 'csv' | 'txt') =>
    void run(async () => `Exported ${await wordFilterService.exportFile(format)}. Check your browser’s downloads.`,
      'The list could not be exported.')

  const setFilter = (change: Partial<WordQuery>) => setQuery((q) => ({ ...q, ...change }))

  return (
    <AdminLayout title="Word Filter"
      description="Extension: masks blocked words in Voice Communication before they are spoken or saved. SOS alerts are never filtered."
      actions={<Button asChild variant="outline"><Link to="/admin/settings">All settings</Link></Button>}>
      {notice && (
        <Alert variant={notice.kind === 'error' ? 'destructive' : 'default'} role="status">
          <AlertDescription>{notice.text}</AlertDescription>
        </Alert>
      )}

      <Card>
        <CardHeader>
          <CardTitle>Settings</CardTitle>
          <CardDescription>Applies to typed messages, Quick Phrases, the board and speech to text.</CardDescription>
        </CardHeader>
        <CardContent className="flex flex-wrap gap-8">
          {settings ? (
            <>
              <div className="grid gap-2">
                <span className="text-sm font-medium">Filter</span>
                <div className="flex gap-2" role="group" aria-label="Filter on or off">
                  <Button variant={settings.enabled ? 'default' : 'outline'} aria-pressed={settings.enabled} disabled={busy}
                    onClick={() => saveSettings({ enabled: true })}>On</Button>
                  <Button variant={!settings.enabled ? 'default' : 'outline'} aria-pressed={!settings.enabled} disabled={busy}
                    onClick={() => saveSettings({ enabled: false })}>Off</Button>
                </div>
              </div>
              <div className="grid gap-2">
                <span className="text-sm font-medium">When speaking a masked word</span>
                <div className="flex gap-2" role="group" aria-label="When speaking a masked word">
                  <Button variant={settings.tts_mode === 'beep' ? 'default' : 'outline'} aria-pressed={settings.tts_mode === 'beep'}
                    disabled={busy} onClick={() => saveSettings({ tts_mode: 'beep' })}>Say “beep”</Button>
                  <Button variant={settings.tts_mode === 'skip' ? 'default' : 'outline'} aria-pressed={settings.tts_mode === 'skip'}
                    disabled={busy} onClick={() => saveSettings({ tts_mode: 'skip' })}>Skip the word</Button>
                </div>
              </div>
            </>
          ) : (
            <LoaderCircle className="text-muted-foreground animate-spin" aria-label="Loading settings" />
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Add a word</CardTitle>
          <CardDescription>
            Matching ignores case, accents, leetspeak (@ 4 3 1 ! 0 $ 5), stretched and split letters, and only whole words.
            An allowed word is never masked, even if it looks like a blocked one.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={addWord} className="flex flex-wrap items-end gap-4">
            <div className="grid gap-1">
              <Label htmlFor="wf-word">Word or phrase</Label>
              <Input id="wf-word" className="h-10 w-64" maxLength={100} value={newWord} onChange={(e) => setNewWord(e.target.value)} />
            </div>
            <div className="grid gap-1">
              <Label htmlFor="wf-language">Language</Label>
              <select id="wf-language" className={SELECT} value={newLanguage} onChange={(e) => setNewLanguage(e.target.value as WordLanguage)}>
                {WORD_LANGUAGES.map((l) => <option key={l} value={l}>{LANGUAGE_NAMES[l]}</option>)}
              </select>
            </div>
            <div className="grid gap-1">
              <Label htmlFor="wf-type">Type</Label>
              <select id="wf-type" className={SELECT} value={newType} onChange={(e) => setNewType(e.target.value as WordType)}>
                <option value="blocked">Blocked (masked)</option>
                <option value="allowed">Allowed (never masked)</option>
              </select>
            </div>
            <Button type="submit" disabled={busy || !newWord.trim()}><Plus aria-hidden />Add</Button>
          </form>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Word list</CardTitle>
          <CardDescription>Removed words stay in the list as “Removed” and can be restored.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex flex-wrap items-end gap-4">
            <div className="grid gap-1">
              <Label htmlFor="wf-search">Search</Label>
              <div className="relative">
                <Search className="text-muted-foreground absolute top-2.5 left-2.5 size-4" aria-hidden />
                <Input id="wf-search" className="h-10 w-56 pl-8" value={query.q} onChange={(e) => setFilter({ q: e.target.value })} />
              </div>
            </div>
            <div className="grid gap-1">
              <Label htmlFor="wf-filter-language">Language</Label>
              <select id="wf-filter-language" className={SELECT} value={query.language}
                onChange={(e) => setFilter({ language: e.target.value as WordQuery['language'] })}>
                <option value="">All</option>
                {WORD_LANGUAGES.map((l) => <option key={l} value={l}>{LANGUAGE_NAMES[l]}</option>)}
              </select>
            </div>
            <div className="grid gap-1">
              <Label htmlFor="wf-filter-type">Type</Label>
              <select id="wf-filter-type" className={SELECT} value={query.type}
                onChange={(e) => setFilter({ type: e.target.value as WordQuery['type'] })}>
                <option value="">All</option>
                <option value="blocked">Blocked</option>
                <option value="allowed">Allowed</option>
              </select>
            </div>
            <div className="grid gap-1">
              <Label htmlFor="wf-filter-status">Status</Label>
              <select id="wf-filter-status" className={SELECT} value={query.status}
                onChange={(e) => setFilter({ status: e.target.value as WordQuery['status'] })}>
                <option value="active">In use</option>
                <option value="removed">Removed</option>
                <option value="all">All</option>
              </select>
            </div>
            <div className="ml-auto flex flex-wrap gap-2">
              <input ref={fileInput} type="file" accept=".txt,.csv,text/plain,text/csv" className="hidden"
                aria-label="Import a .txt or .csv file" onChange={(e) => importFile(e.target.files?.[0])} />
              <Button variant="outline" disabled={busy} onClick={() => fileInput.current?.click()}><Upload aria-hidden />Import .txt / .csv</Button>
              <Button variant="outline" disabled={busy} onClick={() => exportFile('csv')}><Download aria-hidden />Export .csv</Button>
              <Button variant="outline" disabled={busy} onClick={() => exportFile('txt')}><Download aria-hidden />Export .txt</Button>
            </div>
          </div>
          <p className="text-muted-foreground text-sm">
            Import format: one <code>word,language</code> per line (language en, fil or other; optional third column blocked or allowed).
          </p>

          {!words ? (
            <LoaderCircle className="text-muted-foreground animate-spin" aria-label="Loading words" />
          ) : words.length === 0 ? (
            <p className="text-muted-foreground">No words match these filters.</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead className="text-muted-foreground border-b">
                  <tr><th className="py-2 pr-4">#</th><th className="py-2 pr-4">Word</th><th className="py-2 pr-4">Language</th>
                    <th className="py-2 pr-4">Type</th><th className="py-2 pr-4">Status</th><th className="py-2" /></tr>
                </thead>
                <tbody>
                  {words.map((w) => (
                    <tr key={w.word_id} className="border-b last:border-0">
                      <td className="text-muted-foreground py-2 pr-4">{w.word_id}</td>
                      <td className="py-2 pr-4 font-medium break-all">{w.word}</td>
                      <td className="py-2 pr-4">{LANGUAGE_NAMES[w.language]}</td>
                      <td className="py-2 pr-4"><Badge variant={w.type === 'blocked' ? 'destructive' : 'secondary'}>{w.type === 'blocked' ? 'Blocked' : 'Allowed'}</Badge></td>
                      <td className="py-2 pr-4">{w.is_active ? 'In use' : 'Removed'}</td>
                      <td className="py-2 text-right">
                        {w.is_active ? (
                          <Button size="sm" variant="outline" disabled={busy} onClick={() => setRemoving(w)}><Trash2 aria-hidden />Remove</Button>
                        ) : (
                          <Button size="sm" variant="outline" disabled={busy}
                            onClick={() => void run(async () => `Restored word #${(await wordFilterService.restore(w.word_id)).word_id}.`, 'The word was not restored.')}>
                            <RotateCcw aria-hidden />Restore
                          </Button>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <p className="text-muted-foreground mt-2 text-sm">{words.length} word(s).</p>
            </div>
          )}
        </CardContent>
      </Card>

      {removing && (
        <ConfirmDialog
          title={`Remove word #${removing.word_id} from the filter?`}
          text="It stops being masked right away. You can restore it later."
          confirmLabel="Yes, remove"
          busy={busy}
          onCancel={() => setRemoving(null)}
          onConfirm={() => void run(async () => `Removed word #${(await wordFilterService.remove(removing.word_id)).word_id}.`,
            'The word was not removed.').then(() => setRemoving(null))}
        />
      )}
    </AdminLayout>
  )
}
