import React, { useEffect, useState } from 'react';
import { Outlet, useLocation, useNavigate } from 'react-router-dom';
import ProgressStepper from './ProgressStepper';
import SaveExitButton from './SaveExitButton';
import { useSession } from '../store/sessionStore';

export default function AssessmentLayout() {
  const { pathname } = useLocation();
  const navigate = useNavigate();
  const sessionId = useSession((s) => s.sessionId);
  const hydrate = useSession((s) => s.hydrateFromLocalStorage);
  const [checking, setChecking] = useState(!sessionId);

  useEffect(() => {
    let cancelled = false;
    async function run() {
      if (sessionId) {
        setChecking(false);
        return;
      }
      const resp = await hydrate();
      if (cancelled) return;
      if (!resp) {
        // No session on disk — bounce to landing.
        navigate('/', { replace: true });
        return;
      }
      setChecking(false);
    }
    run();
    return () => { cancelled = true; };
  }, [pathname, sessionId]);

  if (checking) {
    return (
      <div className="max-w-content mx-auto px-6 sm:px-8 py-24 text-center">
        <p className="text-sm uppercase tracking-wider2 text-muted">Loading your session…</p>
      </div>
    );
  }

  // Hide Save & exit on the terminal-screen paths — synthesis is running
  // server-side (nothing to save), and results is the final screen.
  const showSaveExit = !(
    pathname.endsWith("/assessment/processing") || pathname.endsWith("/assessment/results")
  );

  return (
    <div className="max-w-content mx-auto px-6 sm:px-8 pt-8 sm:pt-10 pb-8">
      <div className="flex items-center justify-end mb-4 sm:mb-6 h-6">
        {showSaveExit && <SaveExitButton />}
      </div>
      <ProgressStepper />
      <div className="mt-12 sm:mt-16">
        <Outlet />
      </div>
    </div>
  );
}
