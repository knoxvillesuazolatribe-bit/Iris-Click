import { History, Trash2 } from 'lucide-react'
import { TwoPressButton } from '@/components/two-press-button'
import { Badge } from '@/components/ui/badge'
import type { Communication } from '@/validators/voice-validator'

const DATE_FORMAT = new Intl.DateTimeFormat(undefined, { dateStyle: 'medium', timeStyle: 'short' })

interface MessageHistoryProps {
  messages: Communication[]
  onDelete: (message: Communication) => void
  busyId: number | null
}

/** The user's latest sent messages, newest first; each can be deleted (two presses). */
export function MessageHistory({ messages, onDelete, busyId }: MessageHistoryProps) {
  return (
    <section aria-labelledby="message-history" className="bg-card rounded-2xl border-2 p-6">
      <h2 id="message-history" className="mb-4 flex items-center gap-3 text-2xl font-bold">
        <History className="size-8" aria-hidden />
        Your recent messages
      </h2>
      {messages.length === 0 ? (
        <p className="text-muted-foreground text-xl">No messages sent yet.</p>
      ) : (
        <ul className="flex flex-col gap-6">
          {messages.map((m) => (
            <li key={m.communication_id} className="flex flex-wrap items-center justify-between gap-6 border-b pb-6 last:border-0 last:pb-0">
              <div className="min-w-0 flex-1 space-y-2">
                <div className="flex flex-wrap items-center gap-3 text-base">
                  <Badge variant="secondary">{m.mode === 'text_to_speech' ? 'Typed' : 'Spoken'}</Badge>
                  <span className="text-muted-foreground">{DATE_FORMAT.format(new Date(m.date_created))}</span>
                </div>
                <p className="text-2xl break-words whitespace-pre-wrap">{m.message}</p>
              </div>
              <TwoPressButton
                icon={Trash2}
                label="Delete"
                confirmLabel="Yes, delete"
                disabled={busyId === m.communication_id}
                onConfirm={() => onDelete(m)}
              />
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}
