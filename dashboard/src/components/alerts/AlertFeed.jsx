// src/components/alerts/AlertFeed.jsx
import { useState } from 'react'
import { formatDistanceToNow, parseISO } from 'date-fns'
import { useApi } from '../../hooks/useApi.js'
import { getAlerts, resolveAlert } from '../../lib/api.js'
import { Card, CardHeader, Badge, Spinner, EmptyState } from '../layout/UI.jsx'
import { CheckCircle, XCircle, AlertTriangle } from 'lucide-react'

function AlertRow({ alert, onUpdate }) {
  const [busy, setBusy] = useState(false)

  const handle = async (status) => {
    setBusy(true)
    try {
      await resolveAlert(alert.id, { status })
      onUpdate()
    } finally {
      setBusy(false)
    }
  }

  const isCritical = alert.severity === 'critical'

  return (
    <div style={{
      padding: '12px 18px',
      borderBottom: '1px solid var(--border)',
      display: 'flex', alignItems: 'flex-start', gap: 12,
      background: isCritical ? 'rgba(255,59,59,0.03)' : 'transparent',
      transition: 'background 0.2s',
      animation: 'fadeUp 0.3s ease both',
    }}>
      {/* Severity dot */}
      <div style={{
        width: 6, height: 6, borderRadius: '50%', flexShrink: 0, marginTop: 5,
        background: isCritical ? 'var(--red)' : alert.severity === 'high' ? 'var(--orange)' : 'var(--yellow)',
        boxShadow: isCritical ? '0 0 6px var(--red)' : 'none',
        animation: isCritical ? 'pulse-red 1.5s ease-in-out infinite' : 'none',
      }} />

      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 3 }}>
          <Badge label={alert.severity} variant={alert.severity} />
          <span style={{ color: 'var(--text-3)', fontSize: 10 }}>
            {formatDistanceToNow(parseISO(alert.created_at), { addSuffix: true })}
          </span>
        </div>
        <div style={{ fontSize: 12, lineHeight: 1.5, color: 'var(--text-2)', marginBottom: 4 }}>
          {alert.message}
        </div>
        <div style={{ fontSize: 10, color: 'var(--text-3)', fontFamily: 'var(--font-mono)' }}>
          score: <span style={{ color: isCritical ? 'var(--red)' : 'var(--text-2)' }}>
            {alert.fraud_score != null ? (alert.fraud_score * 100).toFixed(0) + '%' : '—'}
          </span>
          {' · '}{alert.alert_type.replace(/_/g, ' ')}
        </div>
      </div>

      {alert.status === 'open' && (
        <div style={{ display: 'flex', gap: 6, flexShrink: 0 }}>
          <button
            onClick={() => handle('resolved')} disabled={busy}
            title="Mark resolved"
            style={{ background: 'none', border: 'none', color: 'var(--green)', padding: 2, opacity: busy ? 0.4 : 1 }}
          >
            <CheckCircle size={14} />
          </button>
          <button
            onClick={() => handle('false_positive')} disabled={busy}
            title="False positive"
            style={{ background: 'none', border: 'none', color: 'var(--text-3)', padding: 2, opacity: busy ? 0.4 : 1 }}
          >
            <XCircle size={14} />
          </button>
        </div>
      )}
    </div>
  )
}

export default function AlertFeed({ maxHeight = 360 }) {
  const { data, loading, refetch } = useApi(
    () => getAlerts({ status: 'open', size: 20 }),
    [],
    { pollInterval: 10_000 }
  )

  const alerts = data?.alerts ?? []

  return (
    <Card>
      <CardHeader
        title="Live Alert Feed"
        subtitle="Auto-refreshes every 10s"
        action={
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            {alerts.length > 0 && (
              <span style={{
                background: 'var(--red)', color: '#fff', borderRadius: 99,
                fontSize: 10, fontWeight: 700, padding: '1px 7px',
              }}>
                {alerts.length}
              </span>
            )}
            <AlertTriangle size={13} color="var(--text-3)" />
          </div>
        }
      />
      <div style={{ maxHeight, overflowY: 'auto' }}>
        {loading ? (
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 32 }}>
            <Spinner />
          </div>
        ) : alerts.length === 0 ? (
          <EmptyState message="No open alerts — system is healthy" />
        ) : (
          alerts.map(a => <AlertRow key={a.id} alert={a} onUpdate={refetch} />)
        )}
      </div>
    </Card>
  )
}
