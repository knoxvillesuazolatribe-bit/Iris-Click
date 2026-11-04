import { LoaderCircle, Mic, MicOff, RotateCcw, Send } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { GazeButton } from '@/components/gaze-button'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { listen, recognitionUnavailableReason, type SpeechLanguage } from '@/lib/speech'
import { cn } from '@/lib/utils'

const LANGUAGES: { lang: SpeechLanguage; label: string }[] = [
  { lang: 'en-PH', label: 'English' },
  { lang: 'fil-PH', label: 'Filipino' },
]

interface SpeechPanelProps {
  /** Saves the text; resolves true when it was saved. */
  onSend: (text: string) => Promise<boolean>
  sending: boolean
}

/** Speech tab: Tap to Speak → recognised text → Speak Again / Send. */
export function SpeechPanel({ onSend, sending }: SpeechPanelProps) {
  const [lang, setLang] = useState<SpeechLanguage>('en-PH')
  const [listening, setListening] = useState(false)
  const [text, setText] = useState('')
  const [error, setError] = useState<string | null>(null)
  const stop = useRef<(() => void) | null>(null)
  useEffect(() => () => stop.current?.(), [])

  const unavailable = recognitionUnavailableReason()

  const start = () => {
    setError(null)
    setText('')
    setListening(true)
    stop.current = listen(lang, {
      onText: (heard) => setText(heard),
      onError: setError,
      onEnd: () => {
        setListening(false)
        stop.current = null
      },
    })
  }

  const send = async () => {
    if (await onSend(text)) setText('')
  }

  return (
    <div className="flex flex-col gap-8">
      <div className="flex flex-wrap items-center gap-6" role="group" aria-label="Language">
        <span className="text-xl font-semibold">Language:</span>
        {LANGUAGES.map((option) => (
          <GazeButton
            key={option.lang}
            variant={lang === option.lang ? 'default' : 'outline'}
            aria-pressed={lang === option.lang}
            disabled={listening}
            onClick={() => setLang(option.lang)}
          >
            {option.label}
          </GazeButton>
        ))}
      </div>

      {unavailable ? (
        <Alert variant="destructive" role="alert">
          <AlertDescription className="text-lg">{unavailable}</AlertDescription>
        </Alert>
      ) : (
        <p className="text-muted-foreground text-lg">
          Your browser turns speech into text online (Google in Chrome, Microsoft in Edge).
        </p>
      )}

      {listening ? (
        <GazeButton variant="destructive" className="min-h-32 text-3xl" onClick={() => stop.current?.()}>
          <MicOff className="size-10" aria-hidden />
          Listening… press to stop
        </GazeButton>
      ) : (
        !text && (
          <GazeButton className="min-h-32 text-3xl" disabled={Boolean(unavailable)} onClick={start}>
            <Mic className="size-10" aria-hidden />
            Tap to Speak
          </GazeButton>
        )
      )}

      {error && (
        <Alert variant="destructive" role="alert">
          <AlertDescription className="text-lg">{error}</AlertDescription>
        </Alert>
      )}

      {(text || listening) && (
        <div
          aria-live="polite"
          className={cn(
            'bg-card min-h-32 rounded-2xl border-2 p-6 text-3xl break-words whitespace-pre-wrap',
            !text && 'text-muted-foreground',
          )}
        >
          {text || 'Say something…'}
        </div>
      )}

      {text && !listening && (
        <div className="flex flex-wrap gap-8">
          <GazeButton variant="outline" onClick={start} disabled={Boolean(unavailable) || sending}>
            <RotateCcw aria-hidden />
            Speak Again
          </GazeButton>
          <GazeButton onClick={() => void send()} disabled={sending}>
            {sending ? <LoaderCircle className="animate-spin" aria-hidden /> : <Send aria-hidden />}
            Send
          </GazeButton>
        </div>
      )}
    </div>
  )
}
