// src/pages/LoginPage.jsx
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { login } from '../lib/api.js'
import { Shield } from 'lucide-react'

export default function LoginPage() {
  const [username, setUsername] = useState('admin')
  const [password, setPassword] = useState('admin123')
  const [error, setError]       = useState(null)
  const [loading, setLoading]   = useState(false)
  const navigate                = useNavigate()

  const submit = async (e) => {
    e.preventDefault()
    setLoading(true); setError(null)
    try {
      await login(username, password)
      navigate('/')
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  const inputStyle = {
    width: '100%', background: 'var(--bg-2)', border: '1px solid var(--border)',
    borderRadius: 6, padding: '10px 14px', color: 'var(--text)',
    fontSize: 13, fontFamily: 'var(--font-mono)', outline: 'none',
    transition: 'border-color 0.15s',
  }

  return (
    <div style={{
      minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center',
      background: 'var(--bg)',
    }}>
      {/* Scan line effect */}
      <div style={{
        position: 'fixed', inset: 0, pointerEvents: 'none', overflow: 'hidden', zIndex: 0,
      }}>
        <div style={{
          position: 'absolute', left: 0, right: 0, height: '2px',
          background: 'linear-gradient(to right, transparent, rgba(255,59,59,0.15), transparent)',
          animation: 'scan 6s linear infinite',
        }} />
      </div>

      <div style={{
        width: 360, animation: 'fadeUp 0.4s ease both',
        position: 'relative', zIndex: 1,
      }}>
        {/* Logo */}
        <div style={{ textAlign: 'center', marginBottom: 32 }}>
          <div style={{
            width: 48, height: 48, borderRadius: 12,
            background: 'var(--red)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            margin: '0 auto 16px',
            boxShadow: '0 0 32px var(--red-glow)',
          }}>
            <Shield size={24} color="#fff" strokeWidth={2.5} />
          </div>
          <div style={{ fontFamily: 'var(--font-display)', fontWeight: 800, fontSize: 20, letterSpacing: '-0.01em' }}>
            FraudShield
          </div>
          <div style={{ color: 'var(--text-3)', fontSize: 12, marginTop: 4 }}>
            Detection Platform
          </div>
        </div>

        {/* Card */}
        <div style={{
          background: 'var(--bg-1)', border: '1px solid var(--border)',
          borderRadius: 12, padding: 28,
        }}>
          <form onSubmit={submit} style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
            <div>
              <label style={{ fontSize: 10, color: 'var(--text-3)', textTransform: 'uppercase', letterSpacing: '0.1em', display: 'block', marginBottom: 6 }}>
                Username
              </label>
              <input
                type="text" value={username} onChange={e => setUsername(e.target.value)}
                style={inputStyle} autoComplete="username"
                onFocus={e => e.target.style.borderColor = 'var(--border-hi)'}
                onBlur={e => e.target.style.borderColor = 'var(--border)'}
              />
            </div>
            <div>
              <label style={{ fontSize: 10, color: 'var(--text-3)', textTransform: 'uppercase', letterSpacing: '0.1em', display: 'block', marginBottom: 6 }}>
                Password
              </label>
              <input
                type="password" value={password} onChange={e => setPassword(e.target.value)}
                style={inputStyle} autoComplete="current-password"
                onFocus={e => e.target.style.borderColor = 'var(--border-hi)'}
                onBlur={e => e.target.style.borderColor = 'var(--border)'}
              />
            </div>

            {error && (
              <div style={{ padding: '8px 12px', background: 'var(--red-glow)', border: '1px solid rgba(255,59,59,0.3)', borderRadius: 6, fontSize: 12, color: 'var(--red)' }}>
                {error}
              </div>
            )}

            <button
              type="submit" disabled={loading}
              style={{
                padding: '11px 0', marginTop: 4,
                background: loading ? 'var(--bg-3)' : 'var(--red)',
                border: 'none', borderRadius: 6, color: '#fff',
                fontFamily: 'var(--font-display)', fontWeight: 700, fontSize: 13,
                letterSpacing: '0.05em', cursor: loading ? 'not-allowed' : 'pointer',
                transition: 'background 0.15s',
              }}
            >
              {loading ? 'Authenticating…' : 'SIGN IN'}
            </button>
          </form>

          <div style={{ marginTop: 20, paddingTop: 16, borderTop: '1px solid var(--border)', fontSize: 11, color: 'var(--text-3)', textAlign: 'center' }}>
            demo: <span style={{ color: 'var(--text-2)', fontFamily: 'var(--font-mono)' }}>admin / admin123</span>
            {' · '}
            <span style={{ color: 'var(--text-2)', fontFamily: 'var(--font-mono)' }}>analyst / analyst123</span>
          </div>
        </div>
      </div>
    </div>
  )
}
