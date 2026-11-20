import { useState } from 'react'
import { useAppName } from '@/lib/use-app-name'
import { cn } from '@/lib/utils'
import type { Report } from '@/validators/admin-validator'

/** The same design as the exported PDF (server/app/services/report_pdf.py): keep the two in step. */
type Tone = 'teal' | 'green' | 'red' | 'amber' | 'slate'

const TONE: Record<Tone, { card: string; value: string; pill: string }> = {
  teal: { card: 'bg-teal-50 border-teal-200', value: 'text-teal-700', pill: 'bg-teal-50 border-teal-200 text-teal-700' },
  green: { card: 'bg-emerald-50 border-emerald-200', value: 'text-emerald-700', pill: 'bg-emerald-50 border-emerald-200 text-emerald-700' },
  red: { card: 'bg-red-50 border-red-200', value: 'text-red-700', pill: 'bg-red-50 border-red-200 text-red-700' },
  amber: { card: 'bg-amber-50 border-amber-200', value: 'text-amber-700', pill: 'bg-amber-50 border-amber-200 text-amber-700' },
  slate: { card: 'bg-slate-50 border-slate-200', value: 'text-slate-700', pill: 'bg-slate-50 border-slate-200 text-slate-700' },
}
const REASON_COLUMNS = new Set(['Failure reason', 'Problem'])

/** Red for failures, green for successes, amber for waiting, teal for totals and averages. */
function kpiTone(label: string): Tone {
  const text = label.toLowerCase()
  if (text.includes('average') || text.includes('accuracy')) return 'teal'
  if (text.includes('fail')) return 'red'
  if (text.includes('success') || text === 'sent') return 'green'
  if (text.includes('not sent') || text.includes('pending')) return 'amber'
  return 'teal'
}

function statusTone(value: string): Tone {
  return ({ successful: 'green', sent: 'green', failed: 'red', pending: 'amber' } as Record<string, Tone>)[
    value.trim().toLowerCase()] ?? 'slate'
}

function Pill({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl border border-teal-200 bg-teal-50 px-4 py-2.5">
      <p className="text-xs font-bold tracking-wide text-teal-700">{label}</p>
      <p className="font-semibold text-slate-900">{value}</p>
    </div>
  )
}

export function ReportPreview({ report }: { report: Report }) {
  const appName = useAppName()
  const [prepared] = useState(() => new Date().toLocaleString('en-PH', { dateStyle: 'long', timeStyle: 'short' }))
  return (
    <section aria-label={report.title} className="bg-card space-y-6 rounded-2xl border p-6 shadow-sm">
      <header className="space-y-4">
        <div className="flex items-center gap-4">
          <img src="/irisclick-logo.png" alt="" className="h-14 w-auto" />
          <div>
            <p className="text-xs font-bold tracking-wide text-teal-700">PDAO REPORT</p>
            <h2 className="text-2xl font-bold text-slate-900">{appName}: {report.title}</h2>
          </div>
        </div>
        <div className="h-1.5 rounded-full bg-teal-700" />
        <div className="grid gap-3 sm:grid-cols-3">
          <Pill label="PERIOD" value={`${report.date_from} to ${report.date_to}`} />
          <Pill label="USER" value={report.user_name ?? 'Everyone'} />
          <Pill label="PREPARED" value={prepared} />
        </div>
        {report.note && <p className="text-muted-foreground text-sm">{report.note}</p>}
      </header>

      {report.summary.length > 0 && (
        <dl aria-label="Summary" className="grid grid-cols-[repeat(auto-fit,minmax(10rem,1fr))] gap-3">
          {report.summary.map((item) => {
            const tone = TONE[kpiTone(item.label)]
            return (
              <div key={item.label} className={cn('rounded-xl border px-4 py-3', tone.card)}>
                <dt className="text-xs font-bold tracking-wide text-slate-500 uppercase">{item.label}</dt>
                <dd className={cn('text-3xl font-bold', tone.value)}>{item.value}</dd>
              </div>
            )
          })}
        </dl>
      )}

      <div className="overflow-x-auto rounded-xl border">
        <table className="w-full text-left text-sm">
          <thead className="border-b-2 border-teal-800 bg-teal-700 text-white">
            <tr>{report.columns.map((c) => <th key={c} className="px-3 py-3 font-semibold">{c}</th>)}</tr>
          </thead>
          <tbody>
            {report.rows.map((row, i) => (
              <tr key={i} className="border-b align-middle last:border-0 even:bg-slate-50">
                {row.map((cell, j) => {
                  const column = report.columns[j]
                  return (
                    <td key={j} className="px-3 py-2.5 break-words whitespace-pre-wrap">
                      {!cell.trim() ? <span className="text-slate-400">—</span>
                        : column === 'Status' ? (
                          <span className={cn('inline-block rounded-full border px-2.5 py-0.5 text-xs font-bold', TONE[statusTone(cell)].pill)}>
                            {cell}
                          </span>
                        ) : <span className={cn(REASON_COLUMNS.has(column) && 'text-amber-700')}>{cell}</span>}
                    </td>
                  )
                })}
              </tr>
            ))}
          </tbody>
        </table>
        {report.rows.length === 0 && (
          <p className="text-muted-foreground px-3 py-4">No records found for these filters. You can still export the report.</p>
        )}
      </div>
      {report.rows.length > 0 && <p className="text-muted-foreground text-sm">{report.rows.length} row(s).</p>}
    </section>
  )
}
