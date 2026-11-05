import { Crosshair, Download, Eye, LoaderCircle, MessageSquare, Siren } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link, Navigate, useNavigate, useParams } from 'react-router'
import { errorMessage } from '@/api/app-client'
import { AdminLayout } from '@/components/admin-layout'
import { ExportSuccessDialog } from '@/components/export-success-dialog'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { adminService, type ReportQuery } from '@/services/admin-service'
import { REPORT_TYPES, type AdminUserRow, type Report, type ReportType } from '@/validators/admin-validator'

const REPORTS: Record<ReportType, { title: string; text: string; icon: typeof Siren }> = {
  calibration: { title: 'Calibration', text: 'Calibrations per person: accuracy, status and failures.', icon: Crosshair },
  communication: { title: 'Communication', text: 'Voice Communication use per person (message text optional).', icon: MessageSquare },
  sos: { title: 'SOS', text: 'Every SOS alert: who was alerted, how, and whether it was sent.', icon: Siren },
}

const iso = (d: Date) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`

/** Screen 31: choose a report. */
export function AdminReportsPage() {
  return (
    <AdminLayout title="Reports" description="Preview a report, then export it as a PDF.">
      <div className="grid gap-4 md:grid-cols-3">
        {REPORT_TYPES.map((type) => {
          const { title, text, icon: Icon } = REPORTS[type]
          return (
            <Link key={type} to={`/admin/reports/${type}`} className="focus-visible:ring-ring rounded-xl outline-none focus-visible:ring-4">
              <Card className="hover:border-primary h-full transition-colors">
                <CardHeader>
                  <CardTitle className="flex items-center gap-2 text-xl"><Icon aria-hidden />{title}</CardTitle>
                  <CardDescription>{text}</CardDescription>
                </CardHeader>
              </Card>
            </Link>
          )
        })}
      </div>
    </AdminLayout>
  )
}

type Export = { state: 'idle' } | { state: 'busy' } | { state: 'done'; fileName: string; bytes: number } | { state: 'error'; message: string }

/** Screens 34–36: one report with Display Report (preview) and Export Report (PDF). */
export function AdminReportPage() {
  const type = useParams().type as ReportType
  const navigate = useNavigate()
  const [dateFrom, setDateFrom] = useState(() => {
    const today = new Date()
    return iso(new Date(today.getFullYear(), today.getMonth(), today.getDate() - 29))
  })
  const [dateTo, setDateTo] = useState(() => iso(new Date()))
  const [userId, setUserId] = useState<number | null>(null)
  const [includeText, setIncludeText] = useState(false)
  const [users, setUsers] = useState<AdminUserRow[]>([])
  const [report, setReport] = useState<Report | null>(null)
  const [previewError, setPreviewError] = useState<string | null>(null)
  const [previewing, setPreviewing] = useState(false)
  const [exported, setExported] = useState<Export>({ state: 'idle' })

  useEffect(() => {
    let current = true
    adminService.users()
      .then((all) => current && setUsers(all.filter((u) => u.role === 'assistive_user')))
      .catch(() => undefined)
    return () => {
      current = false
    }
  }, [])

  if (!REPORT_TYPES.includes(type)) return <Navigate to="/admin/reports" replace />
  const meta = REPORTS[type]
  const query: ReportQuery = { date_from: dateFrom, date_to: dateTo, user_id: userId, include_text: includeText }
  const changed = () => {
    setReport(null)
    setExported({ state: 'idle' })
  }

  const preview = async () => {
    setPreviewing(true)
    setPreviewError(null)
    try {
      setReport(await adminService.report(type, query))
    } catch (err) {
      setPreviewError(errorMessage(err, 'The report could not be made.'))
    } finally {
      setPreviewing(false)
    }
  }

  const exportPdf = async () => {
    setExported({ state: 'busy' })
    try {
      const file = await adminService.exportPdf(type, query)
      setExported({ state: 'done', ...file })
    } catch (err) {
      setExported({ state: 'error', message: err instanceof Error ? err.message : 'The PDF could not be made.' })
    }
  }

  return (
    <AdminLayout title={`${meta.title} Report`} description={meta.text}
      actions={<Button asChild variant="outline"><Link to="/admin/reports">All reports</Link></Button>}>
      <Card>
        <CardContent className="flex flex-wrap items-end gap-4 pt-6">
          <div className="grid gap-1">
            <Label htmlFor="report-from">From</Label>
            <Input id="report-from" type="date" className="h-10" value={dateFrom} max={dateTo}
              onChange={(e) => { setDateFrom(e.target.value); changed() }} />
          </div>
          <div className="grid gap-1">
            <Label htmlFor="report-to">To</Label>
            <Input id="report-to" type="date" className="h-10" value={dateTo} min={dateFrom}
              onChange={(e) => { setDateTo(e.target.value); changed() }} />
          </div>
          <div className="grid gap-1">
            <Label htmlFor="report-user">User</Label>
            <select id="report-user" className="border-input bg-background h-10 rounded-md border px-3"
              value={userId ?? ''} onChange={(e) => { setUserId(e.target.value ? Number(e.target.value) : null); changed() }}>
              <option value="">Everyone</option>
              {users.map((u) => <option key={u.user_id} value={u.user_id}>{u.full_name}</option>)}
            </select>
          </div>
          {type === 'communication' && (
            <label className="flex items-center gap-2 pb-2">
              <input type="checkbox" className="size-4" checked={includeText}
                onChange={(e) => { setIncludeText(e.target.checked); changed() }} />
              Include message text
            </label>
          )}
          <div className="ml-auto flex gap-2">
            <Button variant="outline" disabled={previewing || !dateFrom || !dateTo} onClick={() => void preview()}>
              {previewing ? <LoaderCircle className="animate-spin" aria-hidden /> : <Eye aria-hidden />}
              Display Report
            </Button>
            <Button disabled={exported.state === 'busy' || !dateFrom || !dateTo} onClick={() => void exportPdf()}>
              {exported.state === 'busy' ? <LoaderCircle className="animate-spin" aria-hidden /> : <Download aria-hidden />}
              Export Report
            </Button>
          </div>
        </CardContent>
      </Card>

      {type === 'communication' && includeText && (
        <Alert>
          <AlertTitle>Messages may be private</AlertTitle>
          <AlertDescription>Viewing or exporting message text is recorded in the logs.</AlertDescription>
        </Alert>
      )}
      {exported.state === 'done' && (
        <ExportSuccessDialog fileName={exported.fileName} bytes={exported.bytes}
          onClose={() => void navigate('/admin/reports')} />
      )}
      {exported.state === 'error' && (
        <Alert variant="destructive" role="alert">
          <AlertTitle>Export failed</AlertTitle>
          <AlertDescription>{exported.message}</AlertDescription>
        </Alert>
      )}
      {previewError && (
        <Alert variant="destructive" role="alert"><AlertDescription>{previewError}</AlertDescription></Alert>
      )}

      {report && (
        <Card>
          <CardHeader>
            <CardTitle>{report.title}</CardTitle>
            <CardDescription>
              {report.date_from} to {report.date_to} · {report.user_name ?? 'Everyone'} · {report.rows.length} row(s)
              {report.note && <> · {report.note}</>}
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            {report.summary.length > 0 && (
              <dl aria-label="Summary" className="grid grid-cols-[repeat(auto-fill,minmax(11rem,1fr))] gap-3">
                {report.summary.map((item) => (
                  <div key={item.label} className="bg-muted rounded-lg px-3 py-2">
                    <dt className="text-muted-foreground text-xs">{item.label}</dt>
                    <dd className="text-lg font-semibold">{item.value}</dd>
                  </div>
                ))}
              </dl>
            )}
            {report.rows.length === 0 ? (
              <p className="text-muted-foreground">No records found for these filters. You can still export the report.</p>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-left text-sm">
                  <thead className="text-muted-foreground border-b">
                    <tr>{report.columns.map((c) => <th key={c} className="py-2 pr-4">{c}</th>)}</tr>
                  </thead>
                  <tbody>
                    {report.rows.map((row, i) => (
                      <tr key={i} className="border-b align-top last:border-0">
                        {row.map((cell, j) => <td key={j} className="py-2 pr-4 break-words whitespace-pre-wrap">{cell}</td>)}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </CardContent>
        </Card>
      )}
    </AdminLayout>
  )
}
