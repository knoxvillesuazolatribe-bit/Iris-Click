import { z } from 'zod'
import { appClient } from '@/api/app-client'

/**
 * Word filter (extension): asks the server to mask blocked words before text
 * is spoken or shown. If the check fails, the text is used as written, so
 * speaking never breaks; saving is filtered on the server anyway.
 */
export interface Filtered {
  /** Text to show, with blocked words masked ("b***"). */
  display: string
  /** Text to speak: masked words become "beep" or are left out (admin setting). */
  speak: string
  filtered: boolean
}

const checkSchema = z.object({ masked_text: z.string(), was_filtered: z.boolean(), speak_text: z.string() })

export async function filterText(text: string): Promise<Filtered> {
  if (!text.trim()) return { display: text, speak: text, filtered: false }
  try {
    const r = await appClient.post('/me/filter/check', { text })
    const body = checkSchema.parse(r.data)
    return { display: body.masked_text, speak: body.speak_text, filtered: body.was_filtered }
  } catch {
    return { display: text, speak: text, filtered: false }
  }
}
