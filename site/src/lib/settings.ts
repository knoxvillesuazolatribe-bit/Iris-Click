import type { AccessibilityValues } from '@/validators/settings-validator'

export const SETTING_KEYS: (keyof AccessibilityValues)[] = [
  'dwell_enabled', 'dwell_ms', 'smoothing', 'blink_to_click', 'blink_sensitivity', 'edge_scroll_enabled', 'voice_volume',
]

/** Only the editable values from a settings response. */
export const pickValues = <T extends AccessibilityValues>(s: T): AccessibilityValues =>
  Object.fromEntries(SETTING_KEYS.map((k) => [k, s[k]])) as AccessibilityValues
