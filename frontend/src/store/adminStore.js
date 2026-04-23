import { create } from 'zustand';
import { adminLogin, adminLogout, adminMe, adminErrorMessage } from '../lib/adminApi';

const initialState = {
  email: null,
  role: null,
  checked: false,
  loading: false,
  error: null,
};

export const useAdmin = create((set, get) => ({
  ...initialState,

  async refresh() {
    set({ loading: true });
    try {
      const me = await adminMe();
      set({ email: me.email, role: me.role, checked: true, loading: false, error: null });
      return me;
    } catch (err) {
      set({ email: null, role: null, checked: true, loading: false });
      return null;
    }
  },

  async login(email, password) {
    set({ loading: true, error: null });
    try {
      const me = await adminLogin(email, password);
      set({ email: me.email, role: me.role, checked: true, loading: false, error: null });
      return me;
    } catch (err) {
      const msg = adminErrorMessage(err, 'Invalid credentials.');
      set({ loading: false, error: msg });
      throw new Error(msg);
    }
  },

  async logout() {
    try { await adminLogout(); } catch (_) {}
    set({ ...initialState, checked: true });
  },
}));
