import axios from 'axios';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL || '';
export const API_BASE = `${BACKEND_URL}/api`;

const client = axios.create({
  baseURL: API_BASE,
  headers: { 'Content-Type': 'application/json' },
  timeout: 15000,
});

export async function createSession(form) {
  // form: { name, email, organisation?, role?, consent: true }
  const { data } = await client.post('/sessions', form);
  return data; // { session_id, resume_code, stage }
}

export async function resumeSession(resumeCode) {
  const code = (resumeCode || '').trim().toUpperCase();
  const { data } = await client.get(`/sessions/resume/${encodeURIComponent(code)}`);
  return data; // { session_id, stage, participant }
}

export async function getSession(sessionId) {
  const { data } = await client.get(`/sessions/${encodeURIComponent(sessionId)}`);
  return data;
}

export async function patchStage(sessionId, stage) {
  const { data } = await client.patch(`/sessions/${encodeURIComponent(sessionId)}/stage`, { stage });
  return data; // { stage, updated_at }
}

export function apiErrorMessage(err, fallback = 'Something went wrong.') {
  const resp = err && err.response;
  if (!resp) return err && err.message ? err.message : fallback;
  const data = resp.data;
  if (!data) return fallback;
  if (typeof data.detail === 'string') return data.detail;
  if (Array.isArray(data.detail) && data.detail.length > 0) {
    const first = data.detail[0];
    if (first && first.msg) return first.msg.replace(/^Value error,\s*/i, '');
    return JSON.stringify(first);
  }
  return fallback;
}
