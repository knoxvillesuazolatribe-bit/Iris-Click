import { LoaderCircle, Play, RotateCcw } from 'lucide-react'
import { useEffect, useState } from 'react'
import { errorMessage } from '@/api/app-client'
import { GazeButton } from '@/components/gaze-button'
import { Choice, SettingRow, Stepper } from '@/components/setting-controls'
import { TwoPressButton } from '@/components/two-press-button'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { player } from '@/lib/natural-voice'
import type { SpeechLang } from '@/lib/voices'
import type { VoiceChoice, VoiceSettings, VoiceSettingsApi, VoiceSettingsChange } from '@/services/voice-settings-service'

const SAMPLES: Record<SpeechLang, string> = {
  en: 'Hello, this is how I will sound.',
  fil: 'Kumusta, ganito ang aking boses.',
}
const SPEEDS = [{ value: '-25', label: 'Slower' }, { value: '-10', label: 'Normal' }, { value: '10', label: 'Faster' }]
const PITCHES = [{ value: '-10', label: 'Lower' }, { value: '0', label: 'Normal' }, { value: '10', label: 'Higher' }]
const RATE_STEP = 5

const voiceLabel = (v: VoiceChoice) => `${v.gender === 'female' ? 'Female' : 'Male'} · ${v.name}${v.accent === 'US English' ? ' (US)' : ''}`
const signed = (v: number, unit: string) => `${v > 0 ? '+' : ''}${v}${unit}`

interface VoiceSettingsPanelProps {
  api: VoiceSettingsApi
  /** The volume to preview with (the Voice volume setting, possibly not saved yet). */
  volume?: number
}

/** Settings → Voice: natural voice, speed and pitch, with a Preview (clearer TTS). */
export function VoiceSettingsPanel({ api, volume }: VoiceSettingsPanelProps) {
  const [settings, setSettings] = useState<VoiceSettings | null>(null)
  const [busy, setBusy] = useState(false)
  const [notice, setNotice] = useState<{ kind: 'ok' | 'error'; text: string } | null>(null)

  useEffect(() => {
    api.load()
      .then(setSettings)
      .catch((err) => setNotice({ kind: 'error', text: errorMessage(err, 'The voice settings could not be loaded.') }))
  }, [api])

  const run = async (action: () => Promise<VoiceSettings>, done: string) => {
    setBusy(true)
    setNotice(null)
    try {
      setSettings(await action())
      setNotice({ kind: 'ok', text: done })
    } catch (err) {
      setNotice({ kind: 'error', text: errorMessage(err, 'The voice settings were not saved.') })
    } finally {
      setBusy(false)
    }
  }
  const save = (change: VoiceSettingsChange) => void run(() => api.save(change), 'Voice settings saved.')

  const preview = (lang: SpeechLang) => {
    if (!settings) return
    const voice = lang === 'fil' ? settings.voice_fil : settings.voice_en
    void player.speak(SAMPLES[lang], lang, volume ?? settings.volume, { voice, rate: settings.rate, pitch: settings.pitch })
      .then((r) => !r.ok && setNotice({ kind: 'error', text: r.error }))
  }

  if (!settings) {
    return notice ? (
      <Alert variant="destructive" role="alert"><AlertDescription className="text-lg">{notice.text}</AlertDescription></Alert>
    ) : <LoaderCircle className="text-muted-foreground mx-auto size-10 animate-spin" aria-label="Loading voice settings" />
  }

  const [rateMin, rateMax] = settings.rate_range
  return (
    <section aria-labelledby="voice-settings" className="space-y-6">
      <h2 id="voice-settings" className="text-3xl font-bold">Voice</h2>
      {notice && (
        <Alert variant={notice.kind === 'error' ? 'destructive' : 'default'} role="status">
          <AlertDescription className="text-lg">{notice.text}</AlertDescription>
        </Alert>
      )}
      <SettingRow title="English voice" description="Natural voice for English. Philippine English is easiest to follow.">
        <Choice label="English voice" value={settings.voice_en}
          options={settings.voices.en.map((v) => ({ value: v.id, label: voiceLabel(v), disabled: busy }))}
          onChange={(voice_en) => save({ voice_en })} />
      </SettingRow>
      <SettingRow title="Filipino voice" description="Natural voice for Filipino.">
        <Choice label="Filipino voice" value={settings.voice_fil}
          options={settings.voices.fil.map((v) => ({ value: v.id, label: voiceLabel(v), disabled: busy }))}
          onChange={(voice_fil) => save({ voice_fil })} />
      </SettingRow>
      <SettingRow title="Speed" description={`How fast the voice talks (now ${signed(settings.rate, '%')}). Normal is a little slower than usual, for clarity.`}>
        <div className="flex flex-wrap items-center gap-6">
          <Choice label="Speed" value={String(settings.rate)}
            options={SPEEDS.map((s) => ({ ...s, disabled: busy }))} onChange={(v) => save({ rate: Number(v) })} />
          <Stepper label="speed" value={settings.rate} min={rateMin} max={rateMax} step={RATE_STEP} disabled={busy}
            format={(v) => signed(v, '%')} onChange={(rate) => save({ rate })} />
        </div>
      </SettingRow>
      <SettingRow title="Pitch" description="How high or low the voice sounds.">
        <Choice label="Pitch" value={String(settings.pitch)}
          options={PITCHES.map((p) => ({ ...p, disabled: busy }))} onChange={(v) => save({ pitch: Number(v) })} />
      </SettingRow>
      <SettingRow title="Volume" description={`Uses the Voice volume setting${volume === undefined ? ` (${settings.volume}%)` : ' above'}.`}>
        {api.canPreview ? (
          <div className="flex flex-wrap gap-6">
            <GazeButton className="min-h-24 text-2xl" disabled={busy} onClick={() => preview('en')}><Play aria-hidden />Preview English</GazeButton>
            <GazeButton className="min-h-24 text-2xl" disabled={busy} onClick={() => preview('fil')}><Play aria-hidden />Preview Filipino</GazeButton>
          </div>
        ) : <span className="text-muted-foreground text-lg">The person can preview the voice on their own Settings page.</span>}
      </SettingRow>
      <TwoPressButton icon={RotateCcw} label="Reset voice to default" confirmLabel="Yes, reset voice" disabled={busy}
        onConfirm={() => void run(() => api.reset(), 'Voice settings are back to default.')} />
    </section>
  )
}
