import { z } from 'zod'
import { appClient } from '@/api/app-client'

/** Admin: Manage Settings > Word Filter (extension). */
export const WORD_LANGUAGES = ['en', 'fil', 'other'] as const
export type WordLanguage = (typeof WORD_LANGUAGES)[number]
export type WordType = 'blocked' | 'allowed'

const wordSchema = z.object({
  word_id: z.number(),
  word: z.string(),
  language: z.enum(WORD_LANGUAGES),
  type: z.enum(['blocked', 'allowed']),
  is_active: z.boolean(),
  created_at: z.string(),
})
export type FilterWord = z.infer<typeof wordSchema>

const settingsSchema = z.object({ enabled: z.boolean(), tts_mode: z.enum(['beep', 'skip']) })
export type FilterSettings = z.infer<typeof settingsSchema>

export interface WordQuery {
  q: string
  language: WordLanguage | ''
  type: WordType | ''
  status: 'active' | 'removed' | 'all'
}

const BASE = '/admin/word-filter'

export const wordFilterService = {
  settings: () => appClient.get(`${BASE}/settings`).then((r) => settingsSchema.parse(r.data)),
  saveSettings: (change: Partial<FilterSettings>) =>
    appClient.put(`${BASE}/settings`, change).then((r) => settingsSchema.parse(r.data)),
  words: (q: WordQuery) =>
    appClient
      .get(`${BASE}/words`, {
        params: { q: q.q.trim() || undefined, language: q.language || undefined, type: q.type || undefined, status: q.status },
      })
      .then((r) => wordSchema.array().parse(r.data)),
  add: (word: string, language: WordLanguage, type: WordType) =>
    appClient.post(`${BASE}/words`, { word, language, type }).then((r) => wordSchema.parse(r.data)),
  remove: (id: number) => appClient.delete(`${BASE}/words/${id}`).then((r) => wordSchema.parse(r.data)),
  restore: (id: number) => appClient.post(`${BASE}/words/${id}/restore`).then((r) => wordSchema.parse(r.data)),
  importText: (content: string) =>
    appClient
      .post(`${BASE}/import`, { content })
      .then((r) => z.object({ added: z.number(), restored: z.number(), skipped: z.number() }).parse(r.data)),
  /** Downloads the list; resolves with the file name once the browser has it. */
  exportFile: async (format: 'csv' | 'txt'): Promise<string> => {
    const r = await appClient.get(`${BASE}/export`, { params: { format }, responseType: 'blob' })
    const blob = r.data as Blob
    const match = /filename="([^"]+)"/.exec(String(r.headers['content-disposition'] ?? ''))
    const fileName = match?.[1] ?? `irisclick_word_filter.${format}`
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = fileName
    document.body.append(link)
    link.click()
    link.remove()
    window.setTimeout(() => URL.revokeObjectURL(url), 10_000)
    return fileName
  },
}
