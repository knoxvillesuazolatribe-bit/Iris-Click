import { useMemo } from 'react'
import { UserAppTiles } from '@/components/user-app-tiles'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { tilesForUser } from '@/services/user-apps-service'

/** Admin user page: the person's Apps tiles, with the same rules as on their Home screen. */
export function AdminUserAppsCard({ userId, name }: { userId: number; name: string }) {
  const api = useMemo(() => tilesForUser(userId), [userId])
  return (
    <Card>
      <CardHeader>
        <CardTitle>Apps</CardTitle>
        <CardDescription>The app tiles on {name}’s Home screen. Remove, move or add apps and websites.</CardDescription>
      </CardHeader>
      <CardContent>
        <UserAppTiles api={api} variant="admin"
          fallback={<p className="text-muted-foreground">The apps could not be loaded. Try again later.</p>} />
      </CardContent>
    </Card>
  )
}
