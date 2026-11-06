import { isAxiosError } from 'axios'
import { appClient } from '@/api/app-client'
import { speak, type SpeechLanguage } from '@/lib/speech'

/**
 * English/Filipino speech (extension).
 *
 * English speaks exactly as before. Filipino uses a Filipino voice installed
 * in the browser (fil-PH, then tl); if there is none, it asks the server for
 * an internet voice and says so. It never reads Filipino with an English voice.
 */
export type SpeechLang = 'en' | 'fil'
export const RECOGNITION_LANG: Record<SpeechLang, SpeechLanguage> = { en: 'en-PH', fil: 'fil-PH' }
export const INTERNET_VOICE_NOTICE = 'Filipino voice uses the internet.'

export type SpeakResult = { ok: true; notice?: string } | { ok: false; error: string }

const VOICES_WAIT_MS = 1000
let playing: HTMLAudioElement | null = null

/** Browsers load their voice list late; wait briefly for it. */
function loadVoices(): Promise<SpeechSynthesisVoice[]> {
  const now = window.speechSynthesis.getVoices()
  if (now.length > 0) return Promise.resolve(now)
  return new Promise((resolve) => {
    const done = () => {
      window.speechSynthesis.removeEventListener('voiceschanged', done)
      window.clearTimeout(timer)
      resolve(window.speechSynthesis.getVoices())
    }
    const timer = window.setTimeout(done, VOICES_WAIT_MS)
    window.speechSynthesis.addEventListener('voiceschanged', done)
  })
}

/** The best installed Filipino voice: fil-PH, then tl, else null. */
export function filipinoVoice(voices: SpeechSynthesisVoice[]): SpeechSynthesisVoice | null {
  const lang = (v: SpeechSynthesisVoice) => v.lang.toLowerCase().replace('_', '-')
  return voices.find((v) => lang(v).startsWith('fil')) ?? voices.find((v) => lang(v).startsWith('tl')) ?? null
}

async function detailOf(err: unknown, fallback: string): Promise<string> {
  if (!isAxiosError(err) || !err.response) return 'Could not reach the IrisClick server.'
  const data: unknown = err.response.data
  try {
    const body = data instanceof Blob ? JSON.parse(await data.text()) : data
    return typeof body?.detail === 'string' ? body.detail : fallback
  } catch {
    return fallback
  }
}

async function internetVoice(text: string, volume: number): Promise<SpeakResult> {
  try {
    const r = await appClient.post('/tts', { text, language: 'fil' }, { responseType: 'blob' })
    const url = URL.createObjectURL(r.data as Blob)
    playing?.pause()
    playing = new Audio(url)
    playing.volume = Math.min(Math.max(volume, 0), 100) / 100
    playing.addEventListener('ended', () => URL.revokeObjectURL(url), { once: true })
    await playing.play()
    return { ok: true, notice: INTERNET_VOICE_NOTICE }
  } catch (err) {
    return { ok: false, error: await detailOf(err, 'No Filipino voice is available right now, so nothing was spoken.') }
  }
}

export async function speakIn(text: string, volume: number, lang: SpeechLang): Promise<SpeakResult> {
  if (lang === 'en') {
    return speak(text, volume) ? { ok: true } : { ok: false, error: 'This browser cannot read text aloud.' }
  }
  if (!text.trim()) return { ok: false, error: 'There is nothing to say.' }
  if ('speechSynthesis' in window) {
    const voice = filipinoVoice(await loadVoices())
    if (voice) {
      playing?.pause()
      window.speechSynthesis.cancel()
      const utterance = new SpeechSynthesisUtterance(text)
      utterance.voice = voice
      utterance.lang = voice.lang
      utterance.volume = Math.min(Math.max(volume, 0), 100) / 100
      window.speechSynthesis.speak(utterance)
      return { ok: true }
    }
    window.speechSynthesis.cancel()
  }
  return internetVoice(text, volume)
}
