import React, { useEffect, useState } from 'react';
import { useNavigate, useSearchParams, Link } from 'react-router-dom';
import { useAdmin } from '../../store/adminStore';

export default function AdminLogin() {
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const next = params.get('next') || '/admin/settings';
  const { login, loading, email, checked, refresh } = useAdmin();
  const [form, setForm] = useState({ email: '', password: '' });
  const [err, setErr] = useState(null);

  useEffect(() => {
    if (!checked) refresh();
  }, [checked, refresh]);

  useEffect(() => {
    if (email) navigate(next, { replace: true });
  }, [email, next, navigate]);

  async function onSubmit(e) {
    e.preventDefault();
    setErr(null);
    try {
      await login(form.email.trim().toLowerCase(), form.password);
      navigate(next, { replace: true });
    } catch (e2) {
      setErr(e2.message || 'Invalid credentials.');
    }
  }

  return (
    <div className="min-h-screen bg-paper flex flex-col">
      <header className="border-b border-hairline">
        <div className="max-w-content mx-auto px-6 sm:px-8 h-16 flex items-center justify-between">
          <Link to="/" className="flex items-center gap-3">
            <span className="h-6 w-[2px] bg-gold" aria-hidden="true" />
            <span className="font-serif text-navy text-lg tracking-wide">Admin Console</span>
          </Link>
        </div>
      </header>

      <main className="flex-1 flex items-center justify-center px-6 py-16">
        <div className="w-full max-w-md">
          <span className="eyebrow">Restricted</span>
          <h1 className="mt-4 text-3xl font-serif text-navy tracking-tight">Administrator Login</h1>
          <span className="mt-5 gold-rule block" aria-hidden="true" />

          <form onSubmit={onSubmit} className="mt-10 space-y-5" noValidate>
            <label className="block">
              <span className="text-xs uppercase tracking-wider2 text-navy font-medium">Email</span>
              <input
                type="email"
                autoComplete="username"
                className="form-input mt-2"
                value={form.email}
                onChange={(e) => setForm({ ...form, email: e.target.value })}
                required
                autoFocus
              />
            </label>
            <label className="block">
              <span className="text-xs uppercase tracking-wider2 text-navy font-medium">Password</span>
              <input
                type="password"
                autoComplete="current-password"
                className="form-input mt-2"
                value={form.password}
                onChange={(e) => setForm({ ...form, password: e.target.value })}
                required
              />
            </label>
            {err && <p className="text-sm text-red-700">{err}</p>}
            <div className="pt-2">
              <button type="submit" disabled={loading} className="btn-primary w-full disabled:opacity-60">
                {loading ? 'Signing in…' : 'Sign in'}
              </button>
            </div>
          </form>
        </div>
      </main>

      <footer className="border-t border-hairline">
        <div className="max-w-content mx-auto px-6 sm:px-8 py-5 text-xs uppercase tracking-wider2 text-muted">
          Admin console
        </div>
      </footer>
    </div>
  );
}
