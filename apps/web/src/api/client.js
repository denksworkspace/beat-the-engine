function resolveApiBase() {
  const configured = import.meta.env.VITE_API_BASE;
  if (!configured) {
    return `${window.location.protocol}//${window.location.hostname}:8000`;
  }

  try {
    const url = new URL(configured);
    const isLoopback = url.hostname === 'localhost' || url.hostname === '127.0.0.1';
    const currentIsLoopback = window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1';

    if (isLoopback && !currentIsLoopback) {
      url.hostname = window.location.hostname;
      return url.toString().replace(/\/$/, '');
    }
  } catch {
    // Keep configured value when parsing fails.
  }

  return configured;
}

const API_BASE = resolveApiBase();
const USER_ID = import.meta.env.VITE_USER_ID || 'demo-user';

async function readPayload(response) {
  const contentType = response.headers.get('content-type') || '';
  if (contentType.includes('application/json')) {
    return response.json();
  }

  const text = await response.text();
  if (!text) return null;
  try {
    return JSON.parse(text);
  } catch {
    return { message: text };
  }
}

async function request(path, options = {}) {
  let response;
  try {
    response = await fetch(`${API_BASE}${path}`, {
      ...options,
      headers: {
        'Content-Type': 'application/json',
        'X-User-Id': USER_ID,
        ...(options.headers || {}),
      },
    });
  } catch (error) {
    if (error instanceof TypeError) {
      throw new Error(
        `Cannot reach API at ${API_BASE}. Ensure backend is running and CORS_ALLOW_ORIGINS includes http://localhost:5173.`,
      );
    }
    throw error;
  }

  const payload = await readPayload(response);
  if (!response.ok) {
    const code = payload?.code || `HTTP_${response.status}`;
    const message = payload?.message || response.statusText || 'Request failed';
    throw new Error(`${code}: ${message}`);
  }

  return payload;
}

export function createSession(mode = 'standard', engineLevel = 5) {
  return request('/v1/sessions', {
    method: 'POST',
    body: JSON.stringify({ mode, engine_level: engineLevel }),
  });
}

export function saveCandidates(sessionId, turnId, version, candidates) {
  return request(`/v1/sessions/${sessionId}/turns/${turnId}/candidates`, {
    method: 'PUT',
    body: JSON.stringify({ version, candidates }),
  });
}

export function getSession(sessionId) {
  return request(`/v1/sessions/${sessionId}`, {
    method: 'GET',
  });
}

export function commitMove(sessionId, turnId, payload) {
  return request(`/v1/sessions/${sessionId}/turns/${turnId}/commit`, {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function evaluatePosition(sessionId, fen, thinkSeconds) {
  const payload = { fen };
  if (typeof thinkSeconds === 'number') {
    payload.think_seconds = thinkSeconds;
  }
  return request(`/v1/sessions/${sessionId}/evaluate`, {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function undoLastCommit(sessionId) {
  return request(`/v1/sessions/${sessionId}/undo`, {
    method: 'POST',
    body: JSON.stringify({}),
  });
}
