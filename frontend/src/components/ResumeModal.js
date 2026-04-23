import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import Modal from './Modal';
import { useSession } from '../store/sessionStore';
import { STAGE_PATH } from '../store/sessionStore';

export default function ResumeModal({ open, onClose }) {
  const [code, setCode] = useState('');
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);
  const hydrate = useSession((s) => s.hydrateFromResumeCode);
  const navigate = useNavigate();

  async function onSubmit(e) {
    e.preventDefault();
    setError(null);
    if (!code.trim()) {
      setError('Please enter a resume code.');
      return;
    }
    setBusy(true);
    try {
      const resp = await hydrate(code);
      const path = STAGE_PATH[resp.stage] || '/context';
      onClose();
      navigate(path);
    } catch (err) {
      setError(err.message || 'Resume code not found.');
    } finally {
      setBusy(false);
    }
  }

  function onChange(v) {
    // normalise: uppercase + hyphen after 4 chars, strip other chars
    const clean = v.replace(/[^A-Za-z0-9-]/g, '').toUpperCase();
    setCode(clean);
  }

  return (
    <Modal open={open} onClose={onClose} title="Resume a session">
      <p className="text-sm text-ink/75 leading-relaxed">
        Enter the resume code you received when you began the assessment.
        Codes are 8 characters with a dash in the middle (for example,
        <span className="whitespace-nowrap font-mono text-navy mx-1">A7F3-KQ29</span>).
      </p>
      <form onSubmit={onSubmit} className="mt-6 space-y-4">
        <label className="block">
          <span className="text-xs uppercase tracking-wider2 text-navy font-medium">Resume code</span>
          <input
            type="text"
            inputMode="text"
            autoComplete="off"
            spellCheck={false}
            value={code}
            onChange={(e) => onChange(e.target.value)}
            className="mt-2 w-full font-mono text-lg tracking-[0.15em] text-navy bg-white border border-hairline px-4 py-3 focus:border-navy"
            placeholder="XXXX-XXXX"
            maxLength={9}
            aria-invalid={Boolean(error)}
            aria-describedby={error ? 'resume-err' : undefined}
          />
        </label>
        {error && (
          <p id="resume-err" className="text-sm text-red-700">{error}</p>
        )}
        <div className="flex items-center justify-end gap-3 pt-2">
          <button type="button" onClick={onClose} className="btn-ghost">Cancel</button>
          <button type="submit" disabled={busy} className="btn-primary disabled:opacity-60">
            {busy ? 'Resuming…' : 'Resume'}
          </button>
        </div>
      </form>
    </Modal>
  );
}
