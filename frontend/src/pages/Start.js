import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useSession } from '../store/sessionStore';
import ResumeCodeCard from '../components/ResumeCodeCard';

function validateEmail(v) {
  // Lightweight client-side check; server does the authoritative check.
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(v);
}

export default function Start() {
  const navigate = useNavigate();
  const startSession = useSession((s) => s.startSession);
  const advanceStage = useSession((s) => s.advanceStage);
  const loading = useSession((s) => s.loading);
  const storeError = useSession((s) => s.error);
  const lastCreated = useSession((s) => s.lastCreated);
  const clearLastCreated = useSession((s) => s.clearLastCreated);
  const resumeCode = useSession((s) => s.resumeCode);

  const [form, setForm] = useState({
    name: '',
    email: '',
    organisation: '',
    role: '',
    consent: false,
  });
  const [errors, setErrors] = useState({});
  const [continuing, setContinuing] = useState(false);

  useEffect(() => {
    // Reset the "just created" state if we land here fresh.
    return () => { /* no-op cleanup */ };
  }, []);

  function update(key, value) {
    setForm((f) => ({ ...f, [key]: value }));
  }

  async function onSubmit(e) {
    e.preventDefault();
    const ers = {};
    if (!form.name.trim()) ers.name = 'Please enter your full name.';
    if (!form.email.trim()) ers.email = 'Please enter your email.';
    else if (!validateEmail(form.email)) ers.email = 'That email doesn’t look quite right.';
    if (!form.consent) ers.consent = 'Please accept the consent statement to continue.';
    setErrors(ers);
    if (Object.keys(ers).length > 0) return;

    try {
      await startSession({
        name: form.name.trim(),
        email: form.email.trim(),
        organisation: form.organisation.trim() || undefined,
        role: form.role.trim() || undefined,
        consent: true,
      });
    } catch (err) {
      setErrors({ submit: err.message });
    }
  }

  async function onContinue() {
    setContinuing(true);
    try {
      await advanceStage('context');
      clearLastCreated();
      navigate('/context');
    } catch (err) {
      setErrors({ submit: err.message });
    } finally {
      setContinuing(false);
    }
  }

  const created = Boolean(lastCreated && lastCreated.sessionId);

  return (
    <section className="max-w-content mx-auto px-6 sm:px-8 pt-16 sm:pt-24 pb-20">
      <div className="max-w-2xl">
        <span className="eyebrow">Begin Assessment</span>
        <h1 className="mt-4 text-3xl sm:text-4xl md:text-5xl font-serif text-navy tracking-tight leading-tight">
          A little about you
        </h1>
        <span className="mt-6 gold-rule block" aria-hidden="true" />
        <p className="mt-6 text-base sm:text-lg text-ink/75 leading-relaxed">
          We capture a small amount of information so we can save your progress and return your
          personalised profile to the right person. You can leave and resume at any point using the
          code we issue.
        </p>
      </div>

      {!created && (
        <form onSubmit={onSubmit} className="mt-12 max-w-2xl space-y-5" noValidate>
          <FormField label="Full name" required error={errors.name} htmlFor="f-name">
            <input
              id="f-name"
              type="text"
              autoComplete="name"
              value={form.name}
              onChange={(e) => update('name', e.target.value)}
              className="form-input"
              aria-invalid={Boolean(errors.name)}
            />
          </FormField>

          <FormField label="Email" required error={errors.email} htmlFor="f-email">
            <input
              id="f-email"
              type="email"
              autoComplete="email"
              value={form.email}
              onChange={(e) => update('email', e.target.value)}
              className="form-input"
              aria-invalid={Boolean(errors.email)}
            />
          </FormField>

          <div className="grid sm:grid-cols-2 gap-5">
            <FormField label="Organisation" htmlFor="f-org" hint="Optional">
              <input
                id="f-org"
                type="text"
                autoComplete="organization"
                value={form.organisation}
                onChange={(e) => update('organisation', e.target.value)}
                className="form-input"
              />
            </FormField>
            <FormField label="Role / Title" htmlFor="f-role" hint="Optional">
              <input
                id="f-role"
                type="text"
                autoComplete="organization-title"
                value={form.role}
                onChange={(e) => update('role', e.target.value)}
                className="form-input"
              />
            </FormField>
          </div>

          <label className="flex items-start gap-3 pt-2 cursor-pointer">
            <input
              type="checkbox"
              checked={form.consent}
              onChange={(e) => update('consent', e.target.checked)}
              className="mt-1 h-4 w-4 accent-navy"
              aria-invalid={Boolean(errors.consent)}
            />
            <span className="text-sm text-ink/80 leading-relaxed">
              I understand my responses will be stored securely and used for my assessment and
              authorised review, and deleted after 60&nbsp;days unless flagged for archive.
            </span>
          </label>
          {errors.consent && <p className="text-sm text-red-700">{errors.consent}</p>}

          {(errors.submit || storeError) && (
            <p className="text-sm text-red-700">{errors.submit || storeError}</p>
          )}

          <div className="pt-4">
            <button type="submit" disabled={loading} className="btn-primary disabled:opacity-60">
              {loading ? 'Creating session…' : 'Create session'}
            </button>
          </div>
        </form>
      )}

      {created && resumeCode && (
        <div className="mt-12 max-w-2xl">
          <div className="card card-gold-top">
            <p className="eyebrow">Session created</p>
            <h2 className="mt-3 text-2xl font-serif text-navy">Save your resume code</h2>
            <p className="mt-3 text-sm text-ink/75 leading-relaxed">
              Your session has been created. Your resume code is shown below. Save it somewhere
              safe &mdash; you can use it to resume if you close your browser. A copy has been
              emailed to you.
            </p>
            <div className="mt-6">
              <ResumeCodeCard code={resumeCode} heading="Your resume code" />
            </div>
            <p className="mt-6 text-xs uppercase tracking-wider2 text-muted">
              Email delivery is stubbed in this phase; a real email will be sent once email integration is live.
            </p>
            <div className="mt-8 flex items-center justify-end">
              <button
                type="button"
                onClick={onContinue}
                disabled={continuing}
                className="btn-primary disabled:opacity-60"
              >
                {continuing ? 'Continuing…' : 'Continue'}
              </button>
            </div>
          </div>
        </div>
      )}
    </section>
  );
}

function FormField({ label, required, error, hint, htmlFor, children }) {
  return (
    <label className="block" htmlFor={htmlFor}>
      <span className="flex items-baseline justify-between">
        <span className="text-xs uppercase tracking-wider2 text-navy font-medium">
          {label} {required && <span className="text-gold">*</span>}
        </span>
        {hint && <span className="text-[11px] uppercase tracking-wider2 text-muted">{hint}</span>}
      </span>
      <div className="mt-2">{children}</div>
      {error && <p className="mt-2 text-sm text-red-700">{error}</p>}
    </label>
  );
}
