import { z } from 'zod'
import { appClient } from '@/api/app-client'

/** Natural-voice settings per user (clearer TTS). */
const voiceSchema = z.object({ id: z.string(), name: z.string(), gender: z.string(), accent: z.string() })
const settingsSchema = z.object({
  voice_en: z.string(),
  voice_fil: z.string(),
  rate: z.number(),
  pitch: z.number(),
  volume: z.number(),
  defaults: z.record(z.string(), z.union([z.string(), z.number()])),
  voices: z.object({ en: voiceSchema.array(), fil: voiceSchema.array() }),
  rate_range: z.tuple([z.number(), z.number()]),
  pitch_range: z.tuple([z.number(), z.number()]),
})
export type VoiceSettings = z.infer<typeof settingsSchema>
export type VoiceChoice = z.infer<typeof voiceSchema>
export type VoiceSettingsChange = Partial<Pick<VoiceSettings, 'voice_en' | 'voice_fil' | 'rate' | 'pitch'>>

export interface VoiceSettingsApi {
  load: () => Promise<VoiceSettings>
  save: (change: VoiceSettingsChange) => Promise<VoiceSettings>
  reset: () => Promise<VoiceSettings>
  /** Only the user can preview: the voice plays on their own computer. */
  canPreview: boolean
}

function api(base: string, canPreview: boolean): VoiceSettingsApi {
  const parse = (r: { data: unknown }) => settingsSchema.parse(r.data)
  return {
    load: () => appClient.get(base).then(parse),
    save: (change) => appClient.put(base, change).then(parse),
    reset: () => appClient.post(`${base}/reset`).then(parse),
    canPreview,
  }
}

export const myVoiceSettings = api('/me/voice-settings', true)
export const voiceSettingsForUser = (userId: number) => api(`/admin/users/${userId}/voice-settings`, false)
