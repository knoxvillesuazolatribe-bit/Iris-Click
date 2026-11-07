import { useSyncExternalStore } from 'react'
import { appClient } from '@/api/app-client'
import { speakIn, stopSpeaking, type SpeakResult, type SpeechLang } from '@/lib/voices'

/**
 * Clearer text to speech (neural voices).
 *
 * Order: 1) the natural voice from the server (cached audio first, then
 * Microsoft's neural voice online, 4 s limit), 2) the existing voices
 * (browser voice / Filipino internet voice) unchanged, 3) a clear message.
 * Long text is split at sentence ends; the next part loads while one plays.
 * Pressing Speak again stops what is playing first, so voices never overlap.
 */
export type VoiceSource = 'natural' | 'basic'
export const UNAVAILABLE = 'Voice is unavailable right now. The message stays on the screen.'

export interface VoiceOptions {
  voice?: string
  rate?: number
  pitch?: number
}

export interface PlayerState {
  speaking: boolean
  source: VoiceSource | null
  /** The message being spoken, and the part of it being spoken now. */
  text: string
  highlight: { start: number; end: number } | null
  canReplay: boolean
}

interface Boundary { offset_ms: number; duration_ms: number; text: string }
interface Part { start: number; end: number; text: string }
interface Fetched { url: string; boundaries: Boundary[] }

const PART_CHARS = 220
const REQUEST_TIMEOUT_MS = 6000 // the server gives the neural voice 4 s for its first audio

/** Splits at sentence ends (and line breaks) into parts of up to PART_CHARS, keeping positions. */
export function splitSentences(text: string): Part[] {
  const sentences: Part[] = []
  const re = /[^.?!\n]+(?:[.?!]+|\n|$)/g
  for (let m = re.exec(text); m; m = re.exec(text)) {
    if (m[0].trim()) sentences.push({ start: m.index, end: m.index + m[0].length, text: m[0] })
    if (m[0] === '') re.lastIndex++
  }
  const parts: Part[] = []
  for (const s of sentences) {
    const last = parts.at(-1)
    // The first sentence goes alone so speech starts sooner; later ones are grouped.
    if (last && parts.length > 1 && last.end === s.start && last.text.length + s.text.length <= PART_CHARS) {
      parts[parts.length - 1] = { start: last.start, end: s.end, text: last.text + s.text }
      continue
    }
    if (s.text.length <= PART_CHARS) {
      parts.push(s)
      continue
    }
    let start = s.start // a very long sentence: break at the last space before the limit
    while (start < s.end) {
      let end = Math.min(start + PART_CHARS, s.end)
      if (end < s.end) {
        const space = text.lastIndexOf(' ', end)
        if (space > start) end = space + 1
      }
      parts.push({ start, end, text: text.slice(start, end) })
      start = end
    }
  }
  return parts.filter((p) => p.text.trim())
}

function toBlobUrl(base64: string, mime: string): string {
  const bytes = Uint8Array.from(atob(base64), (c) => c.charCodeAt(0))
  return URL.createObjectURL(new Blob([bytes], { type: mime }))
}

class Player {
  private state: PlayerState = { speaking: false, source: null, text: '', highlight: null, canReplay: false }
  private listeners = new Set<() => void>()
  private generation = 0
  private audio: HTMLAudioElement | null = null
  private context: AudioContext | null = null
  private last: { text: string; lang: SpeechLang; volume: number; options: VoiceOptions } | null = null
  private poll: number | undefined

  subscribe = (listener: () => void) => {
    this.listeners.add(listener)
    return () => this.listeners.delete(listener)
  }

  snapshot = () => this.state

  private set(change: Partial<PlayerState>) {
    this.state = { ...this.state, ...change }
    this.listeners.forEach((l) => l())
  }

  stop = () => {
    this.generation++
    window.clearInterval(this.poll)
    this.audio?.pause()
    this.audio = null
    stopSpeaking()
    if (this.state.speaking) this.set({ speaking: false, highlight: null })
  }

  replay = () => {
    if (!this.last) return Promise.resolve<SpeakResult>({ ok: false, error: 'Nothing has been spoken yet.' })
    const { text, lang, volume, options } = this.last
    return this.speak(text, lang, volume, options)
  }

  /** Speaks ``text`` (already through the word filter). Resolves once speech has started or failed. */
  speak = async (text: string, lang: SpeechLang, volume: number, options: VoiceOptions = {}): Promise<SpeakResult & { source?: VoiceSource }> => {
    this.stop()
    const generation = this.generation
    const parts = splitSentences(text)
    if (parts.length === 0) return { ok: false, error: 'There is nothing to say.' }
    this.last = { text, lang, volume, options }
    this.set({ speaking: true, source: null, text, highlight: null, canReplay: true })
    this.wakeAudio()

    const load = (part: Part) => this.fetchPart(part.text, lang, options)
    let next: Promise<Fetched | null> = load(parts[0])
    for (let i = 0; i < parts.length; i++) {
      const fetched = await next
      if (generation !== this.generation) return { ok: true }
      if (!fetched) return this.basic(text.slice(parts[i].start), lang, volume, generation, i === 0)
      if (i === 0) this.set({ source: 'natural' })
      next = i + 1 < parts.length ? load(parts[i + 1]) : Promise.resolve(null)
      const finished = this.play(fetched, parts[i], volume, generation)
      if (i === 0) {
        void this.playRest(finished, next, parts, lang, volume, options, generation)
        return { ok: true, source: 'natural' }
      }
    }
    return { ok: true, source: 'natural' }
  }

