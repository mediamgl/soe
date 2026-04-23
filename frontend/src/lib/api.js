import axios from 'axios';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL || '';
export const API_BASE = `${BACKEND_URL}/api`;

const client = axios.create({
  baseURL: API_BASE,
  headers: { 'Content-Type': 'application/json' },
  timeout: 15000,
});

export async function createSession(form) {
  const { data } = await client.post('/sessions', form);
  return data;
}

export async function resumeSession(resumeCode) {
  const code = (resumeCode || '').trim().toUpperCase();
  const { data } = await client.get(`/sessions/resume/${encodeURIComponent(code)}`);
  return data;
}

export async function getSession(sessionId) {
  const { data } = await client.get(`/sessions/${encodeURIComponent(sessionId)}`);
  return data;
}

export async function patchStage(sessionId, stage) {
  const { data } = await client.patch(`/sessions/${encodeURIComponent(sessionId)}/stage`, { stage });
  return data;
}

// --- Psychometric (Phase 4) ---------------------------------------------- //
export async function psychNext(sessionId) {
  const { data } = await client.get(`/assessment/psychometric/next`, {
    params: { session_id: sessionId },
  });
  return data;
}

export async function psychProgress(sessionId) {
  const { data } = await client.get(`/assessment/psychometric/progress`, {
    params: { session_id: sessionId },
  });
  return data;
}

export async function psychAnswer(sessionId, itemId, value, responseTimeMs) {
  const { data } = await client.post(`/assessment/psychometric/answer`, {
    session_id: sessionId,
    item_id: itemId,
    value,
    response_time_ms: responseTimeMs,
  });
  return data;
}

export function apiErrorMessage(err, fallback = 'Something went wrong.') {
  const resp = err && err.response;
  if (!resp) return err && err.message ? err.message : fallback;
  const data = resp.data;
  if (!data) return fallback;
  if (typeof data.detail === 'string') return data.detail;
  if (data.detail && typeof data.detail === 'object' && data.detail.message) return data.detail.message;
  if (Array.isArray(data.detail) && data.detail.length > 0) {
    const first = data.detail[0];
    if (first && first.msg) return first.msg.replace(/^Value error,\s*/i, '');
    return JSON.stringify(first);
  }
  return fallback;
}

export function apiErrorStatus(err) {
  return err && err.response && err.response.status;
}
