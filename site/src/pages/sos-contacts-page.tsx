import { zodResolver } from '@hookform/resolvers/zod'
import { ArrowLeft, LoaderCircle, Pencil, Save, Trash2, UserPlus, X } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Controller, useForm } from 'react-hook-form'
import { useNavigate } from 'react-router'
import { errorMessage } from '@/api/app-client'
import { GazeButton } from '@/components/gaze-button'
import { ServerDown } from '@/components/server-down'
import { TwoPressButton } from '@/components/two-press-button'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Field, FieldError, FieldLabel } from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import { sosService } from '@/services/sos-service'
import { sosContactFormSchema, type SosContact, type SosContactForm } from '@/validators/sos-validator'

const MAX_CONTACTS = 10
const EMPTY: SosContactForm = { contact_name: '', contact_number: '', email_address: '', relationship: '' }
const FIELDS = [
  { name: 'contact_name', label: 'Name', autoComplete: 'name', type: 'text' },
  { name: 'relationship', label: 'Relationship (optional), e.g. Mother', autoComplete: 'off', type: 'text' },
  { name: 'contact_number', label: 'Mobile number', autoComplete: 'tel', type: 'tel' },
  { name: 'email_address', label: 'Email', autoComplete: 'email', type: 'email' },
] as const

type Load = { state: 'loading' } | { state: 'error'; message: string } | { state: 'ready'; contacts: SosContact[] }
type Notice = { kind: 'ok' | 'error'; text: string } | null

const toForm = (c: SosContact): SosContactForm => ({
  contact_name: c.contact_name,
  contact_number: c.contact_number ?? '',
  email_address: c.email_address ?? '',
  relationship: c.relationship ?? '',
})

