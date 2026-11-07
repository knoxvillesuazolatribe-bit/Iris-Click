import { useEffect, useState } from 'react'
import { errorMessage } from '@/api/app-client'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import type { SpeechLang } from '@/lib/voices'
import { languageService } from '@/services/language-service'

const OPTIONS: { value: SpeechLang; label: string }[] = [
  { value: 'en', label: 'English' },
  { value: 'fil', label: 'Filipino' },
]

/** Admin user page: the person's speech language for Voice Communication (extension). */
export function AdminUserLanguageCard({ userId, name }: { userId: number; name: string }) {
  const [language, setLanguage] = useState<SpeechLang | null>(null)
  const [busy, setBusy] = useState(false)
  const [notice, setNotice] = useState<{ kind: 'ok' | 'error'; text: string } | null>(null)

  useEffect(() => {
    languageService.forUser(userId)
      .then(setLanguage)
      .catch((err) => setNotice({ kind: 'error', text: errorMessage(err, 'The language could not be loaded.') }))
  }, [userId])

  const save = async (next: SpeechLang) => {
    setBusy(true)
    setNotice(null)
    try {
      setLanguage(await languageService.saveForUser(userId, next))
      setNotice({ kind: 'ok', text: `${name} now speaks and listens in ${next === 'fil' ? 'Filipino' : 'English'}.` })
    } catch (err) {
      setNotice({ kind: 'error', text: errorMessage(err, 'The language was not saved.') })
    } finally {
      setBusy(false)
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Speech language</CardTitle>
        <CardDescription>The language {name} uses for text to speech and speech to text. They can also switch it on the Voice page.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex gap-2" role="group" aria-label="Speech language">
          {OPTIONS.map((o) => (
            <Button key={o.value} variant={language === o.value ? 'default' : 'outline'} aria-pressed={language === o.value}
              disabled={busy || language === null} onClick={() => language !== o.value && void save(o.value)}>
              {o.label}
            </Button>
          ))}
        </div>
        {notice && (
          <Alert variant={notice.kind === 'error' ? 'destructive' : 'default'} role="status">
            <AlertDescription>{notice.text}</AlertDescription>
          </Alert>
        )}
      </CardContent>
    </Card>
  )
}
