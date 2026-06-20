// src/components/layout/UI.jsx — shared primitives

export function Card({ children, style = {}, className = '' }) {
  return (
    <div className={className} style={{
      background: 'var(--bg-1)',
      border: '1px solid var(--border)',
      borderRadius: 'var(--radius-lg)',
      ...style,
    }}>
      {children}
    </div>
  )
}

export function CardHeader({ title, subtitle, action }) {
  return (
    <div style={{
      padding: '14px 18px',
      borderBottom: '1px solid var(--border)',
      display: 'flex', alignItems: 'center', justifyContent: 'space-between',
    }}>
      <div>
        <div style={{ fontFamily: 'var(--font-display)', fontWeight: 600, fontSize: 13, letterSpacing: '0.02em' }}>
          {title}
        </div>
        {subtitle && <div style={{ color: 'var(--text-3)', fontSize: 11, marginTop: 2 }}>{subtitle}</div>}
      </div>
      {action}
    </div>
  )
}

const TIER_COLORS = {
  critical: { bg: 'rgba(255,59,59,0.12)', color: '#ff3b3b', border: 'rgba(255,59,59,0.3)' },
  high:     { bg: 'rgba(255,124,59,0.12)', color: '#ff7c3b', border: 'rgba(255,124,59,0.3)' },
  medium:   { bg: 'rgba(245,197,66,0.12)', color: '#f5c542', border: 'rgba(245,197,66,0.3)' },
  low:      { bg: 'rgba(40,224,154,0.10)', color: '#28e09a', border: 'rgba(40,224,154,0.25)' },
  open:         { bg: 'rgba(77,166,255,0.12)', color: '#4da6ff', border: 'rgba(77,166,255,0.3)' },
  investigating:{ bg: 'rgba(167,139,250,0.12)', color: '#a78bfa', border: 'rgba(167,139,250,0.3)' },
  resolved:     { bg: 'rgba(40,224,154,0.10)', color: '#28e09a', border: 'rgba(40,224,154,0.25)' },
  false_positive:{ bg: 'rgba(92,100,114,0.15)', color: '#9aa3b0', border: 'rgba(92,100,114,0.3)' },
}

export function Badge({ label, variant = 'low' }) {
  const c = TIER_COLORS[variant] || TIER_COLORS.low
  return (
    <span style={{
      display: 'inline-block',
      padding: '2px 8px',
      borderRadius: 3,
      fontSize: 10,
      fontWeight: 500,
      letterSpacing: '0.08em',
      textTransform: 'uppercase',
      background: c.bg, color: c.color,
      border: `1px solid ${c.border}`,
    }}>
      {label}
    </span>
  )
}

export function Spinner({ size = 16 }) {
  return (
    <div style={{
      width: size, height: size,
      border: `2px solid var(--border)`,
      borderTopColor: 'var(--blue)',
      borderRadius: '50%',
      animation: 'spin 0.7s linear infinite',
    }} />
  )
}

export function StatCard({ label, value, sub, trend, color = 'var(--text)', icon: Icon }) {
  return (
    <Card style={{ padding: '18px 20px', position: 'relative', overflow: 'hidden' }}>
      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between' }}>
        <div>
          <div style={{ color: 'var(--text-3)', fontSize: 10, letterSpacing: '0.1em', textTransform: 'uppercase', marginBottom: 8 }}>
            {label}
          </div>
          <div style={{ fontSize: 28, fontFamily: 'var(--font-display)', fontWeight: 700, color, lineHeight: 1 }}>
            {value}
          </div>
          {sub && <div style={{ color: 'var(--text-3)', fontSize: 11, marginTop: 6 }}>{sub}</div>}
        </div>
        {Icon && (
          <div style={{ color, opacity: 0.2, flexShrink: 0 }}>
            <Icon size={32} strokeWidth={1.2} />
          </div>
        )}
      </div>
      {trend !== undefined && (
        <div style={{
          position: 'absolute', bottom: 0, left: 0, right: 0, height: 2,
          background: color, opacity: 0.3,
        }} />
      )}
    </Card>
  )
}

export function EmptyState({ message = 'No data' }) {
  return (
    <div style={{ padding: 48, textAlign: 'center', color: 'var(--text-3)', fontSize: 12 }}>
      {message}
    </div>
  )
}

export function ErrorState({ message }) {
  return (
    <div style={{ padding: 48, textAlign: 'center', color: 'var(--red)', fontSize: 12 }}>
      {message}
    </div>
  )
}

// Inject spin keyframe once
const style = document.createElement('style')
style.textContent = '@keyframes spin { to { transform: rotate(360deg); } }'
document.head.appendChild(style)
