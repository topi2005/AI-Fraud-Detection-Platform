// src/App.jsx
import { Routes, Route, Navigate, useLocation } from 'react-router-dom'
import { isAuthenticated } from './lib/api.js'
import Sidebar from './components/layout/Sidebar.jsx'
import Overview    from './pages/Overview.jsx'
import AlertsPage  from './pages/AlertsPage.jsx'
import ActivityPage from './pages/ActivityPage.jsx'
import ScorePage   from './pages/ScorePage.jsx'
import ModelPage   from './pages/ModelPage.jsx'
import LoginPage   from './pages/LoginPage.jsx'

function RequireAuth({ children }) {
  const location = useLocation()
  return isAuthenticated()
    ? children
    : <Navigate to="/login" state={{ from: location }} replace />
}

function Layout({ children }) {
  return (
    <div style={{ display: 'flex', minHeight: '100vh' }}>
      <Sidebar />
      <main style={{
        flex: 1, marginLeft: 56,
        padding: '28px 32px',
        maxWidth: 1320,
        overflowY: 'auto',
      }}>
        {children}
      </main>
    </div>
  )
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/" element={
        <RequireAuth>
          <Layout><Overview /></Layout>
        </RequireAuth>
      } />
      <Route path="/alerts" element={
        <RequireAuth>
          <Layout><AlertsPage /></Layout>
        </RequireAuth>
      } />
      <Route path="/activity" element={
        <RequireAuth>
          <Layout><ActivityPage /></Layout>
        </RequireAuth>
      } />
      <Route path="/score" element={
        <RequireAuth>
          <Layout><ScorePage /></Layout>
        </RequireAuth>
      } />
      <Route path="/model" element={
        <RequireAuth>
          <Layout><ModelPage /></Layout>
        </RequireAuth>
      } />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}
