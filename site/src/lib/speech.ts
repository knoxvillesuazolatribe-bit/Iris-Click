/**
 * Browser speech (team decision D9): speechSynthesis speaks text, and the Web
 * Speech API turns speech into text. Recognition runs online in Chrome
 * (Google) and Edge (Microsoft); Brave blocks it.
 */

export type SpeechLanguage = 'en-PH' | 'fil-PH'

/** Speaks ``text`` aloud at ``volume`` (0–100). Returns false if the browser cannot. */
export function speak(text: string, volume: number, lang: SpeechLanguage = 'en-PH'): boolean {
  if (!('speechSynthesis' in window) || !text.trim()) return false
  window.speechSynthesis.cancel()
  const utterance = new SpeechSynthesisUtterance(text)
  utterance.lang = lang
  utterance.volume = Math.min(Math.max(volume, 0), 100) / 100
  window.speechSynthesis.speak(utterance)
  return true
}

// The Web Speech API is not in TypeScript's DOM types; only what we use.
interface RecognitionResultEvent {
  resultIndex: number
  results: ArrayLike<{ isFinal: boolean; 0: { transcript: string } }>
}
interface RecognitionErrorEvent {
  error: string
}
interface Recognition {
  lang: string
  interimResults: boolean
  continuous: boolean
  maxAlternatives: number
  onresult: ((event: RecognitionResultEvent) => void) | null
  onerror: ((event: RecognitionErrorEvent) => void) | null
  onend: (() => void) | null
  start(): void
  stop(): void
  abort(): void
}
type RecognitionConstructor = new () => Recognition

function recognitionConstructor(): RecognitionConstructor | null {
  const w = window as unknown as { SpeechRecognition?: RecognitionConstructor; webkitSpeechRecognition?: RecognitionConstructor }
  return w.SpeechRecognition ?? w.webkitSpeechRecognition ?? null
}

const BRAVE_MESSAGE =
  'Speech to text does not work in the Brave browser. Open IrisClick in Chrome or Edge to use it. The keyboard still works.'

/** Why speech recognition cannot be used right now, or null if it can. */
export function recognitionUnavailableReason(): string | null {
  if ((navigator as Navigator & { brave?: unknown }).brave) return BRAVE_MESSAGE
  if (!recognitionConstructor()) {
    return 'This browser cannot turn speech into text. Open IrisClick in Chrome or Edge. The keyboard still works.'
  }
  if (!navigator.onLine) {
    return 'Speech to text needs the internet, and this computer is offline. The keyboard still works.'
  }
  return null
}

const ERROR_MESSAGES: Record<string, string> = {
  'no-speech': 'I did not hear anything. Press Tap to Speak and try again.',
  'audio-capture': 'No microphone was found. Connect a microphone and try again.',
  'not-allowed': 'The browser is not allowed to use the microphone. Allow it in the address bar, then try again.',
  'service-not-allowed': 'The browser is not allowed to use the microphone. Allow it in the address bar, then try again.',
  network: 'Speech to text could not reach the internet. Check the connection, or use the keyboard.',
  'language-not-supported': 'This browser does not understand that language. Try English.',
}

export interface ListenHandlers {
  /** Recognised text so far; ``final`` once the browser is sure. */
  onText: (text: string, final: boolean) => void
  onError: (message: string) => void
  onEnd: () => void
}

/** Starts listening once; returns a function that stops early. */
export function listen(lang: SpeechLanguage, handlers: ListenHandlers): () => void {
  const Constructor = recognitionConstructor()
  if (!Constructor) {
    handlers.onError(recognitionUnavailableReason() ?? 'Speech to text is not available.')
    handlers.onEnd()
    return () => undefined
  }
  const recognition = new Constructor()
  recognition.lang = lang
  recognition.interimResults = true
  recognition.continuous = false
  recognition.maxAlternatives = 1
  recognition.onresult = (event) => {
    let text = ''
    let final = true
    for (let i = 0; i < event.results.length; i++) {
      text += event.results[i][0].transcript
      final &&= event.results[i].isFinal
    }
    handlers.onText(text.trim(), final)
  }
  recognition.onerror = (event) => {
    if (event.error === 'aborted') return
    const brave = (navigator as Navigator & { brave?: unknown }).brave
    handlers.onError(brave ? BRAVE_MESSAGE : (ERROR_MESSAGES[event.error] ?? `Speech to text stopped (${event.error}). Try again or use the keyboard.`))
  }
  recognition.onend = handlers.onEnd
  try {
    recognition.start()
  } catch {
    handlers.onError('Speech to text could not start. Try again.')
    handlers.onEnd()
  }
  return () => recognition.stop()
}
