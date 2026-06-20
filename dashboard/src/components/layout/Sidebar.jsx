// src/components/layout/Sidebar.jsx
import { NavLink } from 'react-router-dom'
import { BarChart3, Bell, Activity, Search, Settings, LogOut, Shield } from 'lucide-react'
import { logout } from '../../lib/api.js'

const NAV = [
  { to: '/',          icon: BarChart3,  label: 'Overview'     },
  { to: '/alerts',    icon: Bell,       label: 'Alerts'       },
  { to: '/activity',  icon: Activity,   label: 'Transactions' },
  { to: '/score',     icon: Search,     label: 'Score'        },
  { to: '/model',     icon: Settings,   label: 'Model'        },
]

export default function Sidebar() {
  return (
    <aside style={{
      width: 56, flexShrink: 0,
      background: 'var(--bg-1)',
      borderRight: '1px solid var(--border)',
      display: 'flex', flexDirection: 'column',
      alignItems: 'center',
      paddingTop: 16, paddingBottom: 16,
      gap: 4,
      position: 'fixed', top: 0, left: 0, bottom: 0,
      zIndex: 100,
    }}>
      {/* Logo */}
      <div style={{
        width: 32, height: 32, marginBottom: 20,
        background: 'var(--red)', borderRadius: 6,
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        boxShadow: '0 0 16px var(--red-glow)',
        flexShrink: 0,
      }}>
        <Shield size={16} color="#fff" strokeWidth={2.5} />
      </div>

      {NAV.map(({ to, icon: Icon, label }) => (
        <NavLink
          key={to} to={to} end={to === '/'}
          title={label}
          style={({ isActive }) => ({
            width: 36, height: 36,
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            borderRadius: 6,
            color: isActive ? 'var(--text)' : 'var(--text-3)',
            background: isActive ? 'var(--bg-3)' : 'transparent',
            border: isActive ? '1px solid var(--border-hi)' : '1px solid transparent',
            transition: 'all 0.15s',
          })}
        >
          <Icon size={16} strokeWidth={1.8} />
        </NavLink>
      ))}

      <div style={{ flex: 1 }} />

      <button
        onClick={logout}
        title="Logout"
        style={{
          width: 36, height: 36,
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          borderRadius: 6, border: '1px solid transparent',
          background: 'transparent', color: 'var(--text-3)',
          transition: 'all 0.15s',
        }}
        onMouseEnter={e => { e.currentTarget.style.color = 'var(--red)'; e.currentTarget.style.background = 'var(--red-glow)' }}
        onMouseLeave={e => { e.currentTarget.style.color = 'var(--text-3)'; e.currentTarget.style.background = 'transparent' }}
      >
        <LogOut size={15} strokeWidth={1.8} />
      </button>
    </aside>
  )
}
