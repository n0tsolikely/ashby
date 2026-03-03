const API_BASE = (import.meta.env.VITE_STUART_API_BASE || '/api').replace(/\/$/, '');

const JSON_HEADERS = {
  'Content-Type': 'application/json',
};

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

async function request(path, options = {}) {
  const url = buildUrl(path);
  const response = await fetch(url, options);
  const contentType = response.headers.get('content-type') || '';
  const isJson = contentType.includes('application/json');
  const body = isJson ? await response.json() : await response.text();

  if (!response.ok) {
    const err = errorFromResponse(response, body, url);
    err.status = response.status;
    err.body = body;
    throw err;
  }

  return body;
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
    const query = new URLSearchParams();
    if (options.sessionId) query.set('session_id', options.sessionId);
    if (options.mode) query.set('mode', options.mode);
    if (options.title) query.set('title', options.title);
    const suffix = query.toString() ? `?${query.toString()}` : '';
    const formData = new FormData();
    formData.append('file', file);
    return request(`/upload${suffix}`, {
      method: 'POST',
      body: formData,
    });
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
      try {
        const modern = await request('/chat', {
          method: 'POST',
          headers: JSON_HEADERS,
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
      return request('/chat/global', {
        method: 'POST',
        headers: JSON_HEADERS,
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
    const query = new URLSearchParams(options).toString();
    const path = `/sessions/${encodeURIComponent(sessionId)}/export${query ? `?${query}` : ''}`;
    const response = await fetch(buildUrl(path));
    if (!response.ok) {
      const text = await response.text();
      throw new Error(text || `Export failed (${response.status})`);
    }
    return response.blob();
  },
};
