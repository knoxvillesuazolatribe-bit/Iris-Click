import { zodResolver } from '@hookform/resolvers/zod'
import { UserPlus, Users } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Controller, useForm } from 'react-hook-form'
import { errorMessage } from '@/api/app-client'
import { ServerDown } from '@/components/server-down'
import { SignOutButton } from '@/components/sign-out-button'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Field, FieldError, FieldLabel } from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import { adminUsersService } from '@/services/auth-service'
import { useSessionStore } from '@/store/session-store'
import {
  assistiveCreateSchema,
  type AdminUser,
  type AssistiveCreateInput,
} from '@/validators/auth-validator'

type Load = { state: 'loading' } | { state: 'error'; message: string } | { state: 'ready'; users: AdminUser[] }

const TEXT_FIELDS = [
  { name: 'full_name', label: 'Full name', autoComplete: 'name' },
  { name: 'barangay', label: 'Barangay (optional)', autoComplete: 'address-level3' },
  { name: 'address', label: 'Address (optional)', autoComplete: 'street-address' },
] as const

/** Admin landing page: assistive users and creating them (full admin module: Phase 8). */
export function AdminPage() {
  const admin = useSessionStore((s) => s.user)
  const [load, setLoad] = useState<Load>({ state: 'loading' })
  const [notice, setNotice] = useState<{ kind: 'ok' | 'error'; text: string } | null>(null)
  const form = useForm<AssistiveCreateInput>({
    resolver: zodResolver(assistiveCreateSchema),
    defaultValues: { full_name: '', barangay: '', address: '' },
  })

  const [attempt, setAttempt] = useState(0)

  useEffect(() => {
    let current = true
    adminUsersService
      .list()
      .then((users) => current && setLoad({ state: 'ready', users }))
      .catch((err) => current && setLoad({ state: 'error', message: errorMessage(err, 'Could not load the users.') }))
    return () => {
      current = false
    }
  }, [attempt])

  const reload = () => setAttempt((n) => n + 1)

  const onSubmit = form.handleSubmit(async (values) => {
    setNotice(null)
    try {
      const created = await adminUsersService.createAssistive(values)
      setNotice({ kind: 'ok', text: `${created.full_name} can now sign in from the name tiles.` })
      form.reset()
      reload()
    } catch (err) {
      setNotice({ kind: 'error', text: errorMessage(err, 'The user was not created.') })
    }
  })

  return (
    <main className="bg-background text-foreground mx-auto flex min-h-svh max-w-5xl flex-col gap-8 p-6">
      <header className="flex flex-wrap items-center justify-between gap-6">
        <div>
          <h1 className="text-3xl font-bold">Administrator</h1>
          <p className="text-muted-foreground">Signed in as {admin?.full_name}</p>
        </div>
        <SignOutButton />
      </header>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-xl"><UserPlus aria-hidden /> Create assistive user</CardTitle>
          <CardDescription>The person then signs in by looking at their name tile. No password is needed.</CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={onSubmit} noValidate className="grid gap-4 md:grid-cols-3">
            {TEXT_FIELDS.map(({ name, label, autoComplete }) => (
              <Controller
                key={name}
                control={form.control}
                name={name}
                render={({ field, fieldState }) => (
                  <Field data-invalid={fieldState.invalid}>
                    <FieldLabel htmlFor={`new-${name}`}>{label}</FieldLabel>
                    <Input id={`new-${name}`} autoComplete={autoComplete} className="h-11"
                      aria-invalid={fieldState.invalid} {...field} />
                    {fieldState.invalid && <FieldError errors={[fieldState.error]} />}
                  </Field>
                )}
              />
            ))}
            <div className="flex flex-wrap items-center gap-4 md:col-span-3">
              <Button type="submit" size="lg" disabled={form.formState.isSubmitting}>
                <UserPlus aria-hidden />
                {form.formState.isSubmitting ? 'Creating…' : 'Create user'}
              </Button>
              {notice && (
                <Alert variant={notice.kind === 'error' ? 'destructive' : 'default'} role="status" className="w-auto flex-1">
                  <AlertDescription>{notice.text}</AlertDescription>
                </Alert>
              )}
            </div>
          </form>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-xl"><Users aria-hidden /> Users</CardTitle>
          <CardDescription>Full user management, settings, logs and reports come in a later update.</CardDescription>
        </CardHeader>
        <CardContent>
          {load.state === 'loading' && <p className="text-muted-foreground">Loading…</p>}
          {load.state === 'error' && <ServerDown message={load.message} onRetry={() => { setLoad({ state: 'loading' }); reload() }} />}
          {load.state === 'ready' && (
            <table className="w-full text-left">
              <thead className="text-muted-foreground border-b text-sm">
                <tr><th className="py-2">Name</th><th>Role</th><th>Barangay</th><th>Status</th></tr>
              </thead>
              <tbody>
                {load.users.map((user) => (
                  <tr key={user.user_id} className="border-b last:border-0">
                    <td className="py-3 font-medium">{user.full_name}</td>
                    <td>{user.role === 'admin' ? 'Administrator' : 'Assistive user'}</td>
                    <td>{user.barangay ?? '—'}</td>
                    <td><Badge variant={user.status === 'active' ? 'secondary' : 'destructive'}>{user.status}</Badge></td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </CardContent>
      </Card>
    </main>
  )
}
