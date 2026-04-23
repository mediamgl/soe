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

export async function adminLogout() {
  await adminApi.post('/auth/logout');
}

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

export function adminErrorMessage(err, fallback = 'Something went wrong.') {
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
