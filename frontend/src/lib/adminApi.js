import axios from 'axios';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL || '';
export const API_BASE = `${BACKEND_URL}/api`;

// Separate client that sends cookies. Required for admin auth (HTTP-only JWT cookie).
export const adminApi = axios.create({
  baseURL: `${API_BASE}/admin`,
  withCredentials: true,
  headers: { 'Content-Type': 'application/json' },
  timeout: 30000,
});

export async function adminLogin(email, password) {
  const { data } = await adminApi.post('/auth/login', { email, password });
  return data;
}
export async function adminLogout() { await adminApi.post('/auth/logout'); }
export async function adminMe() {
  const { data } = await adminApi.get('/auth/me');
  return data;
}
export async function getSettings() {
  const { data } = await adminApi.get('/settings');
  return data;
}
export async function putSettings(body) {
  const { data } = await adminApi.put('/settings', body);
  return data;
}
export async function testSlot(slot, provider, model, apiKey) {
  const body = { slot };
  if (provider) body.provider = provider;
  if (model) body.model = model;
  if (apiKey) body.api_key = apiKey;
  const { data } = await adminApi.post('/settings/test', body);
  return data;
}
export async function testFallback() {
  const { data } = await adminApi.post('/settings/test-fallback');
  return data;
}

// -------- Phase 8 admin endpoints -------- //
export async function listSessions(params = {}) {
  const { data } = await adminApi.get('/sessions', { params });
  return data;
}
export async function getSession(sessionId) {
  const { data } = await adminApi.get(`/sessions/${sessionId}`);
  return data;
}
export async function patchSession(sessionId, body) {
  const { data } = await adminApi.patch(`/sessions/${sessionId}`, body);
  return data;
}
export async function softDeleteSession(sessionId) {
  const { data } = await adminApi.delete(`/sessions/${sessionId}`);
  return data;
}
export async function restoreSession(sessionId) {
  const { data } = await adminApi.post(`/sessions/${sessionId}/restore`, {});
  return data;
}
export async function getDashboardSummary() {
  const { data } = await adminApi.get('/dashboard/summary');
  return data;
}
export async function runLifecycle() {
  const { data } = await adminApi.post('/lifecycle/run', {});
  return data;
}
export function conversationDownloadUrl(sessionId, fmt /* 'markdown' | 'json' */) {
  const base = `${API_BASE}/admin/sessions/${sessionId}/conversation/download`;
  const q = new URLSearchParams({ format: fmt });
  return `${base}?${q.toString()}`;
}
export function deliverableDownloadUrl(sessionId, fmt /* 'pdf' | 'markdown' */) {
  const base = `${API_BASE}/admin/sessions/${sessionId}/deliverable/download`;
  const q = new URLSearchParams({ format: fmt });
  return `${base}?${q.toString()}`;
}

// Small utility to surface a readable error string
export function apiErrorMessage(err, fallback = 'Request failed.') {
  const d = err && err.response && err.response.data;
  if (typeof d === 'string') return d;
  if (d && typeof d.detail === 'string') return d.detail;
  if (d && d.detail && typeof d.detail.message === 'string') return d.detail.message;
  if (err && err.message) return err.message;
  return fallback;
}
// Back-compat alias used by older components (Phase 3 AdminSettings).
export const adminErrorMessage = apiErrorMessage;
