import { create } from 'zustand';
import { createSession, resumeSession, patchStage, getSession, apiErrorMessage } from '../lib/api';

export const STAGE_ORDER = [
  'identity',
  'context',
  'psychometric',
  'ai-discussion',
  'scenario',
  'processing',
  'results',
];

export const STAGE_PATH = {
  identity: '/start',
  context: '/context',
  psychometric: '/assessment/psychometric',
  'ai-discussion': '/assessment/ai-discussion',
  scenario: '/assessment/scenario',
  processing: '/assessment/processing',
  results: '/assessment/results',
};

const LS_KEY = 'tra_session_v1';

function saveLocal(sessionId, resumeCode) {
  try {
    if (sessionId && resumeCode) {
      localStorage.setItem(LS_KEY, JSON.stringify({ sessionId, resumeCode }));
    }
  } catch (_) { /* noop */ }
}

function readLocal() {
  try {
    const raw = localStorage.getItem(LS_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    if (parsed && parsed.sessionId && parsed.resumeCode) return parsed;
    return null;
  } catch (_) { return null; }
}

function clearLocal() {
  try { localStorage.removeItem(LS_KEY); } catch (_) { /* noop */ }
}

const initialState = {
  sessionId: null,
  resumeCode: null,
  participant: null,
  stage: null,
  loading: false,
  error: null,
  // a one-shot marker used by /start to show the "session created" modal
  lastCreated: null,
};

export const useSession = create((set, get) => ({
  ...initialState,

  // ------------------------------------------------------------------ //
  // Session lifecycle
  // ------------------------------------------------------------------ //
  async startSession(form) {
    set({ loading: true, error: null });
    try {
      const resp = await createSession(form);
      saveLocal(resp.session_id, resp.resume_code);
      const participant = {
        name: form.name,
        email: form.email,
        organisation: form.organisation || null,
        role: form.role || null,
      };
      set({
        sessionId: resp.session_id,
        resumeCode: resp.resume_code,
        stage: resp.stage,
        participant,
        loading: false,
        error: null,
        lastCreated: { sessionId: resp.session_id, resumeCode: resp.resume_code },
      });
      return resp;
    } catch (err) {
      const msg = apiErrorMessage(err, 'Could not create session.');
      set({ loading: false, error: msg });
      throw new Error(msg);
    }
  },

  async hydrateFromResumeCode(resumeCode) {
    set({ loading: true, error: null });
    try {
      const resp = await resumeSession(resumeCode);
      saveLocal(resp.session_id, resumeCode);
      set({
        sessionId: resp.session_id,
        resumeCode: resumeCode.trim().toUpperCase(),
        stage: resp.stage,
        participant: resp.participant,
        loading: false,
        error: null,
      });
      return resp;
    } catch (err) {
      const msg = apiErrorMessage(err, 'Resume code not found.');
      set({ loading: false, error: msg });
      throw new Error(msg);
    }
  },

  // Called on hard reload of /assessment/* when store is empty.
  // Uses localStorage-stashed sessionId+resumeCode.
  async hydrateFromLocalStorage() {
    const local = readLocal();
    if (!local) return null;
    set({ loading: true, error: null });
    try {
      const resp = await getSession(local.sessionId);
      set({
        sessionId: resp.session_id,
        resumeCode: resp.resume_code,
        stage: resp.stage,
        participant: resp.participant,
        loading: false,
        error: null,
      });
      return resp;
    } catch (err) {
      // Session no longer exists or bad id — clear and fail silently.
      clearLocal();
      set({ ...initialState });
      return null;
    }
  },

  async advanceStage(nextStage) {
    const { sessionId } = get();
    if (!sessionId) throw new Error('No active session.');
    set({ loading: true, error: null });
    try {
      const resp = await patchStage(sessionId, nextStage);
      set({ stage: resp.stage, loading: false });
      return resp;
    } catch (err) {
      const msg = apiErrorMessage(err, 'Could not update stage.');
      set({ loading: false, error: msg });
      throw new Error(msg);
    }
  },

  async goBack() {
    const { stage } = get();
    const idx = STAGE_ORDER.indexOf(stage);
    if (idx <= 0) return null;
    const prev = STAGE_ORDER[idx - 1];
    return await get().advanceStage(prev);
  },

  clearLastCreated() {
    set({ lastCreated: null });
  },

  // Used by "Save & exit". Keeps localStorage + session in Mongo intact so the
  // participant can come back later with their resume code. Just clears the
  // in-memory store so the in-page context resets.
  saveAndExit() {
    const { sessionId, resumeCode } = get();
    if (sessionId && resumeCode) {
      saveLocal(sessionId, resumeCode);
    }
    set({ ...initialState });
  },

  fullReset() {
    clearLocal();
    set({ ...initialState });
  },
}));

export function getSavedLocal() {
  return readLocal();
}
