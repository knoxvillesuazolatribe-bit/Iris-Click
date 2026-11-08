import { Copy, Link2, LoaderCircle, Monitor, Trash2 } from 'lucide-react'
import { useCallback, useEffect, useState } from 'react'
import { errorMessage } from '@/api/app-client'
import { ConfirmDialog } from '@/components/confirm-dialog'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Field, FieldDescription, FieldLabel } from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import {
  computersService,
  type ApprovalLink,
  type ApprovedComputer,
  type ComputerList,
} from '@/services/computers-service'

const DATE = new Intl.DateTimeFormat(undefined, { dateStyle: 'medium', timeStyle: 'short' })
const STATUS_TEXT: Record<ApprovedComputer['status'], string> = {
  approved: 'Approved',
  waiting: 'Link not opened yet',
  expired: 'Link expired',
}

type Notice = { kind: 'ok' | 'error'; text: string } | null

/**
 * Admin user page (website): the computers where this person's name shows on the
 * sign-in screen. Approve the computer you are on, or make a one-time link to open
 * on the person's computer.
 */
export function AdminApprovedComputersCard({ userId, name }: { userId: number; name: string }) {
  const [list, setList] = useState<ComputerList | null>(null)
  const [label, setLabel] = useState('')
  const [busy, setBusy] = useState<'here' | 'link' | null>(null)
  const [link, setLink] = useState<ApprovalLink | null>(null)
  const [notice, setNotice] = useState<Notice>(null)
  const [removing, setRemoving] = useState<ApprovedComputer | null>(null)
  const [removeBusy, setRemoveBusy] = useState(false)

  const reload = useCallback(() => {
    computersService.list(userId).then(setList, (e: unknown) =>
      setNotice({ kind: 'error', text: errorMessage(e, 'The computers could not be loaded.') }))
  }, [userId])

  useEffect(reload, [reload])

  const approveHere = () => {
    setBusy('here')
    setNotice(null)
    computersService.approveHere(userId, label).then(
      () => {
        setNotice({ kind: 'ok', text: `This computer is approved for ${name}. Sign out so ${name} can pick their name.` })
        setLabel('')
        reload()
      },
      (e: unknown) => setNotice({ kind: 'error', text: errorMessage(e, 'This computer could not be approved.') }),
    ).finally(() => setBusy(null))
  }

  const makeLink = () => {
    setBusy('link')
    setNotice(null)
    computersService.makeLink(userId, label).then(
      (made) => {
        setLink(made)
        setLabel('')
        reload()
      },
      (e: unknown) => setNotice({ kind: 'error', text: errorMessage(e, 'The link could not be made.') }),
    ).finally(() => setBusy(null))
  }

  const linkUrl = link ? `${window.location.origin}${link.path}` : ''

  const copy = () => {
    navigator.clipboard.writeText(linkUrl).then(
      () => setNotice({ kind: 'ok', text: 'Link copied. Send it to the person’s helper.' }),
      () => setNotice({ kind: 'error', text: 'Copying did not work. Select the link and copy it.' }),
    )
  }

  const remove = () => {
    if (!removing) return
    setRemoveBusy(true)
    computersService.remove(userId, removing.computer_id).then(
      () => {
        setNotice({ kind: 'ok', text: `“${removing.label}” removed. ${name}’s name no longer shows there.` })
        reload()
      },
      (e: unknown) => setNotice({ kind: 'error', text: errorMessage(e, 'That computer could not be removed.') }),
    ).finally(() => {
      setRemoveBusy(false)
      setRemoving(null)
    })
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Approved computers</CardTitle>
        <CardDescription>
          On the website, {name}’s name shows only on these computers. Approve each computer once.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-6">
        {list && !list.lock_on && (
          <Alert>
            <AlertDescription>
              The computer lock is off, so the access code still protects the website. Approvals made now
              start working when the lock is turned on.
            </AlertDescription>
          </Alert>
        )}
        {notice && (
          <Alert variant={notice.kind === 'error' ? 'destructive' : 'default'} role={notice.kind === 'error' ? 'alert' : 'status'}>
            <AlertDescription>{notice.text}</AlertDescription>
          </Alert>
        )}

        <Field>
          <FieldLabel htmlFor={`computer-label-${userId}`}>Computer name (optional)</FieldLabel>
          <Input id={`computer-label-${userId}`} value={label} maxLength={80} autoComplete="off"
            placeholder="For example: Home laptop" onChange={(e) => setLabel(e.target.value)} />
          <FieldDescription>Helps you tell the computers apart later.</FieldDescription>
        </Field>
        <div className="flex flex-wrap gap-3">
          <Button type="button" disabled={busy !== null} onClick={approveHere}>
            {busy === 'here' ? <LoaderCircle className="animate-spin" aria-hidden /> : <Monitor aria-hidden />}
            Approve this computer
          </Button>
          <Button type="button" variant="outline" disabled={busy !== null} onClick={makeLink}>
            {busy === 'link' ? <LoaderCircle className="animate-spin" aria-hidden /> : <Link2 aria-hidden />}
            Make approval link
          </Button>
        </div>

        {link && (
          <div className="bg-muted space-y-3 rounded-lg p-4">
            <p className="font-medium">
              Open this link on {name}’s computer. It works once, until {DATE.format(new Date(link.expires_at))}.
            </p>
            <div className="flex flex-wrap gap-2">
              <Input readOnly value={linkUrl} aria-label="Approval link" className="min-w-0 flex-1 font-mono text-sm"
                onFocus={(e) => e.target.select()} />
              <Button type="button" variant="outline" onClick={copy}><Copy aria-hidden /> Copy</Button>
            </div>
          </div>
        )}

        {list && list.computers.length === 0 && (
          <p className="text-muted-foreground">No computers yet.</p>
        )}
        {list && list.computers.length > 0 && (
          <ul className="divide-y rounded-lg border">
            {list.computers.map((c) => (
              <li key={c.computer_id} className="flex flex-wrap items-center justify-between gap-3 p-4">
                <div className="space-y-1">
                  <p className="flex flex-wrap items-center gap-2 font-medium">
                    {c.label}
                    <Badge variant={c.status === 'approved' ? 'default' : 'secondary'}>{STATUS_TEXT[c.status]}</Badge>
                    {c.this_computer && <Badge variant="outline">This computer</Badge>}
                  </p>
                  <p className="text-muted-foreground text-sm">
                    {c.status === 'approved' && c.last_used_at && `Last used ${DATE.format(new Date(c.last_used_at))}`}
                    {c.status === 'waiting' && c.code_expires_at && `Link works until ${DATE.format(new Date(c.code_expires_at))}`}
                    {c.status === 'expired' && 'Make a new link if it is still needed.'}
                  </p>
                </div>
                <Button type="button" variant="outline" size="sm" onClick={() => setRemoving(c)}>
                  <Trash2 aria-hidden /> Remove
                </Button>
              </li>
            ))}
          </ul>
        )}
      </CardContent>
      {removing && (
        <ConfirmDialog
          title={`Remove “${removing.label}”?`}
          text={removing.status === 'approved'
            ? `${name}’s name will no longer show on that computer.`
            : 'The link will stop working.'}
          confirmLabel="Remove"
          busy={removeBusy}
          onConfirm={remove}
          onCancel={() => setRemoving(null)}
        />
      )}
    </Card>
  )
}
