// src/pages/Overview.jsx
import { useState } from 'react'
import { AlertTriangle, Activity, Shield, TrendingUp } from 'lucide-react'
import { useApi } from '../hooks/useApi.js'
import { getSummary, getAlertStats } from '../lib/api.js'
import { StatCard } from '../components/layout/UI.jsx'
import TrendChart from '../components/charts/TrendChart.jsx'
import CategoryChart from '../components/charts/CategoryChart.jsx'
import AlertFeed from '../components/alerts/AlertFeed.jsx'

const PERIODS = ['1h', '24h', '7d', '30d']

function fmt(n, decimals = 0) {
  if (n == null) return '—'
  if (n >= 1_000_000) return (n / 1_000_000).toFixed(1) + 'M'
  if (n >= 1_000) return (n / 1_000).toFixed(1) + 'K'
  return Number(n).toFixed(decimals)
}

export default function Overview() {
  const [period, setPeriod] = useState('24h')
  const { data: summary } = useApi(() => getSummary(period), [period], { pollInterval: 15_000 })
  const { data: alertStats } = useApi(getAlertStats, [], { pollInterval: 20_000 })

  const fraudRate = summary ? (summary.fraud_rate * 100).toFixed(2) + '%' : '—'
  const openAlerts = alertStats?.last_24h?.open_alerts ?? summary?.open_alerts ?? 0
  const criticalAlerts = alertStats?.last_24h?.critical_alerts ?? summary?.critical_alerts ?? 0

  return (
    <div style={{ animation: 'fadeUp 0.3s ease both' }}>
      {/* Header */}
      <div style={{ marginBottom: 24, display: 'flex', alignItems: 'flex-end', justifyContent: 'space-between' }}>
        <div>
          <div style={{
            fontFamily: 'var(--font-display)', fontWeight: 800,
            fontSize: 22, letterSpacing: '-0.01em', marginBottom: 2,
          }}>
            Overview
          </div>
          <div style={{ color: 'var(--text-3)', fontSize: 12 }}>
            Real-time fraud monitoring dashboard
          </div>
        </div>

        {/* Period selector */}
        <div style={{ display: 'flex', gap: 4, background: 'var(--bg-2)', padding: 3, borderRadius: 6, border: '1px solid var(--border)' }}>
          {PERIODS.map(p => (
            <button
              key={p}
              onClick={() => setPeriod(p)}
              style={{
                padding: '4px 12px', borderRadius: 4, border: 'none', fontSize: 11,
                fontFamily: 'var(--font-mono)', cursor: 'pointer',
                background: period === p ? 'var(--bg-3)' : 'transparent',
                color: period === p ? 'var(--text)' : 'var(--text-3)',
                transition: 'all 0.15s',
              }}
            >
              {p}
            </button>
          ))}
        </div>
      </div>

      {/* KPI row */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 12, marginBottom: 20 }}>
        <StatCard
          label="Total Transactions"
          value={fmt(summary?.total_transactions)}
          sub={`${period} window`}
          color="var(--blue)"
          icon={Activity}
        />
        <StatCard
          label="Fraud Rate"
          value={fraudRate}
          sub={`${fmt(summary?.fraud_count)} flagged`}
          color={summary?.fraud_rate > 0.05 ? 'var(--red)' : 'var(--green)'}
          icon={TrendingUp}
        />
        <StatCard
          label="Open Alerts"
          value={openAlerts}
          sub={`${criticalAlerts} critical`}
          color={openAlerts > 0 ? 'var(--orange)' : 'var(--green)'}
          icon={AlertTriangle}
        />
        <StatCard
          label="Fraud Exposure"
          value={`$${fmt(summary?.fraud_amount_usd)}`}
          sub={`of $${fmt(summary?.total_amount_usd)} total`}
          color="var(--yellow)"
          icon={Shield}
        />
      </div>

      {/* Charts row */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, marginBottom: 20 }}>
        <TrendChart period={period} granularity={period === '30d' ? 'day' : 'hour'} />
        <CategoryChart period={period === '1h' ? '24h' : period} />
      </div>

      {/* Alert feed */}
      <AlertFeed maxHeight={320} />
    </div>
  )
}
