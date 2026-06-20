// src/components/charts/TrendChart.jsx
import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer,
} from 'recharts'
import { format, parseISO } from 'date-fns'
import { useApi } from '../../hooks/useApi.js'
import { getTrend } from '../../lib/api.js'
import { Card, CardHeader, Spinner, EmptyState } from '../layout/UI.jsx'

const CustomTooltip = ({ active, payload, label }) => {
  if (!active || !payload?.length) return null
  return (
    <div style={{
      background: 'var(--bg-2)', border: '1px solid var(--border-hi)',
      borderRadius: 6, padding: '10px 14px', fontSize: 12,
    }}>
      <div style={{ color: 'var(--text-3)', marginBottom: 6 }}>{label}</div>
      <div style={{ color: 'var(--blue)' }}>Transactions: <b>{payload[0]?.value}</b></div>
      <div style={{ color: 'var(--red)' }}>Fraud: <b>{payload[1]?.value}</b></div>
    </div>
  )
}

export default function TrendChart({ period = '24h', granularity = 'hour' }) {
  const { data, loading } = useApi(
    () => getTrend(period, granularity),
    [period, granularity],
    { pollInterval: 30_000 }
  )

  const points = data?.points?.map(p => ({
    time: format(parseISO(p.timestamp), granularity === 'hour' ? 'HH:mm' : 'MMM d'),
    tx:   p.tx_count,
    fraud:p.fraud_count,
    rate: +(p.fraud_rate * 100).toFixed(2),
  })) ?? []

  return (
    <Card>
      <CardHeader
        title="Transaction Volume & Fraud"
        subtitle={`${period} — ${granularity}ly breakdown`}
      />
      <div style={{ padding: '16px 8px 8px', height: 220 }}>
        {loading ? (
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%' }}>
            <Spinner size={20} />
          </div>
        ) : points.length === 0 ? <EmptyState message="No trend data yet" /> : (
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={points} margin={{ top: 4, right: 16, left: -20, bottom: 0 }}>
              <defs>
                <linearGradient id="gTx" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%"  stopColor="#4da6ff" stopOpacity={0.15} />
                  <stop offset="95%" stopColor="#4da6ff" stopOpacity={0} />
                </linearGradient>
                <linearGradient id="gFraud" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%"  stopColor="#ff3b3b" stopOpacity={0.2} />
                  <stop offset="95%" stopColor="#ff3b3b" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" vertical={false} />
              <XAxis dataKey="time" tick={{ fontSize: 10, fill: 'var(--text-3)', fontFamily: 'var(--font-mono)' }} axisLine={false} tickLine={false} />
              <YAxis tick={{ fontSize: 10, fill: 'var(--text-3)', fontFamily: 'var(--font-mono)' }} axisLine={false} tickLine={false} />
              <Tooltip content={<CustomTooltip />} />
              <Area type="monotone" dataKey="tx"    stroke="#4da6ff" strokeWidth={1.5} fill="url(#gTx)"    dot={false} />
              <Area type="monotone" dataKey="fraud" stroke="#ff3b3b" strokeWidth={1.5} fill="url(#gFraud)" dot={false} />
            </AreaChart>
          </ResponsiveContainer>
        )}
      </div>
    </Card>
  )
}
