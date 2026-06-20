// src/pages/ScorePage.jsx — live transaction scoring sandbox
import { useState } from 'react'
import { scoreTransaction } from '../lib/api.js'
import { Card, CardHeader, Badge } from '../components/layout/UI.jsx'
import { Zap, AlertTriangle } from 'lucide-react'

const PRESETS = {
  Normal: {
    tx_id: 'demo-' + Math.random().toString(36).slice(2,8),
    account_id: 'acc-demo-001',
    amount: 42.50,
    currency: 'USD',
    transaction_type: 'purchase',
    channel: 'card',
    country_code: 'US',
    ip_address: '74.125.20.1',
    latitude: 37.77,
    longitude: -122.42,
    merchant_category: 'food_beverage',
  },
  'Amount Spike': {
    tx_id: 'demo-' + Math.random().toString(36).slice(2,8),
    account_id: 'acc-demo-002',
    amount: 14800.00,
    currency: 'USD',
    transaction_type: 'transfer',
    channel: 'wire',
    country_code: 'CY',
    merchant_category: 'money_transfer',
  },
  'Geo Anomaly': {
    tx_id: 'demo-' + Math.random().toString(36).slice(2,8),
    account_id: 'acc-demo-003',
    amount: 350.00,
    currency: 'USD',
    transaction_type: 'online_purchase',
    channel: 'online',
    country_code: 'RO',
    ip_address: '5.2.3.4',
    latitude: 44.43,
    longitude: 26.10,
    merchant_category: 'online_retail',
  },
  'Crypto High Risk': {
    tx_id: 'demo-' + Math.random().toString(36).slice(2,8),
    account_id: 'acc-demo-004',
    amount: 2500.00,
    currency: 'USD',
    transaction_type: 'transfer',
    channel: 'online',
    country_code: 'MT',
    merchant_category: 'cryptocurrency',
  },
}

function ScoreMeter({ score }) {
  const pct = score * 100
  const color = score >= 0.8 ? 'var(--red)' : score >= 0.55 ? 'var(--orange)' : score >= 0.3 ? 'var(--yellow)' : 'var(--green)'
  return (
    <div style={{ textAlign: 'center', padding: '32px 24px' }}>
      {/* Big score circle */}
      <div style={{
        width: 120, height: 120, borderRadius: '50%', margin: '0 auto 20px',
        background: `conic-gradient(${color} ${pct}%, var(--bg-3) 0)`,
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        position: 'relative',
        boxShadow: `0 0 32px ${color}33`,
      }}>
        <div style={{
          width: 88, height: 88, borderRadius: '50%',
          background: 'var(--bg-1)',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          flexDirection: 'column',
        }}>
          <span style={{ fontFamily: 'var(--font-display)', fontWeight: 800, fontSize: 24, color, lineHeight: 1 }}>
            {pct.toFixed(0)}
          </span>
          <span style={{ fontSize: 10, color: 'var(--text-3)' }}>%</span>
        </div>
      </div>
    </div>
  )
}

