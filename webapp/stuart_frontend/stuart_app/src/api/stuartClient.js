const API_BASE = (import.meta.env.VITE_STUART_API_BASE || '/api').replace(/\/$/, '');

const JSON_HEADERS = {
  'Content-Type': 'application/json',
};
const SECRET_RE = /(bearer\s+[A-Za-z0-9\-\._~\+/=]+|sk-[A-Za-z0-9]{8,}|AIza[0-9A-Za-z\-_]{16,}|ya29\.[0-9A-Za-z\-_]+)/gi;

function createCorrelationId() {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID();
  }
  return `cid_${Date.now()}_${Math.random().toString(16).slice(2)}`;
}

async function sha256Hex(text) {
  const value = String(text || '');
  if (typeof crypto !== 'undefined' && crypto?.subtle && typeof TextEncoder !== 'undefined') {
    const bytes = new TextEncoder().encode(value);
    const digest = await crypto.subtle.digest('SHA-256', bytes);
    return Array.from(new Uint8Array(digest))
      .map((b) => b.toString(16).padStart(2, '0'))
      .join('');
  }
  return `sha256_unavailable_len_${value.length}`;
}

function buildUrl(path) {
  return `${API_BASE}${path.startsWith('/') ? path : `/${path}`}`;
}

function errorFromResponse(response, body, url) {
  const message =
    body?.detail ||
    body?.message ||
    body?.error ||
    `Request failed (${response.status}) at ${url}`;
  return new Error(message);
}

function redactText(value, maxLen = 400) {
  const src = String(value || '').replace(SECRET_RE, '[REDACTED]');
  return src.length > maxLen ? `${src.slice(0, maxLen)}...` : src;
}

async function request(path, options = {}) {
  const url = buildUrl(path);
  const started = (typeof performance !== 'undefined' && typeof performance.now === 'function')
    ? performance.now()
    : Date.now();
  const correlationId = options?.correlationId || createCorrelationId();
  const mergedHeaders = {
    ...(options?.headers || {}),
    'X-Correlation-Id': correlationId,
  };
  const metaSessionId = options?.sessionId ?? options?.session_id ?? null;
  const metaRunId = options?.runId ?? options?.run_id ?? null;
  let response;
  try {
    response = await fetch(url, {
      ...options,
      headers: mergedHeaders,
    });
  } catch (error) {
    const ended = (typeof performance !== 'undefined' && typeof performance.now === 'function')
      ? performance.now()
      : Date.now();
    if (!String(path || '').startsWith('/ui/event')) {
      await postUiEvent(
        {
          event: 'ui.fetch_failed',
          summary: 'Network request failed',
          session_id: metaSessionId,
          run_id: metaRunId,
          data: {
            route: path,
            duration_ms: Math.max(0, Math.round(ended - started)),
            reason: redactText(error?.message || 'network_error'),
          },
        },
        correlationId,
      );
    }
    throw error;
  }
  const contentType = response.headers.get('content-type') || '';
  const isJson = contentType.includes('application/json');
  const body = isJson ? await response.json() : await response.text();

  if (!response.ok) {
    const ended = (typeof performance !== 'undefined' && typeof performance.now === 'function')
      ? performance.now()
      : Date.now();
    if (!String(path || '').startsWith('/ui/event')) {
      await postUiEvent(
        {
          event: 'ui.fetch_failed',
          summary: 'HTTP request failed',
          session_id: metaSessionId,
          run_id: metaRunId,
          data: {
            route: path,
            status: Number(response.status || 0),
            duration_ms: Math.max(0, Math.round(ended - started)),
            reason: redactText(
              typeof body === 'string'
                ? body
                : body?.detail || body?.message || body?.error || `HTTP ${response.status}`,
            ),
          },
        },
        correlationId,
      );
    }
    const err = errorFromResponse(response, body, url);
    err.status = response.status;
    err.body = body;
    throw err;
  }

  return body;
}

async function postUiEvent(eventPayload = {}, correlationId = null) {
  try {
    const cid = correlationId || createCorrelationId();
    await fetch(buildUrl('/ui/event'), {
      method: 'POST',
      headers: {
        ...JSON_HEADERS,
        'X-Correlation-Id': cid,
      },
      body: JSON.stringify(eventPayload),
    });
  } catch (_) {
    // Best effort only; UI telemetry must never block product behavior.
  }
}

async function requestOrEmpty(path) {
  try {
    return await request(path);
  } catch (error) {
    if (String(error?.message || '').includes('404')) {
      return [];
    }
    throw error;
  }
}

function asArray(payload) {
  if (Array.isArray(payload)) return payload;
  if (Array.isArray(payload?.sessions)) return payload.sessions;
  if (Array.isArray(payload?.runs)) return payload.runs;
  if (Array.isArray(payload?.transcripts)) return payload.transcripts;
  if (Array.isArray(payload?.formalizations)) return payload.formalizations;
  if (Array.isArray(payload?.items)) return payload.items;
  if (Array.isArray(payload?.data)) return payload.data;
  return [];
}

