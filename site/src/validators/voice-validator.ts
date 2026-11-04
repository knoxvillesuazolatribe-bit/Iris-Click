import { z } from 'zod'

export const MAX_MESSAGE_CHARS = 1000

export const communicationModeSchema = z.enum(['text_to_speech', 'speech_to_text'])
export type CommunicationMode = z.infer<typeof communicationModeSchema>

export const communicationSchema = z.object({
  communication_id: z.number().int(),
  mode: communicationModeSchema,
  message: z.string(),
  date_created: z.string(),
})
export type Communication = z.infer<typeof communicationSchema>

export const voiceSchema = z.object({
  voice_volume: z.number().int(),
  messages: z.array(communicationSchema),
})
export type Voice = z.infer<typeof voiceSchema>
