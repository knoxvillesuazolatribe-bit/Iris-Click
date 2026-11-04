import { zodResolver } from '@hookform/resolvers/zod'
import { ArrowLeft, LogIn } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Controller, useForm } from 'react-hook-form'
import { Navigate, useNavigate } from 'react-router'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from '@/components/ui/card'
import { Field, FieldError, FieldLabel } from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import { useSessionStore } from '@/store/session-store'
import { adminLoginSchema, type AdminLoginInput } from '@/validators/auth-validator'

/** Admin sign-in (Fig. 17): email + password, with an error and retry on invalid input. */
export function AdminLoginPage() {
  const navigate = useNavigate()
  const status = useSessionStore((s) => s.status)
  const user = useSessionStore((s) => s.user)
  const load = useSessionStore((s) => s.load)
  const adminLogin = useSessionStore((s) => s.adminLogin)
  const [error, setError] = useState<string | null>(null)
  const form = useForm<AdminLoginInput>({
    resolver: zodResolver(adminLoginSchema),
    defaultValues: { email: '', password: '' },
  })

  useEffect(() => {
    if (status === 'unknown') void load()
  }, [status, load])

  const onSubmit = form.handleSubmit(async (values) => {
    setError(null)
    const message = await adminLogin(values)
    if (message) {
      setError(message)
      form.resetField('password')
      form.setFocus('password')
      return
    }
    void navigate('/admin', { replace: true })
  })

  if (status === 'signed-in' && user?.role === 'admin') return <Navigate to="/admin" replace />

  return (
    <main className="bg-background text-foreground flex min-h-svh flex-col items-center justify-center gap-6 p-6">
      <Card className="w-full max-w-md">
        <CardHeader>
          <CardTitle className="text-3xl">Administrator sign-in</CardTitle>
          <CardDescription className="text-base">PDAO staff only.</CardDescription>
        </CardHeader>
        <form onSubmit={onSubmit} noValidate>
          <CardContent className="space-y-5">
            {error && (
              <Alert variant="destructive" role="alert">
                <AlertDescription className="text-base">{error}</AlertDescription>
              </Alert>
            )}
            <Controller
              control={form.control}
              name="email"
              render={({ field, fieldState }) => (
                <Field data-invalid={fieldState.invalid}>
                  <FieldLabel htmlFor="admin-email" className="text-base">Email</FieldLabel>
                  <Input id="admin-email" type="email" autoComplete="username" autoFocus
                    className="h-12 text-lg" aria-invalid={fieldState.invalid} {...field} />
                  {fieldState.invalid && <FieldError errors={[fieldState.error]} />}
                </Field>
              )}
            />
            <Controller
              control={form.control}
              name="password"
              render={({ field, fieldState }) => (
                <Field data-invalid={fieldState.invalid}>
                  <FieldLabel htmlFor="admin-password" className="text-base">Password</FieldLabel>
                  <Input id="admin-password" type="password" autoComplete="current-password"
                    className="h-12 text-lg" aria-invalid={fieldState.invalid} {...field} />
                  {fieldState.invalid && <FieldError errors={[fieldState.error]} />}
                </Field>
              )}
            />
          </CardContent>
          <CardFooter className="mt-6 flex flex-col gap-3">
            <Button type="submit" size="lg" className="h-12 w-full text-lg" disabled={form.formState.isSubmitting}>
              <LogIn aria-hidden />
              {form.formState.isSubmitting ? 'Signing in…' : 'Sign in'}
            </Button>
            <Button type="button" variant="ghost" size="lg" className="h-12 w-full" onClick={() => void navigate('/')}>
              <ArrowLeft aria-hidden />
              Back
            </Button>
          </CardFooter>
        </form>
      </Card>
    </main>
  )
}
