import { useMemo } from 'react'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { VoiceSettingsPanel } from '@/components/voice-settings-panel'
import { voiceSettingsForUser } from '@/services/voice-settings-service'

/** Admin user page: the person's natural voice, speed and pitch (clearer TTS). */
export function AdminUserVoiceCard({ userId, name }: { userId: number; name: string }) {
  const api = useMemo(() => voiceSettingsForUser(userId), [userId])
  return (
    <Card>
      <CardHeader>
        <CardTitle>Voice</CardTitle>
        <CardDescription>The natural voice {name} speaks with. Changes are saved right away.</CardDescription>
      </CardHeader>
      <CardContent>
        <VoiceSettingsPanel api={api} />
      </CardContent>
    </Card>
  )
}