  private async playRest(first: Promise<boolean>, next: Promise<Fetched | null>, parts: Part[], lang: SpeechLang,
    volume: number, options: VoiceOptions, generation: number) {
    let done = await first
    for (let i = 1; i < parts.length && done; i++) {
      const fetched = await next
      if (generation !== this.generation) return
      if (!fetched) {
        await this.basic(this.state.text.slice(parts[i].start), lang, volume, generation, false)
        return
      }
      next = i + 1 < parts.length ? this.fetchPart(parts[i + 1].text, lang, options) : Promise.resolve(null)
      done = await this.play(fetched, parts[i], volume, generation)
    }
    if (generation === this.generation) this.set({ speaking: false, highlight: null })
  }

  private async fetchPart(text: string, lang: SpeechLang, options: VoiceOptions): Promise<Fetched | null> {
    try {
      const r = await appClient.post('/tts/speak', { text, language: lang, ...options }, { timeout: REQUEST_TIMEOUT_MS })
      const body = r.data as { audio: string; mime: string; boundaries: Boundary[] }
      return { url: toBlobUrl(body.audio, body.mime), boundaries: body.boundaries ?? [] }
    } catch {
      return null
    }
  }

  /** Audio goes through a compressor so loud and quiet phrases come out at a similar level. */
  private wakeAudio() {
    try {
      this.context ??= new AudioContext()
      void this.context.resume()
    } catch {
      this.context = null
    }
  }

  private route(audio: HTMLAudioElement, volume: number) {
    const level = Math.min(Math.max(volume, 0), 100) / 100
    if (!this.context) {
      audio.volume = level
      return
    }
    try {
      const source = this.context.createMediaElementSource(audio)
      const compressor = this.context.createDynamicsCompressor()
      compressor.threshold.value = -24
      compressor.knee.value = 12
      compressor.ratio.value = 4
      compressor.attack.value = 0.003
      compressor.release.value = 0.25
      const gain = this.context.createGain()
      gain.gain.value = level * 1.4 // makes up for the compressor
      source.connect(compressor).connect(gain).connect(this.context.destination)
    } catch {
      audio.volume = level
    }
  }

  /** Plays one part; resolves true when it ended, false if stopped or failed. */
  private play(fetched: Fetched, part: Part, volume: number, generation: number): Promise<boolean> {
    return new Promise((resolve) => {
      const audio = new Audio(fetched.url)
      this.audio = audio
      this.route(audio, volume)
      const words = this.locateWords(fetched.boundaries, part)
      this.set({ highlight: { start: part.start, end: part.end } })
      audio.addEventListener('timeupdate', () => {
        if (generation !== this.generation) return
        const ms = audio.currentTime * 1000
        const current = words.filter((w) => w.offset <= ms).at(-1)
        this.set({ highlight: current ? { start: current.start, end: current.end } : { start: part.start, end: part.end } })
      })
      const finish = (ok: boolean) => {
        URL.revokeObjectURL(fetched.url)
        resolve(ok && generation === this.generation)
      }
      audio.addEventListener('ended', () => finish(true), { once: true })
      audio.addEventListener('error', () => finish(false), { once: true })
      audio.play().catch(() => finish(false))
    })
  }

  /** Word timings → positions in the message, found in order (numbers read as words are skipped). */
  private locateWords(boundaries: Boundary[], part: Part) {
    const found: { offset: number; start: number; end: number }[] = []
    const lower = this.state.text.toLowerCase()
    let from = part.start
    for (const b of boundaries) {
      const at = lower.indexOf(b.text.toLowerCase(), from)
      if (at >= 0 && at < part.end) {
        found.push({ offset: b.offset_ms, start: at, end: at + b.text.length })
        from = at + b.text.length
      }
    }
    return found
  }

  /** The existing voices, unchanged; "Voice is unavailable" if they fail too. */
  private async basic(text: string, lang: SpeechLang, volume: number, generation: number,
    first: boolean): Promise<SpeakResult & { source?: VoiceSource }> {
    const result = await speakIn(text, volume, lang)
    if (generation !== this.generation) return { ok: true }
    if (!result.ok) {
      this.set({ speaking: false, highlight: null, source: null })
      return { ok: false, error: first ? UNAVAILABLE : result.error }
    }
    this.set({ source: 'basic', highlight: { start: 0, end: this.state.text.length } })
    // The browser voice gives no timings; keep "Speaking…" while it talks.
    this.poll = window.setInterval(() => {
      if (generation !== this.generation || !window.speechSynthesis?.speaking) {
        window.clearInterval(this.poll)
        if (generation === this.generation) this.set({ speaking: false, highlight: null })
      }
    }, 300)
    return { ...result, source: 'basic' as const }
  }
}

export const player = new Player()

export function usePlayer(): PlayerState {
  return useSyncExternalStore(player.subscribe, player.snapshot)
}

/** Saves audio for these phrases on the server so they play at once (and offline) later. */
export function warmPhrases(texts: string[], lang: SpeechLang) {
  appClient.post('/tts/warm', { texts, language: lang }).catch(() => undefined)
}
