import { Volume2 } from 'lucide-react'
import { GazeButton } from '@/components/gaze-button'
import { Choice, OnOff, SettingRow, Stepper } from '@/components/setting-controls'
import { speak } from '@/lib/speech'
import { BLINK_STEPS, DWELL_MS, VOLUME, type AccessibilityValues } from '@/validators/settings-validator'

const BLINK_LABELS = ['Least sensitive', 'Less sensitive', 'Standard', 'More sensitive', 'Most sensitive']

interface AccessibilityFieldsProps {
  draft: AccessibilityValues
  set: <K extends keyof AccessibilityValues>(key: K, value: AccessibilityValues[K]) => void
}

/** The accessibility settings rows, shared by the user's page and the admin pages. */
export function AccessibilityFields({ draft, set }: AccessibilityFieldsProps) {
  return (
    <>
      <SettingRow title="Dwell click" description="Click by keeping your eyes on one spot."
        note={!draft.blink_to_click ? 'Stays on while wink-to-click is off, so you can always click.' : undefined}>
        <OnOff label="Dwell click" value={draft.dwell_enabled} offDisabled={!draft.blink_to_click}
          onChange={(v) => set('dwell_enabled', v)} />
      </SettingRow>

      <SettingRow title="Dwell time" description="How long to look before a dwell click.">
        <Stepper label="dwell time" value={draft.dwell_ms} min={DWELL_MS.min} max={DWELL_MS.max} step={DWELL_MS.step}
          format={(v) => `${(v / 1000).toFixed(1)} s`} onChange={(v) => set('dwell_ms', v)} />
      </SettingRow>

      <SettingRow title="Cursor smoothing" description="High is steadier but follows the eyes a little slower.">
        <Choice label="Cursor smoothing" value={draft.smoothing} onChange={(v) => set('smoothing', v)}
          options={[{ value: 'low', label: 'Low' }, { value: 'medium', label: 'Medium' }, { value: 'high', label: 'High' }]} />
      </SettingRow>

      <SettingRow title="Wink to click" description="A left-eye wink clicks."
        note={!draft.dwell_enabled ? 'Turn on dwell click first to turn this off.' : undefined}>
        <OnOff label="Wink to click" value={draft.blink_to_click} offDisabled={!draft.dwell_enabled}
          onChange={(v) => set('blink_to_click', v)} />
      </SettingRow>

      <SettingRow title="Blink sensitivity" description="More sensitive: a smaller wink counts, but accidental winks happen more.">
        <Stepper label="blink sensitivity" value={draft.blink_sensitivity} min={BLINK_STEPS.min} max={BLINK_STEPS.max}
          format={(v) => BLINK_LABELS[v - 1]} onChange={(v) => set('blink_sensitivity', v)} />
      </SettingRow>

      <SettingRow title="Edge scroll" description="Look at the top or bottom edge of the screen to scroll.">
        <OnOff label="Edge scroll" value={draft.edge_scroll_enabled} onChange={(v) => set('edge_scroll_enabled', v)} />
      </SettingRow>

      <SettingRow title="Voice volume" description="How loud Voice Communication speaks.">
        <Stepper label="voice volume" value={draft.voice_volume} min={VOLUME.min} max={VOLUME.max} step={VOLUME.step}
          format={(v) => `${v}%`} onChange={(v) => set('voice_volume', v)} />
        <GazeButton variant="outline" onClick={() => speak('This is how loud I will speak.', draft.voice_volume)}>
          <Volume2 aria-hidden />
          Test
        </GazeButton>
      </SettingRow>
    </>
  )
}
