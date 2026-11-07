import { z } from 'zod'
import { appClient } from '@/api/app-client'
import type { SpeechLang } from '@/lib/voices'

/** Speech language, saved per user (extension). */
const languageSchema = z.object({ language: z.enum(['en', 'fil']) })

export const languageService = {
  mine: () => appClient.get('/me/language').then((r) => languageSchema.parse(r.data).language),
  saveMine: (language: SpeechLang) =>
    appClient.put('/me/language', { language }).then((r) => languageSchema.parse(r.data).language),
  forUser: (userId: number) =>
    appClient.get(`/admin/users/${userId}/language`).then((r) => languageSchema.parse(r.data).language),
  saveForUser: (userId: number, language: SpeechLang) =>
    appClient.put(`/admin/users/${userId}/language`, { language }).then((r) => languageSchema.parse(r.data).language),
}
