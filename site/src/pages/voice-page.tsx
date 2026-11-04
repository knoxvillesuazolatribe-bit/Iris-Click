import { ArrowLeft, Eraser, Keyboard, LayoutGrid, LoaderCircle, Mic, Send, Volume2 } from 'lucide-react'
import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router'
import { errorMessage } from '@/api/app-client'
import { GazeButton } from '@/components/gaze-button'
import { GazeKeyboard } from '@/components/gaze-keyboard'
import { MessageHistory } from '@/components/message-history'
import { ServerDown } from '@/components/server-down'
import { SpeechPanel } from '@/components/speech-panel'
import { AacBoard } from '@/components/aac-board'
import { TwoPressButton } from '@/components/two-press-button'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { speak } from '@/lib/speech'
import { typeKey } from '@/lib/typing'
import { voiceService } from '@/services/voice-service'
import {
  MAX_MESSAGE_CHARS,
  type Communication,
  type CommunicationMode,
} from '@/validators/voice-validator'

const QUICK_PHRASES = [
  'I need help',
  'Yes',
  'No',
  'Thank you',
  "I'm hungry",
  'I need water',
  'Please call my caregiver',
]
const HISTORY_SIZE = 10
const DEFAULT_VOLUME = 100

type Tab = 'keyboard' | 'speech' | 'board'
type Load = { state: 'loading' } | { state: 'error'; message: string } | { state: 'ready' }
type Notice = { kind: 'ok' | 'error'; text: string } | null

