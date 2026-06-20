// src/components/charts/CategoryChart.jsx
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell } from 'recharts'
import { useApi } from '../../hooks/useApi.js'
import { getByCategory } from '../../lib/api.js'
import { Card, CardHeader, Spinner, EmptyState } from '../layout/UI.jsx'

const COLORS = ['#ff3b3b','#ff7c3b','#f5c542','#4da6ff','#28e09a','#a78bfa',
                 '#ff6b6b','#ffa07a','#87ceeb','#98fb98']

const CustomTooltip = ({ active, payload }) => {
  if (!active || !payload?.length) return null
  const d = payload[0].payload
  return (
    <div style={{
      background: 'var(--bg-2)', border: '1px solid var(--border-hi)',
      borderRadius: 6, padding: '10px 14px', fontSize: 12,
    }}>
      <div style={{ fontWeight: 600, marginBottom: 4 }}>{d.category}</div>
      <div style={{ color: 'var(--text-3)' }}>Transactions: {d.tx_count}</div>
      <div style={{ color: 'var(--red)' }}>Fraud: {d.fraud_count}</div>
      <div style={{ color: 'var(--yellow)' }}>Rate: {(d.fraud_rate * 100).toFixed(1)}%</div>
    </div>
  )
}

export default function CategoryChart({ period = '7d' }) {
  const { data, loading } = useApi(() => getByCategory(period), [period], { pollInterval: 60_000 })

  const items = (data ?? []).slice(0, 10).map(d => ({
    ...d,
    category: d.category.replace(/_/g, ' '),
    pct: +(d.fraud_rate * 100).toFixed(1),
  }))

  return (
    <Card>
      <CardHeader title="Fraud by Merchant Category" subtitle={`${period} window`} />
      <div style={{ padding: '16px 8px 8px', height: 220 }}>
        {loading ? (
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%' }}>
            <Spinner size={20} />
          </div>
        ) : items.length === 0 ? <EmptyState message="No category data yet" /> : (
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={items} layout="vertical" margin={{ top: 0, right: 16, left: 0, bottom: 0 }}>
              <XAxis type="number" tick={{ fontSize: 10, fill: 'var(--text-3)' }} axisLine={false} tickLine={false} tickFormatter={v => v + '%'} />
              <YAxis type="category" dataKey="category" width={100}
                tick={{ fontSize: 10, fill: 'var(--text-3)', fontFamily: 'var(--font-mono)' }}
                axisLine={false} tickLine={false} />
              <Tooltip content={<CustomTooltip />} />
              <Bar dataKey="pct" radius={[0, 2, 2, 0]}>
                {items.map((_, i) => <Cell key={i} fill={COLORS[i % COLORS.length]} fillOpacity={0.8} />)}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        )}
      </div>
    </Card>
  )
}
