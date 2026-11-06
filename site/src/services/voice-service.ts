import { appClient } from '@/api/app-client'
import { communicationSchema, voiceSchema, type CommunicationMode } from '@/validators/voice-validator'

/** Voice Communication; every call needs a signed-in assistive user. */
export const voiceService = {
  getVoice: () => appClient.get('/me/voice').then((r) => voiceSchema.parse(r.data)),
  send: (mode: CommunicationMode, message: string, language?: 'en' | 'fil') =>
    appClient
      .post('/me/communications', { mode, message, ...(language ? { language } : {}) })
      .then((r) => communicationSchema.parse(r.data)),
  remove: (communicationId: number) => appClient.delete(`/me/communications/${communicationId}`).then(() => undefined),
}