export const stuartClient = {
  telemetry: {
    createCorrelationId,
    async hashText(text) {
      return sha256Hex(text);
    },
    async emitUiEvent({ event, summary = null, session_id = null, run_id = null, data = {} } = {}, correlationId = null) {
      if (!event) return;
      await postUiEvent(
        {
          event,
          summary,
          session_id,
          run_id,
          data,
        },
        correlationId,
      );
    },
  },

  registry: {
    async get() {
      return request('/registry');
    },
  },

  templates: {
    async list({ mode, q, limit = 50, offset = 0 } = {}) {
      const params = new URLSearchParams();
      if (mode) params.set('mode', String(mode));
      if (q) params.set('q', String(q));
      params.set('limit', String(limit));
      params.set('offset', String(offset));
      return request(`/templates?${params.toString()}`);
    },
    async get({ mode, template_id, version } = {}) {
      const params = new URLSearchParams();
      if (mode) params.set('mode', String(mode));
      if (version != null) params.set('version', String(version));
      return request(`/templates/${encodeURIComponent(template_id)}?${params.toString()}`);
    },
    async versions({ mode, template_id } = {}) {
      const params = new URLSearchParams();
      if (mode) params.set('mode', String(mode));
      return request(`/templates/${encodeURIComponent(template_id)}/versions?${params.toString()}`);
    },
    async draft(data) {
      return request('/templates/draft', {
        method: 'POST',
        headers: JSON_HEADERS,
        body: JSON.stringify(data),
      });
    },
    async create(data) {
      return request('/templates', {
        method: 'POST',
        headers: JSON_HEADERS,
        body: JSON.stringify(data),
      });
    },
    async remove({ mode, template_id } = {}) {
      const params = new URLSearchParams();
      if (mode) params.set('mode', String(mode));
      params.set('confirm', 'true');
      return request(`/templates/${encodeURIComponent(template_id)}?${params.toString()}`, {
        method: 'DELETE',
      });
    },
  },

  sessions: {
    async list(filters = {}) {
      const query = new URLSearchParams();
      if (filters?.q) query.set('q', String(filters.q));
      if (filters?.mode) query.set('mode', String(filters.mode));
      if (filters?.attendee) query.set('attendee', String(filters.attendee));
      const suffix = query.toString() ? `?${query.toString()}` : '';
      const payload = await request(`/sessions${suffix}`);
      return asArray(payload);
    },
    async create(data) {
      return request('/sessions', {
        method: 'POST',
        headers: JSON_HEADERS,
        sessionId: data?.session_id || null,
        body: JSON.stringify(data),
      });
    },
    async remove(sessionId) {
      return request(`/sessions/${encodeURIComponent(sessionId)}`, {
        method: 'DELETE',
      });
    },
    async update(sessionId, data) {
      return request(`/sessions/${encodeURIComponent(sessionId)}`, {
        method: 'PATCH',
        headers: JSON_HEADERS,
        body: JSON.stringify(data),
      });
    },
  },

  async upload(file, options = {}) {
    const correlationId = options?.correlationId || createCorrelationId();
    await postUiEvent(
      {
        event: 'ui.upload_started',
        summary: 'Audio upload started',
        session_id: options?.sessionId || null,
        run_id: null,
        data: {
          filename: file?.name || '',
          size_bytes: Number(file?.size || 0),
        },
      },
      correlationId,
    );

    const query = new URLSearchParams();
    if (options.sessionId) query.set('session_id', options.sessionId);
    if (options.mode) query.set('mode', options.mode);
    if (options.title) query.set('title', options.title);
    const suffix = query.toString() ? `?${query.toString()}` : '';
    const formData = new FormData();
    formData.append('file', file);
    const result = await request(`/upload${suffix}`, {
      method: 'POST',
      body: formData,
      correlationId,
    });
    await postUiEvent(
      {
        event: 'ui.upload_finished',
        summary: 'Audio upload finished',
        session_id: result?.session_id || options?.sessionId || null,
        run_id: null,
        data: {
          filename: file?.name || '',
          size_bytes: Number(file?.size || 0),
        },
      },
      correlationId,
    );
    return result;
  },

  runs: {
    async create(data) {
      return request('/run', {
        method: 'POST',
        headers: JSON_HEADERS,
        body: JSON.stringify(data),
      });
    },
    async status(runId) {
      return request(`/runs/${encodeURIComponent(runId)}`);
    },
    async cancel(runId) {
      return request(`/runs/${encodeURIComponent(runId)}/cancel`, {
        method: 'POST',
      });
    },
    async remove(runId) {
      return request(`/runs/${encodeURIComponent(runId)}`, {
        method: 'DELETE',
      });
    },
    async update(runId, data) {
      return request(`/runs/${encodeURIComponent(runId)}`, {
        method: 'PATCH',
        headers: JSON_HEADERS,
        body: JSON.stringify(data),
      });
    },
    async listBySession(sessionId) {
      const payload = await requestOrEmpty(`/sessions/${encodeURIComponent(sessionId)}/runs`);
      return asArray(payload);
    },
    async speakers(runId) {
      const payload = await request(`/runs/${encodeURIComponent(runId)}/speakers`);
      return asArray(payload?.speakers ?? payload);
    },
    async setSpeakerMap(runId, data) {
      return request(`/runs/${encodeURIComponent(runId)}/speaker_map`, {
        method: 'POST',
        headers: JSON_HEADERS,
        body: JSON.stringify(data),
      });
    },
    async reformalize(runId, data) {
      return request(`/runs/${encodeURIComponent(runId)}/reformalize`, {
        method: 'POST',
        headers: JSON_HEADERS,
        body: JSON.stringify(data),
      });
    },
  },

  async transcribe(data) {
    return request('/transcribe', {
      method: 'POST',
      headers: JSON_HEADERS,
      sessionId: data?.session_id || null,
      body: JSON.stringify(data),
    });
  },

  transcripts: {
    async list(sessionId) {
      const payload = await requestOrEmpty(`/sessions/${encodeURIComponent(sessionId)}/transcripts`);
      return asArray(payload);
    },
    async get(versionId) {
      return request(`/transcripts/${encodeURIComponent(versionId)}`);
    },
    async getSpeakerMap(versionId) {
      return request(`/transcripts/${encodeURIComponent(versionId)}/speaker_map`);
    },
    async setSpeakerMap(versionId, data) {
      return request(`/transcripts/${encodeURIComponent(versionId)}/speaker_map`, {
        method: 'PUT',
        headers: JSON_HEADERS,
        body: JSON.stringify(data),
      });
    },
    async setActive(sessionId, transcriptVersionId) {
      return request(`/sessions/${encodeURIComponent(sessionId)}/transcripts/active`, {
        method: 'PATCH',
        headers: JSON_HEADERS,
        body: JSON.stringify({ transcript_version_id: transcriptVersionId }),
      });
    },
    async remove(transcriptVersionId, { cascade = false } = {}) {
      const q = cascade ? '?cascade=true' : '';
      return request(`/transcripts/${encodeURIComponent(transcriptVersionId)}${q}`, {
        method: 'DELETE',
      });
    },
  },

  formalizations: {
    async list(sessionId) {
      const payload = await requestOrEmpty(`/sessions/${encodeURIComponent(sessionId)}/formalizations`);
      return asArray(payload);
    },
  },

  search: {
    async mentioned(query, options = {}) {
      const params = new URLSearchParams();
      params.set('q', String(query || ''));
      if (options?.session_id) params.set('session_id', String(options.session_id));
      if (options?.limit) params.set('limit', String(options.limit));
      const payload = await request(`/search?${params.toString()}`);
      return asArray(payload?.hits ?? payload);
    },
  },

  chat: {
    async session(data) {
      const correlationId = data?.correlationId || createCorrelationId();
      try {
        const modern = await request('/chat', {
          method: 'POST',
          headers: JSON_HEADERS,
          correlationId,
          sessionId: data?.session_id || null,
          body: JSON.stringify({
            text: data?.text || data?.message || '',
            session_id: data?.session_id,
            ui: data?.ui_state || data?.ui || {},
            attachments: data?.attachments || [],
            history_tail: data?.history_tail || [],
          }),
        });
        return modern;
      } catch (error) {
        if (!String(error?.message || '').includes('404')) {
          throw error;
        }
        const legacy = await request('/message', {
          method: 'POST',
          headers: JSON_HEADERS,
          correlationId,
          sessionId: data?.session_id || null,
          body: JSON.stringify({
            text: data?.text || data?.message || '',
            session_id: data?.session_id,
            ui: data?.ui_state || data?.ui || {},
            attachments: data?.attachments || [],
            history_tail: data?.history_tail || [],
          }),
        });
        return legacy?.result || legacy;
      }
    },
    async global(data) {
      const correlationId = data?.correlationId || createCorrelationId();
      return request('/chat/global', {
        method: 'POST',
        headers: JSON_HEADERS,
        correlationId,
        sessionId: data?.session_id || null,
        body: JSON.stringify({
          text: data?.text || data?.message || '',
          ui: data?.ui_state || data?.ui || {},
          attachments: data?.attachments || [],
          history_tail: data?.history_tail || [],
          ...(data?.session_id ? { session_id: data.session_id } : {}),
        }),
      });
    },
  },

  async exportSession(sessionId, options = {}) {
    const correlationId = options?.correlationId || createCorrelationId();
    const { correlationId: _ignoreCorrelation, ...queryOptions } = options || {};
    const query = new URLSearchParams(queryOptions).toString();
    const path = `/sessions/${encodeURIComponent(sessionId)}/export${query ? `?${query}` : ''}`;
    const response = await fetch(buildUrl(path), {
      headers: {
        'X-Correlation-Id': correlationId,
      },
    });
    if (!response.ok) {
      const text = await response.text();
      throw new Error(text || `Export failed (${response.status})`);
    }
    return response.blob();
  },
};
