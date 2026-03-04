import React from 'react'
import ReactDOM from 'react-dom/client'
import App from '@/App.jsx'
import '@/index.css'

const API_BASE = (import.meta.env.VITE_STUART_API_BASE || '/api').replace(/\/$/, '')
const SECRET_RE = /(bearer\s+[A-Za-z0-9\-\._~\+/=]+|sk-[A-Za-z0-9]{8,}|AIza[0-9A-Za-z\-_]{16,}|ya29\.[0-9A-Za-z\-_]+)/gi

function redactText(value, maxLen = 1200) {
  const src = String(value || '').replace(SECRET_RE, '[REDACTED]')
  return src.length > maxLen ? `${src.slice(0, maxLen)}...` : src
}

function correlationId() {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID()
  }
  return `cid_${Date.now()}_${Math.random().toString(16).slice(2)}`
}

async function emitUiError(payload) {
  try {
    await fetch(`${API_BASE}/ui/event`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-Correlation-Id': correlationId(),
      },
      body: JSON.stringify(payload),
    })
  } catch (_) {
    // best effort
  }
}

window.onerror = (message, source, lineno, colno, error) => {
  emitUiError({
    event: 'ui.error',
    summary: 'Unhandled window error',
    session_id: null,
    run_id: null,
    data: {
      message: redactText(message),
      source: redactText(source),
      line: Number(lineno || 0),
      column: Number(colno || 0),
      stack: redactText(error?.stack || ''),
    },
  })
}

window.onunhandledrejection = (event) => {
  const reason = event?.reason
  emitUiError({
    event: 'ui.error',
    summary: 'Unhandled promise rejection',
    session_id: null,
    run_id: null,
    data: {
      message: redactText(reason?.message || String(reason || 'unhandled_rejection')),
      stack: redactText(reason?.stack || ''),
    },
  })
}

ReactDOM.createRoot(document.getElementById('root')).render(
  <App />
)