/** Screen 15a: emergency contacts, usually filled in by a caregiver. */
export function SosContactsPage() {
  const navigate = useNavigate()
  const [load, setLoad] = useState<Load>({ state: 'loading' })
  const [attempt, setAttempt] = useState(0)
  const [editing, setEditing] = useState<number | 'new' | null>(null)
  const [notice, setNotice] = useState<Notice>(null)
  const form = useForm<SosContactForm>({ resolver: zodResolver(sosContactFormSchema), defaultValues: EMPTY })

  useEffect(() => {
    let current = true
    sosService
      .getOverview()
      .then((o) => current && setLoad({ state: 'ready', contacts: o.contacts }))
      .catch((err) => current && setLoad({ state: 'error', message: errorMessage(err, 'Could not load contacts.') }))
    return () => {
      current = false
    }
  }, [attempt])

  const reload = () => setAttempt((n) => n + 1)

  const startEdit = (target: SosContact | 'new') => {
    setNotice(null)
    form.reset(target === 'new' ? EMPTY : toForm(target))
    setEditing(target === 'new' ? 'new' : target.contact_id)
  }

  const onSubmit = form.handleSubmit(async (values) => {
    setNotice(null)
    try {
      if (editing === 'new') await sosService.addContact(values)
      else if (editing !== null) await sosService.updateContact(editing, values)
      setNotice({ kind: 'ok', text: `${values.contact_name} is saved.` })
      setEditing(null)
      reload()
    } catch (err) {
      setNotice({ kind: 'error', text: errorMessage(err, 'The contact was not saved.') })
    }
  })

  const remove = async (contact: SosContact) => {
    setNotice(null)
    try {
      await sosService.deleteContact(contact.contact_id)
      setNotice({ kind: 'ok', text: `${contact.contact_name} was removed.` })
      reload()
    } catch (err) {
      setNotice({ kind: 'error', text: errorMessage(err, 'The contact was not removed.') })
    }
  }

  const contactForm = (
    <form onSubmit={onSubmit} noValidate className="bg-card grid gap-5 rounded-2xl border-2 p-6 md:grid-cols-2">
      <h2 className="text-2xl font-bold md:col-span-2">{editing === 'new' ? 'Add a contact' : 'Change contact'}</h2>
      {FIELDS.map(({ name, label, autoComplete, type }) => (
        <Controller
          key={name}
          control={form.control}
          name={name}
          render={({ field, fieldState }) => (
            <Field data-invalid={fieldState.invalid}>
              <FieldLabel htmlFor={`contact-${name}`} className="text-lg">{label}</FieldLabel>
              <Input id={`contact-${name}`} type={type} autoComplete={autoComplete} className="h-14 text-xl"
                aria-invalid={fieldState.invalid} {...field} />
              {fieldState.invalid && <FieldError errors={[fieldState.error]} />}
            </Field>
          )}
        />
      ))}
      <p className="text-muted-foreground text-base md:col-span-2">
        SOS alerts go by email. SMS is not set up yet, so a contact with only a mobile number will not be reached.
      </p>
      <div className="flex flex-wrap gap-6 md:col-span-2">
        <GazeButton type="submit" disabled={form.formState.isSubmitting}>
          {form.formState.isSubmitting ? <LoaderCircle className="animate-spin" aria-hidden /> : <Save aria-hidden />}
          Save contact
        </GazeButton>
        <GazeButton type="button" variant="outline" onClick={() => setEditing(null)}>
          <X aria-hidden />
          Cancel
        </GazeButton>
      </div>
    </form>
  )

  return (
    <main className="bg-background text-foreground mx-auto flex min-h-svh max-w-5xl flex-col gap-8 p-6">
      <header className="flex flex-wrap items-center justify-between gap-6">
        <div>
          <h1 className="text-4xl font-bold">Emergency contacts</h1>
          <p className="text-muted-foreground mt-2 text-xl">A caregiver can fill this in with a keyboard.</p>
        </div>
        <GazeButton variant="outline" onClick={() => void navigate('/sos')}>
          <ArrowLeft aria-hidden />
          Back to SOS
        </GazeButton>
      </header>

      {notice && (
        <Alert variant={notice.kind === 'error' ? 'destructive' : 'default'} role="status">
          <AlertDescription className="text-lg">{notice.text}</AlertDescription>
        </Alert>
      )}

      {load.state === 'loading' && <LoaderCircle className="text-muted-foreground mx-auto size-12 animate-spin" aria-label="Loading" />}
      {load.state === 'error' && (
        <div className="flex justify-center">
          <ServerDown message={load.message} onRetry={() => { setLoad({ state: 'loading' }); reload() }} />
        </div>
      )}

      {load.state === 'ready' && (
        <>
          {editing === 'new' ? contactForm : (
            <GazeButton
              className="self-start"
              disabled={load.contacts.length >= MAX_CONTACTS || editing !== null}
              onClick={() => startEdit('new')}
            >
              <UserPlus aria-hidden />
              {load.contacts.length >= MAX_CONTACTS ? `Up to ${MAX_CONTACTS} contacts` : 'Add a contact'}
            </GazeButton>
          )}

          {load.contacts.length === 0 && editing !== 'new' && (
            <p className="text-muted-foreground text-xl">No contacts yet. SOS cannot alert anyone until you add one.</p>
          )}

          <ul className="flex flex-col gap-6">
            {load.contacts.map((c) =>
              editing === c.contact_id ? (
                <li key={c.contact_id}>{contactForm}</li>
              ) : (
                <li key={c.contact_id} className="bg-card flex flex-wrap items-center justify-between gap-6 rounded-2xl border-2 p-6">
                  <div className="min-w-0 flex-1 space-y-1">
                    <p className="text-2xl font-semibold">
                      {c.contact_name}
                      {c.relationship && <span className="text-muted-foreground font-normal"> ({c.relationship})</span>}
                    </p>
                    {c.email_address && <p className="text-xl break-words">Email: {c.email_address}</p>}
                    {c.contact_number && <p className="text-xl">Mobile: {c.contact_number}</p>}
                    {!c.email_address && (
                      <p className="text-destructive text-lg font-semibold">
                        SOS can't text this contact yet. Add an email so they get alerts.
                      </p>
                    )}
                  </div>
                  <div className="flex flex-wrap gap-6">
                    <GazeButton variant="outline" disabled={editing !== null} onClick={() => startEdit(c)}>
                      <Pencil aria-hidden />
                      Edit
                    </GazeButton>
                    <TwoPressButton icon={Trash2} label="Delete" confirmLabel="Yes, delete" disabled={editing !== null}
                      onConfirm={() => void remove(c)} />
                  </div>
                </li>
              ),
            )}
          </ul>
        </>
      )}
    </main>
  )
}
