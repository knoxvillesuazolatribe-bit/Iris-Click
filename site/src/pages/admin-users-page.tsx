import { zodResolver } from '@hookform/resolvers/zod'
import { UserPlus } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Controller, useForm } from 'react-hook-form'
import { Link } from 'react-router'
import { errorMessage } from '@/api/app-client'
import { AdminLayout } from '@/components/admin-layout'
import { ServerDown } from '@/components/server-down'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Field, FieldError, FieldLabel } from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import { adminService } from '@/services/admin-service'
import { adminUsersService } from '@/services/auth-service'
import type { AdminUserRow } from '@/validators/admin-validator'
import { assistiveCreateSchema, type AssistiveCreateInput } from '@/validators/auth-validator'

type Load = { state: 'loading' } | { state: 'error'; message: string } | { state: 'ready'; users: AdminUserRow[] }

const TEXT_FIELDS = [
  { name: 'full_name', label: 'Full name', autoComplete: 'name' },
  { name: 'barangay', label: 'Barangay', autoComplete: 'address-level3' },
  { name: 'address', label: 'Address', autoComplete: 'street-address' },
] as const
const DATE = new Intl.DateTimeFormat(undefined, { dateStyle: 'medium' })

/** Screens 19–21: assistive users and creating them. */
export function AdminUsersPage() {
  const [load, setLoad] = useState<Load>({ state: 'loading' })
  const [attempt, setAttempt] = useState(0)
  const [notice, setNotice] = useState<{ kind: 'ok' | 'error'; text: string } | null>(null)
  const form = useForm<AssistiveCreateInput>({
    resolver: zodResolver(assistiveCreateSchema),
    defaultValues: { full_name: '', barangay: '', address: '' },
  })

  useEffect(() => {
    let current = true
    adminService
      .users()
      .then((users) => current && setLoad({ state: 'ready', users: users.filter((u) => u.role === 'assistive_user') }))
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
    <AdminLayout title="Users" description="Assistive users sign in by looking at their name tile. No password is needed.">
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-xl"><UserPlus aria-hidden /> Create assistive user</CardTitle>
          <CardDescription>The address and barangay are shared with emergency contacts when the person presses SOS.</CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={onSubmit} noValidate className="grid gap-4 md:grid-cols-3">
            {TEXT_FIELDS.map(({ name, label, autoComplete }) => (
              <Controller key={name} control={form.control} name={name}
                render={({ field, fieldState }) => (
                  <Field data-invalid={fieldState.invalid}>
                    <FieldLabel htmlFor={`new-${name}`}>{label}{name !== 'full_name' && ' (optional)'}</FieldLabel>
                    <Input id={`new-${name}`} autoComplete={autoComplete} className="h-11" aria-invalid={fieldState.invalid} {...field} />
                    {fieldState.invalid && <FieldError errors={[fieldState.error]} />}
                  </Field>
                )} />
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
        <CardContent className="pt-6">
          {load.state === 'loading' && <p className="text-muted-foreground">Loading…</p>}
          {load.state === 'error' && <ServerDown message={load.message} onRetry={() => { setLoad({ state: 'loading' }); reload() }} />}
          {load.state === 'ready' && load.users.length === 0 && <p className="text-muted-foreground">No assistive users yet.</p>}
          {load.state === 'ready' && load.users.length > 0 && (
            <div className="overflow-x-auto">
              <table className="w-full text-left">
                <thead className="text-muted-foreground border-b text-sm">
                  <tr><th className="py-2 pr-4">Name</th><th className="pr-4">Barangay</th><th className="pr-4">Calibration</th><th className="pr-4">Status</th><th /></tr>
                </thead>
                <tbody>
                  {load.users.map((u) => (
                    <tr key={u.user_id} className="border-b last:border-0">
                      <td className="py-3 pr-4 font-medium">{u.full_name}</td>
                      <td className="pr-4">{u.barangay ?? '—'}</td>
                      <td className="pr-4">
                        {u.calibration_count === 0 ? (
                          <span className="text-muted-foreground">Not calibrated</span>
                        ) : (
                          <>
                            {u.latest_accuracy !== null ? `${u.latest_accuracy.toFixed(2)}%` : 'Linked'}
                            <span className="text-muted-foreground text-sm">
                              {u.last_calibrated_at && ` · ${DATE.format(new Date(u.last_calibrated_at))}`}
                            </span>
                          </>
                        )}
                      </td>
                      <td className="pr-4">
                        <Badge variant={u.status === 'active' ? 'secondary' : 'destructive'}>
                          {u.status === 'active' ? 'Active' : 'Inactive'}
                        </Badge>
                      </td>
                      <td className="text-right">
                        <Button asChild variant="outline" size="sm"><Link to={`/admin/users/${u.user_id}`}>Open</Link></Button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>
    </AdminLayout>
  )
}
