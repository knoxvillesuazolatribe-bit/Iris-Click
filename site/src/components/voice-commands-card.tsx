import { CircleCheck, CircleX, Mic } from 'lucide-react'
import { useState } from 'react'
import { apiClient } from '@/api/api-client'
import { GazeButton } from '@/components/gaze-button'
import { cn } from '@/lib/utils'

/**
 * Panel revision: how IrisClick tells valid commands from invalid input. The samples go through the
 * same classifier IrisClick Desktop uses for the microphone (POST /api/desktop/voice-check on this PC),
 * so the panel can see each result without anyone speaking.
 */
const SAMPLES: { text: string; typing?: boolean }[] = [
  { text: 'Go to Facebook' },
  { text: 'Open YouTube' },
  { text: 'Start typing' },
  { text: "Hi I'm Knoxville", typing: true },
  { text: 'Send', typing: true },
  { text: 'Go to Netflix' },
  { text: 'What is the weather' },
  { text: '' },
]

type Result = { valid: boolean; kind: string; message: string }

const KIND_LABEL: Record<string, string> = {
  navigate: 'Valid navigation command',
  action: 'Valid action command',
  dictation: 'Valid dictation (typed into the text box)',
  invalid: 'Unrecognized / invalid input',
}

export function VoiceCommandsCard() {
  const [result, setResult] = useState<{ sample: string; typing: boolean; data: Result } | null>(null)
  const [error, setError] = useState<string | null>(null)

  const check = async (text: string, typing = false) => {
    setError(null)
    try {
      const { data } = await apiClient.post<Result>('/desktop/voice-check', { text, typing })
      setResult({ sample: text, typing, data })
    } catch {
      setError('Start IrisClick Desktop to check voice commands.')
    }
  }

  return (
    <section className="space-y-4 rounded-xl border bg-card p-6" aria-labelledby="voice-commands-title">
      <h2 id="voice-commands-title" className="flex items-center gap-3 text-2xl font-bold">
        <Mic aria-hidden />Voice commands
      </h2>
      <p className="text-lg text-muted-foreground">
        Turn on <strong>Mic</strong> on the IrisClick control bar, then say <strong>&ldquo;Go to Facebook&rdquo;</strong>.
        In a chat box say <strong>&ldquo;Start typing&rdquo;</strong>, speak your message, then <strong>&ldquo;Send&rdquo;</strong> or
        <strong> &ldquo;Stop typing&rdquo;</strong>. The microphone is off until you turn it on, and nothing you say leaves this computer.
      </p>
      <p className="text-lg font-semibold">Try how IrisClick checks what it hears:</p>
      <div className="flex flex-wrap gap-3">
        {SAMPLES.map((s) => (
          <GazeButton key={`${s.text}-${s.typing}`} variant="outline" onClick={() => void check(s.text, s.typing)}>
            {s.text ? `“${s.text}”${s.typing ? ' (while typing)' : ''}` : '(silence)'}
          </GazeButton>
        ))}
      </div>
      {error && <p role="alert" className="text-lg text-destructive">{error}</p>}
      {result && (
        <p role="status" className={cn('flex items-center gap-3 rounded-lg border-2 p-4 text-xl font-semibold',
          result.data.valid ? 'border-emerald-600 text-emerald-700' : 'border-destructive text-destructive')}>
          {result.data.valid ? <CircleCheck aria-hidden className="size-7 shrink-0" /> : <CircleX aria-hidden className="size-7 shrink-0" />}
          <span>
            {result.sample ? `“${result.sample}”` : '(silence)'}: {KIND_LABEL[result.data.kind] ?? result.data.kind}. {result.data.message}
          </span>
        </p>
      )}
    </section>
  )
}
