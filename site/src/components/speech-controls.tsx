import { Repeat, Square } from 'lucide-react'
import { GazeButton } from '@/components/gaze-button'
import { player, usePlayer } from '@/lib/natural-voice'
import { cn } from '@/lib/utils'

/** Stop and Replay (≥ 80 px, gaze-friendly), placed next to Speak. */
export function SpeechButtons({ onError }: { onError: (message: string) => void }) {
  const state = usePlayer()
  return (
    <>
      <GazeButton variant="outline" className="min-w-44" disabled={!state.speaking} onClick={player.stop}>
        <Square aria-hidden />
        Stop
      </GazeButton>
      <GazeButton variant="outline" className="min-w-44" disabled={!state.canReplay}
        onClick={() => void player.replay().then((r) => !r.ok && onError(r.error))}>
        <Repeat aria-hidden />
        Replay
      </GazeButton>
    </>
  )
}

/** "Speaking…" with which voice is used, and the message with the spoken part highlighted. */
export function NowSpeaking() {
  const state = usePlayer()
  if (!state.speaking) return null
  const { text, highlight } = state
  return (
    <div role="status" aria-live="polite" className="bg-card space-y-3 rounded-2xl border-2 p-5">
      <div className="flex flex-wrap items-center gap-3">
        <span className="text-primary text-2xl font-bold">Speaking…</span>
        {state.source && (
          <span className={cn('rounded-full px-3 py-1 text-base font-semibold',
            state.source === 'natural' ? 'bg-primary text-primary-foreground' : 'bg-muted text-foreground')}>
            {state.source === 'natural' ? 'Natural voice' : 'Basic voice (offline)'}
          </span>
        )}
      </div>
      <p className="text-2xl leading-relaxed break-words whitespace-pre-wrap">
        {highlight ? (
          <>
            {text.slice(0, highlight.start)}
            <mark className="bg-primary/25 text-foreground rounded px-0.5">{text.slice(highlight.start, highlight.end)}</mark>
            {text.slice(highlight.end)}
          </>
        ) : text}
      </p>
    </div>
  )
}
