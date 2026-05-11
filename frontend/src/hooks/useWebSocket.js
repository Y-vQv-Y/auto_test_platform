import { useEffect, useRef, useState, useCallback } from 'react'

/**
 * WebSocket hook with exponential backoff reconnection.
 *
 * @param {() => WebSocket} connectFn — factory that returns a new WebSocket
 * @param {object} options
 * @param {number} options.maxRetries — max reconnection attempts (default Infinity)
 * @param {number} options.baseDelay — initial delay in ms (default 1000)
 * @param {number} options.maxDelay — max delay in ms (default 30000)
 * @param {function} options.onMessage — handler for incoming messages
 * @returns {{ status: 'connected'|'disconnected'|'reconnecting'|'error', send: function }}
 */
export default function useWebSocket(connectFn, options = {}) {
  const {
    maxRetries = Infinity,
    baseDelay = 1000,
    maxDelay = 30000,
    onMessage,
  } = options

  const [status, setStatus] = useState('disconnected')
  const wsRef = useRef(null)
  const retryCountRef = useRef(0)
  const retryTimerRef = useRef(null)
  const mountedRef = useRef(true)
  const connectFnRef = useRef(connectFn)

  // Keep connectFn ref current
  connectFnRef.current = connectFn

  const send = useCallback((data) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(typeof data === 'string' ? data : JSON.stringify(data))
    }
  }, [])

  useEffect(() => {
    mountedRef.current = true

    function connect() {
      if (!mountedRef.current) return
      if (!connectFnRef.current) return  // No connect function provided — skip

      // Clean up previous connection
      if (wsRef.current) {
        try { wsRef.current.close() } catch (e) { /* ignore */ }
        wsRef.current = null
      }

      try {
        const ws = connectFnRef.current()
        wsRef.current = ws

        ws.onopen = () => {
          if (!mountedRef.current) return
          retryCountRef.current = 0
          setStatus('connected')
        }

        ws.onmessage = (event) => {
          if (!mountedRef.current) return
          if (onMessage) {
            try {
              const data = JSON.parse(event.data)
              onMessage(data)
            } catch (e) {
              onMessage(event.data)
            }
          }
        }

        ws.onclose = () => {
          if (!mountedRef.current) return
          wsRef.current = null
          scheduleRetry()
        }

        ws.onerror = () => {
          if (!mountedRef.current) return
          // onclose will fire after onerror, retry handled there
          setStatus('reconnecting')
        }
      } catch (e) {
        if (!mountedRef.current) return
        setStatus('error')
        scheduleRetry()
      }
    }

    function scheduleRetry() {
      if (retryCountRef.current >= maxRetries) {
        setStatus('error')
        return
      }

      setStatus('reconnecting')

      // Exponential backoff: 1s, 2s, 4s, 8s, ... capped at maxDelay
      const delay = Math.min(baseDelay * Math.pow(2, retryCountRef.current), maxDelay)
      retryCountRef.current += 1

      retryTimerRef.current = setTimeout(() => {
        if (mountedRef.current && wsRef.current === null) {
          connect()
        }
      }, delay)
    }

    connect()

    return () => {
      mountedRef.current = false
      if (retryTimerRef.current) {
        clearTimeout(retryTimerRef.current)
      }
      if (wsRef.current) {
        try { wsRef.current.close() } catch (e) { /* ignore */ }
        wsRef.current = null
      }
    }
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  return { status, send }
}
