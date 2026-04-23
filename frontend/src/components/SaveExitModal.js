import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import Modal from './Modal';
import ResumeCodeCard from './ResumeCodeCard';
import { useSession } from '../store/sessionStore';

export default function SaveExitModal({ open, onClose }) {
  const resumeCode = useSession((s) => s.resumeCode);
  const saveAndExit = useSession((s) => s.saveAndExit);
  const navigate = useNavigate();
  const [leaving, setLeaving] = useState(false);

  function onLeave() {
    setLeaving(true);
    saveAndExit();
    onClose();
    navigate('/');
  }

  return (
    <Modal open={open} onClose={onClose} title="Save and exit">
      <p className="text-sm text-ink/75 leading-relaxed">
        Your progress is saved. Use this resume code to return to your assessment at any point in the next 60 days.
      </p>
      <div className="mt-6">
        {resumeCode ? (
          <ResumeCodeCard
            code={resumeCode}
            heading="Your resume code"
            note="We’ve also stashed this code in this browser for convenience."
          />
        ) : (
          <p className="text-sm text-muted">No active session.</p>
        )}
      </div>
      <div className="mt-8 flex items-center justify-end gap-3">
        <button type="button" onClick={onClose} className="btn-ghost">Keep going</button>
        <button type="button" onClick={onLeave} disabled={leaving} className="btn-primary disabled:opacity-60">
          {leaving ? 'Exiting…' : 'Exit to home'}
        </button>
      </div>
    </Modal>
  );
}
