// src/pages/ActivityPage.jsx
import { useState } from 'react'
import { formatDistanceToNow, parseISO } from 'date-fns'
import { useApi } from '../hooks/useApi.js'
import { getTransactions } from '../lib/api.js'
import { Card, Badge, Spinner, EmptyState } from '../components/layout/UI.jsx'

const RISK_OPTS = ['', 'critical', 'high', 'medium', 'low']

function ScoreBar({ score }) {
  if (score == null) return <span style={{ color: 'var(--text-3)' }}>—</span>
  const pct = (score * 100).toFixed(0)
  const color = score >= 0.8 ? 'var(--red)' : score >= 0.55 ? 'var(--orange)' : score >= 0.3 ? 'var(--yellow)' : 'var(--green)'
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
      <div style={{ width: 48, height: 4, background: 'var(--bg-3)', borderRadius: 2, overflow: 'hidden' }}>
        <div style={{ width: pct + '%', height: '100%', background: color, borderRadius: 2, transition: 'width 0.3s' }} />
      </div>
      <span style={{ fontSize: 11, color, fontFamily: 'var(--font-mono)', width: 28 }}>{pct}%</span>
    </div>
  )
}

export default function ActivityPage() {
  const [riskTier, setRiskTier] = useState('')
  const [isForaud, setIsFraud]  = useState('')
  const [page, setPage]         = useState(1)

  const params = {
    page, size: 30,
    ...(riskTier ? { risk_tier: riskTier } : {}),
    ...(isForaud === 'true' ? { is_fraud: true } : isForaud === 'false' ? { is_fraud: false } : {}),
  }
  const { data, loading } = useApi(() => getTransactions(params), [riskTier, isForaud, page], { pollInterval: 8_000 })

  const txns  = data?.transactions ?? []
  const total = data?.total ?? 0

  return (
    <div style={{ animation: 'fadeUp 0.3s ease both' }}>
      <div style={{ marginBottom: 20 }}>
        <div style={{ fontFamily: 'var(--font-display)', fontWeight: 800, fontSize: 22, marginBottom: 2 }}>Transactions</div>
        <div style={{ color: 'var(--text-3)', fontSize: 12 }}>Live transaction feed with fraud scores · refreshes every 8s</div>
      </div>

      <Card>
        {/* Filters */}
        <div style={{ padding: '12px 16px', borderBottom: '1px solid var(--border)', display: 'flex', gap: 10, alignItems: 'center' }}>
          <select
            value={riskTier} onChange={e => { setRiskTier(e.target.value); setPage(1) }}
            style={{ background: 'var(--bg-2)', border: '1px solid var(--border)', color: 'var(--text-2)', borderRadius: 4, padding: '4px 10px', fontSize: 11, fontFamily: 'var(--font-mono)' }}
          >
            <option value="">Risk: All</option>
            {RISK_OPTS.filter(Boolean).map(o => <option key={o} value={o}>{o}</option>)}
          </select>
          <select
            value={isForaud} onChange={e => { setIsFraud(e.target.value); setPage(1) }}
            style={{ background: 'var(--bg-2)', border: '1px solid var(--border)', color: 'var(--text-2)', borderRadius: 4, padding: '4px 10px', fontSize: 11, fontFamily: 'var(--font-mono)' }}
          >
            <option value="">Label: All</option>
            <option value="true">Fraud only</option>
            <option value="false">Legit only</option>
          </select>
          <span style={{ marginLeft: 'auto', color: 'var(--text-3)', fontSize: 11 }}>{total.toLocaleString()} transactions</span>
        </div>

        {/* Table */}
        <div style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse' }}>
            <thead>
              <tr style={{ borderBottom: '1px solid var(--border)' }}>
                {['ID', 'Amount', 'Type', 'Channel', 'Country', 'Fraud Score', 'Risk', 'Status', 'When'].map(h => (
                  <th key={h} style={{ padding: '8px 14px', textAlign: 'left', fontSize: 10, color: 'var(--text-3)', fontWeight: 500, textTransform: 'uppercase', letterSpacing: '0.08em', whiteSpace: 'nowrap' }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {loading && (
                <tr><td colSpan={9} style={{ padding: 32, textAlign: 'center' }}><Spinner /></td></tr>
              )}
              {!loading && txns.length === 0 && (
                <tr><td colSpan={9}><EmptyState message="No transactions found" /></td></tr>
              )}
              {txns.map(tx => (
                <tr key={tx.id}
                  style={{ borderBottom: '1px solid var(--border)', transition: 'background 0.15s' }}
                  onMouseEnter={e => e.currentTarget.style.background = 'var(--bg-2)'}
                  onMouseLeave={e => e.currentTarget.style.background = 'transparent'}
                >
                  <td style={{ padding: '9px 14px', fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--text-3)' }}>
                    {tx.external_tx_id?.slice(0, 14)}…
                  </td>
                  <td style={{ padding: '9px 14px', fontFamily: 'var(--font-mono)', fontSize: 12, fontWeight: 500,
                    color: tx.amount > 5000 ? 'var(--yellow)' : 'var(--text)' }}>
                    ${Number(tx.amount).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                  </td>
                  <td style={{ padding: '9px 14px', fontSize: 11, color: 'var(--text-2)' }}>
                    {tx.transaction_type?.replace(/_/g, ' ')}
                  </td>
                  <td style={{ padding: '9px 14px', fontSize: 11, color: 'var(--text-3)' }}>{tx.channel}</td>
                  <td style={{ padding: '9px 14px', fontSize: 11, fontFamily: 'var(--font-mono)', color: 'var(--text-2)' }}>
                    {tx.country_code ?? '—'}
                  </td>
                  <td style={{ padding: '9px 14px' }}><ScoreBar score={tx.fraud_score} /></td>
                  <td style={{ padding: '9px 14px' }}>
                    {tx.risk_tier ? <Badge label={tx.risk_tier} variant={tx.risk_tier} /> : <span style={{ color: 'var(--text-3)' }}>—</span>}
                  </td>
                  <td style={{ padding: '9px 14px', fontSize: 11 }}>
                    <span style={{
                      color: tx.status === 'flagged' ? 'var(--orange)'
                           : tx.status === 'approved' ? 'var(--green)'
                           : tx.status === 'declined' ? 'var(--red)' : 'var(--text-3)',
                    }}>{tx.status}</span>
                  </td>
                  <td style={{ padding: '9px 14px', fontSize: 10, color: 'var(--text-3)', whiteSpace: 'nowrap' }}>
                    {formatDistanceToNow(parseISO(tx.initiated_at), { addSuffix: true })}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {/* Pagination */}
        {total > 30 && (
          <div style={{ padding: '10px 16px', borderTop: '1px solid var(--border)', display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
            <button disabled={page === 1} onClick={() => setPage(p => p - 1)}
              style={{ padding: '4px 12px', background: 'var(--bg-2)', border: '1px solid var(--border)', borderRadius: 4, color: 'var(--text-2)', fontSize: 11, cursor: 'pointer' }}>
              Prev
            </button>
            <span style={{ padding: '4px 8px', color: 'var(--text-3)', fontSize: 11 }}>Page {page} / {Math.ceil(total / 30)}</span>
            <button disabled={page >= Math.ceil(total / 30)} onClick={() => setPage(p => p + 1)}
              style={{ padding: '4px 12px', background: 'var(--bg-2)', border: '1px solid var(--border)', borderRadius: 4, color: 'var(--text-2)', fontSize: 11, cursor: 'pointer' }}>
              Next
            </button>
          </div>
        )}
      </Card>
    </div>
  )
}
