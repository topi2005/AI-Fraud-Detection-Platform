// src/pages/ModelPage.jsx
import { useApi } from '../hooks/useApi.js'
import { getModelHealth, getHealth } from '../lib/api.js'
import { Card, CardHeader, Spinner } from '../components/layout/UI.jsx'
import { RadarChart, Radar, PolarGrid, PolarAngleAxis, ResponsiveContainer } from 'recharts'
import { CheckCircle, XCircle, AlertCircle } from 'lucide-react'

function MetricRow({ label, value, description, color = 'var(--blue)' }) {
  const pct = value != null ? Math.round(value * 100) : null
  return (
    <div style={{ padding: '14px 20px', borderBottom: '1px solid var(--border)', display: 'flex', alignItems: 'center', gap: 16 }}>
      <div style={{ width: 160, flexShrink: 0 }}>
        <div style={{ fontSize: 12, color: 'var(--text-2)' }}>{label}</div>
        <div style={{ fontSize: 10, color: 'var(--text-3)', marginTop: 2 }}>{description}</div>
      </div>
      <div style={{ flex: 1 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <div style={{ flex: 1, height: 6, background: 'var(--bg-3)', borderRadius: 3, overflow: 'hidden' }}>
            <div style={{
              width: pct + '%', height: '100%', borderRadius: 3,
              background: color,
              transition: 'width 0.6s cubic-bezier(0.22,1,0.36,1)',
            }} />
          </div>
          <span style={{ width: 40, textAlign: 'right', fontSize: 13, fontFamily: 'var(--font-display)', fontWeight: 700, color }}>
            {pct != null ? pct + '%' : '—'}
          </span>
        </div>
      </div>
    </div>
  )
}

function ServiceDot({ status }) {
  const ok = status === 'ok' || status === 'loaded'
  const warn = status === 'degraded'
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
      {ok ? <CheckCircle size={14} color="var(--green)" /> :
       warn ? <AlertCircle size={14} color="var(--yellow)" /> :
       <XCircle size={14} color="var(--red)" />}
      <span style={{ fontSize: 12, color: ok ? 'var(--green)' : warn ? 'var(--yellow)' : 'var(--red)' }}>
        {status}
      </span>
    </div>
  )
}

export default function ModelPage() {
  const { data: model, loading } = useApi(getModelHealth, [], { pollInterval: 60_000 })
  const { data: health }         = useApi(getHealth, [], { pollInterval: 30_000 })

  const radarData = model ? [
    { metric: 'ROC-AUC',   value: Math.round((model.roc_auc ?? 0) * 100) },
    { metric: 'Avg Prec',  value: Math.round((model.avg_precision ?? 0) * 100) },
    { metric: 'F1',        value: Math.round((model.f1 ?? 0) * 100) },
    { metric: 'Precision', value: Math.round((model.precision ?? 0) * 100) },
    { metric: 'Recall',    value: Math.round((model.recall ?? 0) * 100) },
  ] : []

  return (
    <div style={{ animation: 'fadeUp 0.3s ease both' }}>
      <div style={{ marginBottom: 20 }}>
        <div style={{ fontFamily: 'var(--font-display)', fontWeight: 800, fontSize: 22, marginBottom: 2 }}>Model</div>
        <div style={{ color: 'var(--text-3)', fontSize: 12 }}>ML model performance metrics and system health</div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 320px', gap: 16 }}>
        {/* Metrics */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          <Card>
            <CardHeader
              title="Model Performance"
              subtitle={`Version: ${model?.model_version ?? '—'} · Threshold: ${model?.threshold != null ? (model.threshold * 100).toFixed(0) + '%' : '—'}`}
              action={
                loading ? <Spinner size={13} /> :
                <span style={{
                  fontSize: 10, padding: '2px 8px', borderRadius: 3,
                  background: model?.model_loaded ? 'rgba(40,224,154,0.1)' : 'rgba(255,59,59,0.1)',
                  color: model?.model_loaded ? 'var(--green)' : 'var(--red)',
                  border: `1px solid ${model?.model_loaded ? 'rgba(40,224,154,0.3)' : 'rgba(255,59,59,0.3)'}`,
                }}>
                  {model?.model_loaded ? 'LOADED' : 'NOT LOADED'}
                </span>
              }
            />
            {loading ? (
              <div style={{ padding: 48, display: 'flex', justifyContent: 'center' }}><Spinner size={20} /></div>
            ) : (
              <>
                <MetricRow label="ROC-AUC"         value={model?.roc_auc}        color="var(--blue)"   description="Area under ROC curve — overall discriminative power" />
                <MetricRow label="Avg Precision"   value={model?.avg_precision}  color="var(--purple)" description="Mean precision across recall thresholds (PR-AUC)" />
                <MetricRow label="F1 Score"        value={model?.f1}             color="var(--green)"  description="Harmonic mean of precision and recall" />
                <MetricRow label="Precision"       value={model?.precision}      color="var(--yellow)" description="Of all flagged transactions, how many are actually fraud" />
                <MetricRow label="Recall"          value={model?.recall}         color="var(--orange)" description="Of all real fraud, how many did we catch" />
              </>
            )}
          </Card>

          {/* Model config */}
          <Card>
            <CardHeader title="Ensemble Configuration" subtitle="Random Forest + XGBoost soft-vote" />
            <div style={{ padding: 20, display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
              {[
                ['RF Estimators', '300'],
                ['XGB Estimators', '400'],
                ['SMOTE Ratio', '15%'],
                ['XGB LR', '0.05'],
                ['Ensemble Weights', '1 : 1.5'],
                ['Feature Count', '23'],
              ].map(([k, v]) => (
                <div key={k}>
                  <div style={{ fontSize: 10, color: 'var(--text-3)', textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: 4 }}>{k}</div>
                  <div style={{ fontFamily: 'var(--font-mono)', fontSize: 14, color: 'var(--text)', fontWeight: 500 }}>{v}</div>
                </div>
              ))}
            </div>
          </Card>
        </div>

        {/* Right column */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          {/* Radar */}
          <Card>
            <CardHeader title="Performance Radar" />
            <div style={{ height: 220, padding: '8px 0' }}>
              {radarData.length > 0 ? (
                <ResponsiveContainer width="100%" height="100%">
                  <RadarChart data={radarData} cx="50%" cy="50%" outerRadius="70%">
                    <PolarGrid stroke="var(--border)" />
                    <PolarAngleAxis dataKey="metric" tick={{ fontSize: 10, fill: 'var(--text-3)', fontFamily: 'var(--font-mono)' }} />
                    <Radar dataKey="value" stroke="var(--blue)" fill="var(--blue)" fillOpacity={0.15} strokeWidth={1.5} dot={{ r: 3, fill: 'var(--blue)' }} />
                  </RadarChart>
                </ResponsiveContainer>
              ) : (
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%', color: 'var(--text-3)', fontSize: 12 }}>
                  Model not loaded
                </div>
              )}
            </div>
          </Card>

          {/* System health */}
          <Card>
            <CardHeader title="System Health" subtitle={health?.status ?? 'checking…'} />
            <div style={{ padding: '12px 20px', display: 'flex', flexDirection: 'column', gap: 12 }}>
              {health?.services && Object.entries(health.services).map(([svc, status]) => (
                <div key={svc} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <span style={{ fontSize: 12, color: 'var(--text-3)', textTransform: 'capitalize' }}>
                    {svc.replace(/_/g, ' ')}
                  </span>
                  <ServiceDot status={status} />
                </div>
              ))}
              {!health?.services && (
                <div style={{ color: 'var(--text-3)', fontSize: 12 }}>Loading…</div>
              )}
            </div>
          </Card>

          {/* Risk tiers */}
          <Card>
            <CardHeader title="Risk Tier Thresholds" />
            <div style={{ padding: '12px 20px', display: 'flex', flexDirection: 'column', gap: 10 }}>
              {[
                { tier: 'critical', range: '≥ 80%', color: 'var(--red)',    action: 'Auto-decline' },
                { tier: 'high',     range: '55–80%',color: 'var(--orange)', action: 'Flag for review' },
                { tier: 'medium',   range: '30–55%',color: 'var(--yellow)', action: 'Monitor' },
                { tier: 'low',      range: '< 30%', color: 'var(--green)',  action: 'Approve' },
              ].map(({ tier, range, color, action }) => (
                <div key={tier} style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                  <div style={{ width: 8, height: 8, borderRadius: '50%', background: color, flexShrink: 0 }} />
                  <span style={{ fontSize: 11, color, textTransform: 'capitalize', width: 56 }}>{tier}</span>
                  <span style={{ fontSize: 11, fontFamily: 'var(--font-mono)', color: 'var(--text-3)', width: 60 }}>{range}</span>
                  <span style={{ fontSize: 11, color: 'var(--text-3)' }}>{action}</span>
                </div>
              ))}
            </div>
          </Card>
        </div>
      </div>
    </div>
  )
}
