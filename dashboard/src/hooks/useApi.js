// src/hooks/useApi.js — generic data-fetching hook

import { useState, useEffect, useCallback, useRef } from 'react'

export function useApi(fetcher, deps = [], options = {}) {
  const { pollInterval = null, initialData = null } = options
  const [data, setData]       = useState(initialData)
  const [loading, setLoading] = useState(true)
  const [error, setError]     = useState(null)
  const mountedRef = useRef(true)

  const fetch = useCallback(async () => {
    try {
      const result = await fetcher()
      if (mountedRef.current) { setData(result); setError(null) }
    } catch (e) {
      if (mountedRef.current) setError(e.message)
    } finally {
      if (mountedRef.current) setLoading(false)
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps)

  useEffect(() => {
    mountedRef.current = true
    setLoading(true)
    fetch()
    let timer
    if (pollInterval) timer = setInterval(fetch, pollInterval)
    return () => { mountedRef.current = false; clearInterval(timer) }
  }, [fetch, pollInterval])

  return { data, loading, error, refetch: fetch }
}

// WebSocket hook for real-time alert feed
export function useAlertStream(onAlert) {
  const cbRef = useRef(onAlert)
  cbRef.current = onAlert

  useEffect(() => {
    // Simulate SSE / WebSocket with polling in dev
    // In production swap this for: new EventSource('/api/v1/stream/alerts')
    const interval = setInterval(async () => {
      try {
        const { getAlerts } = await import('../lib/api.js')
        const result = await getAlerts({ status: 'open', size: 5 })
        if (result.alerts?.length) cbRef.current(result.alerts)
      } catch (_) {}
    }, 8000)
    return () => clearInterval(interval)
  }, [])
}
