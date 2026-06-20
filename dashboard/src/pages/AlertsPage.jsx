// src/pages/AlertsPage.jsx
import { useState } from 'react'
import { formatDistanceToNow, parseISO } from 'date-fns'
import { useApi } from '../hooks/useApi.js'
import { getAlerts, getAlertStats, resolveAlert } from '../lib/api.js'
import { Card, CardHeader, Badge, Spinner, EmptyState } from '../components/layout/UI.jsx'
import { CheckCircle, XCircle, Eye } from 'lucide-react'

const STATUS_OPTS = ['', 'open', 'investigating', 'resolved', 'false_positive']
const SEV_OPTS    = ['', 'critical', 'high', 'medium', 'low']

export default function AlertsPage() {
  const [status, setStatus]   = useState('open')
  const [severity, setSeverity] = useState('')
  const [page, setPage]       = useState(1)

  const params = { page, size: 25, ...(status ? { status } : {}), ...(severity ? { severity } : {}) }
  const { data, loading, refetch } = useApi(() => getAlerts(params), [status, severity, page], { pollInterval: 15_000 })
  const { data: stats } = useApi(getAlertStats, [], { pollInterval: 20_000 })

  const alerts = data?.alerts ?? []
  const total  = data?.total ?? 0

  const handle = async (id, newStatus) => {
    await resolveAlert(id, { status: newStatus })
    refetch()
  }

  const kpis = stats?.last_24h ?? {}

  return (
    <div style={{ animation: 'fadeUp 0.3s ease both' }}>
      {/* Header */}
      <div style={{ marginBottom: 20 }}>
        <div style={{ fontFamily: 'var(--font-display)', fontWeight: 800, fontSize: 22, marginBottom: 2 }}>
          Alerts
        </div>
        <div style={{ color: 'var(--text-3)', fontSize: 12 }}>Fraud alert management and resolution</div>
      </div>

      {/* Stats strip */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 10, marginBottom: 18 }}>
        {[
          { label: 'Open',     val: kpis.open_alerts,    color: 'var(--blue)' },
          { label: 'Critical', val: kpis.critical_alerts, color: 'var(--red)' },
          { label: 'High',     val: kpis.high_alerts,     color: 'var(--orange)' },
          { label: 'False Pos',val: kpis.false_positives, color: 'var(--text-3)' },
        ].map(({ label, val, color }) => (
          <Card key={label} style={{ padding: '12px 16px' }}>
            <div style={{ color: 'var(--text-3)', fontSize: 10, textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: 6 }}>{label}</div>
            <div style={{ fontSize: 24, fontFamily: 'var(--font-display)', fontWeight: 700, color }}>{val ?? '—'}</div>
          </Card>
        ))}
      </div>

      <Card>
        {/* Filters */}
        <div style={{
          padding: '12px 16px', borderBottom: '1px solid var(--border)',
          display: 'flex', gap: 10, alignItems: 'center', flexWrap: 'wrap',
        }}>
          <span style={{ color: 'var(--text-3)', fontSize: 11 }}>Filter:</span>
          {['Status', 'Severity'].map((label, i) => {
            const opts  = i === 0 ? STATUS_OPTS : SEV_OPTS
            const val   = i === 0 ? status : severity
            const setVal= i === 0 ? (v) => { setStatus(v); setPage(1) } : (v) => { setSeverity(v); setPage(1) }
            return (
              <select
                key={label}
                value={val}
                onChange={e => setVal(e.target.value)}
                style={{
                  background: 'var(--bg-2)', border: '1px solid var(--border)',
                  color: 'var(--text-2)', borderRadius: 4, padding: '4px 10px',
                  fontSize: 11, fontFamily: 'var(--font-mono)', cursor: 'pointer',
                }}
              >
                <option value="">{label}: All</option>
                {opts.filter(Boolean).map(o => (
                  <option key={o} value={o}>{o}</option>
                ))}
              </select>
            )
          })}
          <span style={{ marginLeft: 'auto', color: 'var(--text-3)', fontSize: 11 }}>
            {total} results
          </span>
        </div>

        {/* Table */}
        <div style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse' }}>
            <thead>
              <tr style={{ borderBottom: '1px solid var(--border)' }}>
                {['Severity', 'Type', 'Message', 'Score', 'Status', 'When', 'Actions'].map(h => (
                  <th key={h} style={{
                    padding: '8px 16px', textAlign: 'left', fontSize: 10,
                    color: 'var(--text-3)', fontWeight: 500,
                    textTransform: 'uppercase', letterSpacing: '0.08em',
                    whiteSpace: 'nowrap',
                  }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {loading && (
                <tr><td colSpan={7} style={{ padding: 32, textAlign: 'center' }}><Spinner /></td></tr>
              )}
              {!loading && alerts.length === 0 && (
                <tr><td colSpan={7}><EmptyState message="No alerts match these filters" /></td></tr>
              )}
              {alerts.map(a => (
                <tr
                  key={a.id}
                  style={{ borderBottom: '1px solid var(--border)', transition: 'background 0.15s' }}
                  onMouseEnter={e => e.currentTarget.style.background = 'var(--bg-2)'}
                  onMouseLeave={e => e.currentTarget.style.background = 'transparent'}
                >
                  <td style={{ padding: '10px 16px' }}><Badge label={a.severity} variant={a.severity} /></td>
                  <td style={{ padding: '10px 16px', fontSize: 11, color: 'var(--text-2)', whiteSpace: 'nowrap' }}>
                    {a.alert_type.replace(/_/g, ' ')}
                  </td>
                  <td style={{ padding: '10px 16px', fontSize: 12, maxWidth: 320 }}>
                    <div className="truncate" style={{ color: 'var(--text-2)' }}>{a.message}</div>
                  </td>
                  <td style={{ padding: '10px 16px', fontFamily: 'var(--font-mono)', fontSize: 11,
                    color: a.fraud_score > 0.8 ? 'var(--red)' : a.fraud_score > 0.55 ? 'var(--orange)' : 'var(--text-2)' }}>
                    {a.fraud_score != null ? (a.fraud_score * 100).toFixed(0) + '%' : '—'}
                  </td>
                  <td style={{ padding: '10px 16px' }}><Badge label={a.status} variant={a.status} /></td>
                  <td style={{ padding: '10px 16px', fontSize: 11, color: 'var(--text-3)', whiteSpace: 'nowrap' }}>
                    {formatDistanceToNow(parseISO(a.created_at), { addSuffix: true })}
                  </td>
                  <td style={{ padding: '10px 16px' }}>
                    {a.status === 'open' && (
                      <div style={{ display: 'flex', gap: 8 }}>
                        <button onClick={() => handle(a.id, 'investigating')} title="Investigate"
                          style={{ background: 'none', border: 'none', color: 'var(--blue)', cursor: 'pointer', padding: 2 }}>
                          <Eye size={13} />
                        </button>
                        <button onClick={() => handle(a.id, 'resolved')} title="Resolve"
                          style={{ background: 'none', border: 'none', color: 'var(--green)', cursor: 'pointer', padding: 2 }}>
                          <CheckCircle size={13} />
                        </button>
                        <button onClick={() => handle(a.id, 'false_positive')} title="False positive"
                          style={{ background: 'none', border: 'none', color: 'var(--text-3)', cursor: 'pointer', padding: 2 }}>
                          <XCircle size={13} />
                        </button>
                      </div>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {/* Pagination */}
        {total > 25 && (
          <div style={{ padding: '12px 16px', borderTop: '1px solid var(--border)', display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
            <button disabled={page === 1} onClick={() => setPage(p => p - 1)}
              style={{ padding: '4px 12px', background: 'var(--bg-2)', border: '1px solid var(--border)', borderRadius: 4, color: 'var(--text-2)', fontSize: 11, cursor: 'pointer' }}>
              Prev
            </button>
            <span style={{ padding: '4px 8px', color: 'var(--text-3)', fontSize: 11 }}>
              Page {page} of {Math.ceil(total / 25)}
            </span>
            <button disabled={page >= Math.ceil(total / 25)} onClick={() => setPage(p => p + 1)}
              style={{ padding: '4px 12px', background: 'var(--bg-2)', border: '1px solid var(--border)', borderRadius: 4, color: 'var(--text-2)', fontSize: 11, cursor: 'pointer' }}>
              Next
            </button>
          </div>
        )}
      </Card>
    </div>
  )
}
