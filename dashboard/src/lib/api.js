// src/lib/api.js — typed API client with JWT auth

const BASE = '/api/v1'

function getToken() {
  return localStorage.getItem('fraud_token')
}

function setToken(token) {
  localStorage.setItem('fraud_token', token)
}

function clearToken() {
  localStorage.removeItem('fraud_token')
}

async function req(path, opts = {}) {
  const token = getToken()
  const res = await fetch(`${BASE}${path}`, {
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...opts.headers,
    },
    ...opts,
  })
  if (res.status === 401) {
    clearToken()
    window.location.href = '/login'
    throw new Error('Unauthorized')
  }
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(err.detail || 'API error')
  }
  return res.json()
}

// ── Auth ──────────────────────────────────────────────────────────────────────
export async function login(username, password) {
  const form = new URLSearchParams({ username, password })
  const res = await fetch(`${BASE}/auth/token`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: form,
  })
  if (!res.ok) throw new Error('Invalid credentials')
  const data = await res.json()
  setToken(data.access_token)
  return data
}

export function logout() {
  clearToken()
  window.location.href = '/login'
}

export function isAuthenticated() {
  return !!getToken()
}

// ── Analytics ─────────────────────────────────────────────────────────────────
export const getSummary      = (period = '24h') => req(`/analytics/summary?period=${period}`)
export const getTrend        = (period = '24h', granularity = 'hour') =>
  req(`/analytics/trend?period=${period}&granularity=${granularity}`)
export const getByCategory   = (period = '7d') => req(`/analytics/by-category?period=${period}`)
export const getByCountry    = (period = '7d') => req(`/analytics/by-country?period=${period}`)
export const getTransactions = (params = {}) => {
  const qs = new URLSearchParams(params).toString()
  return req(`/analytics/transactions${qs ? '?' + qs : ''}`)
}

// ── Alerts ────────────────────────────────────────────────────────────────────
export const getAlerts     = (params = {}) => req(`/alerts?${new URLSearchParams(params)}`)
export const getAlertStats = ()            => req('/alerts/stats')
export const resolveAlert  = (id, body)   => req(`/alerts/${id}`, { method: 'PATCH', body: JSON.stringify(body) })

// ── Scoring ───────────────────────────────────────────────────────────────────
export const scoreTransaction = (tx)     => req('/score', { method: 'POST', body: JSON.stringify(tx) })
export const getModelHealth   = ()       => req('/model/health')

// ── System ────────────────────────────────────────────────────────────────────
export const getHealth = () => fetch('/health').then(r => r.json())