export default function ScorePage() {
  const [form, setForm] = useState(PRESETS['Normal'])
  const [result, setResult] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  const set = (k, v) => setForm(f => ({ ...f, [k]: v }))

  const submit = async () => {
    setLoading(true); setError(null); setResult(null)
    try {
      const res = await scoreTransaction({ ...form, tx_id: 'demo-' + Date.now() })
      setResult(res)
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }

  const loadPreset = (name) => setForm({ ...PRESETS[name], tx_id: 'demo-' + Date.now() })

  const inputStyle = {
    width: '100%', background: 'var(--bg-2)', border: '1px solid var(--border)',
    borderRadius: 4, padding: '6px 10px', color: 'var(--text)',
    fontSize: 12, fontFamily: 'var(--font-mono)', outline: 'none',
  }
  const labelStyle = { fontSize: 10, color: 'var(--text-3)', textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: 4, display: 'block' }

  return (
    <div style={{ animation: 'fadeUp 0.3s ease both' }}>
      <div style={{ marginBottom: 20 }}>
        <div style={{ fontFamily: 'var(--font-display)', fontWeight: 800, fontSize: 22, marginBottom: 2 }}>Score</div>
        <div style={{ color: 'var(--text-3)', fontSize: 12 }}>Submit a transaction to get a real-time fraud score</div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 360px', gap: 16 }}>
        {/* Form */}
        <Card>
          <CardHeader title="Transaction Payload" subtitle="Edit fields or choose a preset" action={
            <div style={{ display: 'flex', gap: 6 }}>
              {Object.keys(PRESETS).map(name => (
                <button key={name} onClick={() => loadPreset(name)} style={{
                  padding: '3px 10px', fontSize: 10, borderRadius: 4,
                  background: 'var(--bg-3)', border: '1px solid var(--border)',
                  color: 'var(--text-2)', cursor: 'pointer',
                  fontFamily: 'var(--font-mono)',
                }}>{name}</button>
              ))}
            </div>
          } />

          <div style={{ padding: 20, display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14 }}>
            {[
              { key: 'account_id',       label: 'Account ID',        type: 'text' },
              { key: 'amount',           label: 'Amount (USD)',       type: 'number' },
              { key: 'transaction_type', label: 'Transaction Type',   type: 'select', opts: ['purchase','online_purchase','atm_withdrawal','transfer','international','refund'] },
              { key: 'channel',          label: 'Channel',            type: 'select', opts: ['card','online','mobile','atm','wire'] },
              { key: 'country_code',     label: 'Country Code',       type: 'text' },
              { key: 'currency',         label: 'Currency',           type: 'text' },
              { key: 'merchant_category',label: 'Merchant Category',  type: 'select', opts: ['retail','online_retail','food_beverage','fuel','digital_services','atm','gambling','cryptocurrency','money_transfer','travel'] },
              { key: 'ip_address',       label: 'IP Address',         type: 'text' },
              { key: 'latitude',         label: 'Latitude',           type: 'number' },
              { key: 'longitude',        label: 'Longitude',          type: 'number' },
            ].map(({ key, label, type, opts }) => (
              <div key={key}>
                <label style={labelStyle}>{label}</label>
                {type === 'select' ? (
                  <select value={form[key] ?? ''} onChange={e => set(key, e.target.value)} style={inputStyle}>
                    {opts.map(o => <option key={o} value={o}>{o}</option>)}
                  </select>
                ) : (
                  <input
                    type={type}
                    value={form[key] ?? ''}
                    onChange={e => set(key, type === 'number' ? +e.target.value : e.target.value)}
                    style={inputStyle}
                  />
                )}
              </div>
            ))}
          </div>

          <div style={{ padding: '0 20px 20px' }}>
            <button
              onClick={submit} disabled={loading}
              style={{
                width: '100%', padding: '10px 0',
                background: loading ? 'var(--bg-3)' : 'var(--red)',
                border: 'none', borderRadius: 6, color: '#fff',
                fontSize: 12, fontFamily: 'var(--font-display)', fontWeight: 700,
                letterSpacing: '0.05em', cursor: loading ? 'not-allowed' : 'pointer',
                display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8,
                transition: 'background 0.15s',
              }}
            >
              <Zap size={14} />
              {loading ? 'Scoring…' : 'SCORE TRANSACTION'}
            </button>
          </div>
        </Card>

        {/* Result */}
        <Card>
          <CardHeader title="Scoring Result" />
          {error && (
            <div style={{ padding: 24, textAlign: 'center' }}>
              <AlertTriangle size={24} color="var(--orange)" style={{ marginBottom: 8 }} />
              <div style={{ color: 'var(--orange)', fontSize: 12 }}>{error}</div>
              <div style={{ color: 'var(--text-3)', fontSize: 11, marginTop: 8 }}>
                Make sure the API is running and you're logged in.
              </div>
            </div>
          )}
          {!result && !error && (
            <div style={{ padding: 48, textAlign: 'center', color: 'var(--text-3)', fontSize: 12 }}>
              Submit a transaction to see the fraud score
            </div>
          )}
          {result && (
            <>
              <ScoreMeter score={result.fraud_score} />
              <div style={{ padding: '0 20px 20px', display: 'flex', flexDirection: 'column', gap: 10 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <span style={{ color: 'var(--text-3)', fontSize: 11 }}>Risk Tier</span>
                  <Badge label={result.risk_tier} variant={result.risk_tier} />
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                  <span style={{ color: 'var(--text-3)', fontSize: 11 }}>Prediction</span>
                  <span style={{ fontSize: 12, color: result.is_fraud_pred ? 'var(--red)' : 'var(--green)' }}>
                    {result.is_fraud_pred ? '⚠ FRAUD' : '✓ LEGITIMATE'}
                  </span>
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                  <span style={{ color: 'var(--text-3)', fontSize: 11 }}>Threshold</span>
                  <span style={{ fontSize: 11, fontFamily: 'var(--font-mono)', color: 'var(--text-2)' }}>{(result.threshold * 100).toFixed(0)}%</span>
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                  <span style={{ color: 'var(--text-3)', fontSize: 11 }}>Model Version</span>
                  <span style={{ fontSize: 11, fontFamily: 'var(--font-mono)', color: 'var(--text-2)' }}>{result.model_version}</span>
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                  <span style={{ color: 'var(--text-3)', fontSize: 11 }}>Latency</span>
                  <span style={{ fontSize: 11, fontFamily: 'var(--font-mono)', color: 'var(--text-2)' }}>{result.latency_ms}ms</span>
                </div>
                {result.alert_created && (
                  <div style={{ marginTop: 4, padding: '8px 12px', background: 'var(--red-glow)', border: '1px solid rgba(255,59,59,0.3)', borderRadius: 4, fontSize: 11, color: 'var(--red)' }}>
                    🚨 Alert created — check the Alerts page
                  </div>
                )}
              </div>
            </>
          )}
        </Card>
      </div>
    </div>
  )
}