/** Screens 12–14: Voice Communication (keyboard + text to speech, speech to text). */
export function VoicePage() {
  const navigate = useNavigate()
  const [tab, setTab] = useState<Tab>('keyboard')
  const [load, setLoad] = useState<Load>({ state: 'loading' })
  const [attempt, setAttempt] = useState(0)
  const [volume, setVolume] = useState(DEFAULT_VOLUME)
  const [messages, setMessages] = useState<Communication[]>([])
  const [message, setMessage] = useState('')
  const [notice, setNotice] = useState<Notice>(null)
  const [sending, setSending] = useState(false)
  const [deletingId, setDeletingId] = useState<number | null>(null)

  useEffect(() => {
    let current = true
    voiceService
      .getVoice()
      .then((voice) => {
        if (!current) return
        setVolume(voice.voice_volume)
        setMessages(voice.messages)
        setLoad({ state: 'ready' })
      })
      .catch((err) => current && setLoad({ state: 'error', message: errorMessage(err, 'Could not load Voice Communication.') }))
    return () => {
      current = false
    }
  }, [attempt])

  const speakNow = (text: string) => {
    if (!text.trim()) {
      setNotice({ kind: 'error', text: 'Type a message first.' })
      return
    }
    setNotice(speak(text, volume) ? null : { kind: 'error', text: 'This browser cannot read text aloud.' })
  }

  const send = async (mode: CommunicationMode, text: string): Promise<boolean> => {
    const trimmed = text.trim()
    if (!trimmed) {
      setNotice({ kind: 'error', text: mode === 'text_to_speech' ? 'Type a message first.' : 'Say something first.' })
      return false
    }
    setSending(true)
    setNotice(null)
    try {
      const saved = await voiceService.send(mode, trimmed)
      setMessages((list) => [saved, ...list].slice(0, HISTORY_SIZE))
      setNotice({ kind: 'ok', text: 'Saved to your recent messages.' })
      return true
    } catch (err) {
      setNotice({ kind: 'error', text: errorMessage(err, 'The message was not saved.') })
      return false
    } finally {
      setSending(false)
    }
  }

  const remove = async (item: Communication) => {
    setDeletingId(item.communication_id)
    setNotice(null)
    try {
      await voiceService.remove(item.communication_id)
      setMessages((list) => list.filter((m) => m.communication_id !== item.communication_id))
      setNotice({ kind: 'ok', text: 'Message deleted.' })
    } catch (err) {
      setNotice({ kind: 'error', text: errorMessage(err, 'The message was not deleted.') })
    } finally {
      setDeletingId(null)
    }
  }

  const tabButton = (name: Tab, label: string, Icon: typeof Keyboard) => (
    <GazeButton
      role="tab"
      aria-selected={tab === name}
      variant={tab === name ? 'default' : 'outline'}
      className="min-w-64 text-2xl"
      onClick={() => {
        setTab(name)
        setNotice(null)
      }}
    >
      <Icon aria-hidden />
      {label}
    </GazeButton>
  )

  return (
    <main className="bg-background text-foreground mx-auto flex min-h-svh max-w-6xl flex-col gap-8 p-6">
      <header className="flex flex-wrap items-center justify-between gap-6">
        <h1 className="text-4xl font-bold">Voice Communication</h1>
        <GazeButton variant="outline" onClick={() => void navigate('/home')}>
          <ArrowLeft aria-hidden />
          Home
        </GazeButton>
      </header>

      {load.state === 'loading' && (
        <LoaderCircle className="text-muted-foreground mx-auto size-12 animate-spin" aria-label="Loading" />
      )}
      {load.state === 'error' && (
        <div className="flex justify-center">
          <ServerDown
            message={load.message}
            onRetry={() => {
              setLoad({ state: 'loading' })
              setAttempt((n) => n + 1)
            }}
          />
        </div>
      )}

      {load.state === 'ready' && (
        <>
          <div role="tablist" aria-label="Ways to communicate" className="flex flex-wrap gap-6">
            {tabButton('keyboard', 'Keyboard', Keyboard)}
            {tabButton('speech', 'Speech', Mic)}
            {tabButton('board', 'Board', LayoutGrid)}
          </div>

          {notice && (
            <Alert variant={notice.kind === 'error' ? 'destructive' : 'default'} role="status">
              <AlertDescription className="text-lg">{notice.text}</AlertDescription>
            </Alert>
          )}

          {tab === 'keyboard' ? (
            <section role="tabpanel" aria-label="Keyboard" className="flex flex-col gap-8">
              <div>
                <h2 className="mb-4 text-2xl font-bold">Quick Phrases</h2>
                <div className="flex flex-wrap gap-6">
                  {QUICK_PHRASES.map((phrase) => (
                    <GazeButton
                      key={phrase}
                      variant="secondary"
                      className="border-2"
                      onClick={() => {
                        setMessage(phrase)
                        speakNow(phrase)
                      }}
                    >
                      {phrase}
                    </GazeButton>
                  ))}
                </div>
              </div>

              <div className="space-y-2">
                <label htmlFor="message" className="text-2xl font-bold">
                  Your message
                </label>
                <textarea
                  id="message"
                  value={message}
                  maxLength={MAX_MESSAGE_CHARS}
                  onChange={(e) => setMessage(e.target.value)}
                  placeholder="Look at the letters below and wink to type."
                  className="bg-card focus-visible:ring-ring min-h-36 w-full resize-y rounded-2xl border-2 p-5 text-3xl break-words outline-none focus-visible:ring-4"
                />
                <p className="text-muted-foreground text-right text-base">
                  {message.length} / {MAX_MESSAGE_CHARS}
                </p>
              </div>

              <div className="flex flex-wrap gap-8">
                <GazeButton onClick={() => speakNow(message)} className="min-w-56">
                  <Volume2 aria-hidden />
                  Speak
                </GazeButton>
                <GazeButton
                  variant="outline"
                  disabled={sending}
                  onClick={() => void send('text_to_speech', message).then((ok) => ok && setMessage(''))}
                  className="min-w-56"
                >
                  {sending ? <LoaderCircle className="animate-spin" aria-hidden /> : <Send aria-hidden />}
                  Send
                </GazeButton>
                <TwoPressButton
                  icon={Eraser}
                  label="Clear"
                  confirmLabel="Yes, clear"
                  disabled={!message}
                  onConfirm={() => setMessage('')}
                />
              </div>

              <GazeKeyboard onKey={(key) => setMessage((text) => typeKey(text, key, MAX_MESSAGE_CHARS))} />
            </section>
          ) : tab === 'speech' ? (
            <section role="tabpanel" aria-label="Speech">
              <SpeechPanel sending={sending} onSend={(text) => send('speech_to_text', text)} />
            </section>
          ) : (
            <section role="tabpanel" aria-label="Board">
              <AacBoard volume={volume} onError={(text) => setNotice({ kind: 'error', text })} />
            </section>
          )}

          <MessageHistory messages={messages} busyId={deletingId} onDelete={(m) => void remove(m)} />
        </>
      )}
    </main>
  )
}
