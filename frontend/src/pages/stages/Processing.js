import React, { useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { ArrowRight, RefreshCcw } from 'lucide-react';
import { useSession } from '../../store/sessionStore';
import { processingStart, processingState, apiErrorMessage } from '../../lib/api';

const MIN_DISPLAY_MS = 8000;
const POLL_MS = 3000;
const SLOW_HELPER_AFTER_MS = 90000;

const STATUS_LINES = [
  'Synthesising psychometric signal…',
  'Reviewing your AI fluency discussion…',
  'Mapping strategic-scenario responses…',
  'Composing your profile…',
];

export default function Processing() {
  const navigate = useNavigate();
  const sessionId = useSession((s) => s.sessionId);
  const advanceStage = useSession((s) => s.advanceStage);

  const [status, setStatus] = useState(null); // null | 'in_progress' | 'completed' | 'failed'
  const [error, setError] = useState(null);
  const [startedMountAt] = useState(() => Date.now());
  const [statusIdx, setStatusIdx] = useState(0);
  const [slowHelper, setSlowHelper] = useState(false);
  const [readyToContinue, setReadyToContinue] = useState(false);
  const [retrying, setRetrying] = useState(false);

  const pollRef = useRef(null);
  const statusLineRef = useRef(null);
  const slowRef = useRef(null);
  const mountedRef = useRef(true);

  // Rotate the status line every 3s
  useEffect(() => {
    statusLineRef.current = setInterval(() => {
      setStatusIdx((i) => (i + 1) % STATUS_LINES.length);
    }, 3000);
    return () => clearInterval(statusLineRef.current);
  }, []);

  // "Taking a little longer" after 90s
  useEffect(() => {
    slowRef.current = setTimeout(() => setSlowHelper(true), SLOW_HELPER_AFTER_MS);
    return () => clearTimeout(slowRef.current);
  }, []);

  useEffect(() => { mountedRef.current = true; return () => { mountedRef.current = false; }; }, []);

  // Boot: GET state; if null → POST start. Poll every 3s.
  useEffect(() => {
    if (!sessionId) return;
    let stop = false;

    async function bootAndPoll() {
      try {
        const st = await processingState(sessionId);
        if (stop) return;
        if (!st.status) {
          await processingStart(sessionId);
          setStatus('in_progress');
        } else {
          setStatus(st.status);
        }
      } catch (e) {
        setError(apiErrorMessage(e, 'Could not start synthesis.'));
      }

      // Poll until completed or failed
      pollRef.current = setInterval(async () => {
        if (stop) return;
        try {
          const st = await processingState(sessionId);
          if (stop) return;
          setStatus(st.status);
          if (st.error) setError(st.error);
          if (st.status === 'completed' || st.status === 'failed') {
            clearInterval(pollRef.current);
          }
        } catch (e) {
          // transient — keep polling, but surface the last message
          setError(apiErrorMessage(e, 'Polling failed; retrying…'));
        }
      }, POLL_MS);
    }

    bootAndPoll();
    return () => {
      stop = true;
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, [sessionId]);

  // Respect minimum floor before revealing Continue
  useEffect(() => {
    if (status === 'completed') {
      const elapsed = Date.now() - startedMountAt;
      const wait = Math.max(0, MIN_DISPLAY_MS - elapsed);
      const t = setTimeout(() => {
        if (mountedRef.current) setReadyToContinue(true);
      }, wait);
      return () => clearTimeout(t);
    }
  }, [status, startedMountAt]);

  async function onRetry() {
    setRetrying(true);
    setError(null);
    try {
      await processingStart(sessionId);
      setStatus('in_progress');
      setSlowHelper(false);
    } catch (e) {
      setError(apiErrorMessage(e, 'Could not restart synthesis.'));
    } finally {
      setRetrying(false);
    }
  }

  async function onContinue() {
    try {
      // Server should already have set stage=results; if not, align local store.
      await advanceStage('results').catch(() => {});
    } finally {
      navigate('/assessment/results');
    }
  }

  return (
    <section className="max-w-2xl mx-auto">
      <div className="flex flex-col items-center text-center">
        <PentagonAnimation />
        <div aria-live="polite" className="mt-10 h-6">
          {status === 'failed' ? (
            <p className="text-sm text-red-700 italic font-serif">We couldn’t complete the synthesis.</p>
          ) : readyToContinue ? (
            <p className="text-sm uppercase tracking-wider2 text-gold-dark">Your results are ready.</p>
          ) : (
            <p className="text-base italic font-serif text-navy/80">
              {STATUS_LINES[statusIdx]}
            </p>
          )}
        </div>
        {slowHelper && status === 'in_progress' && (
          <p className="mt-6 text-xs uppercase tracking-wider2 text-muted">
            This is taking a little longer than usual…
          </p>
        )}

        {error && status !== 'completed' && (
          <p className="mt-6 text-xs text-red-700 max-w-md">{error}</p>
        )}

        {status === 'failed' && (
          <div className="mt-10">
            <button type="button" onClick={onRetry} disabled={retrying} className="btn-primary disabled:opacity-60">
              {retrying ? 'Restarting…' : 'Retry synthesis'}
              <RefreshCcw className="w-4 h-4" strokeWidth={2} />
            </button>
          </div>
        )}

        {readyToContinue && status === 'completed' && (
          <div className="mt-10">
            <button type="button" onClick={onContinue} className="btn-primary">
              Continue
              <ArrowRight className="w-4 h-4" strokeWidth={2} />
            </button>
          </div>
        )}
      </div>
    </section>
  );
}

// Pentagon SVG with 5 axes that fill in gold one-by-one on a ~10s loop.
// Uses pure CSS animation; no external dependency.
function PentagonAnimation() {
  // Pentagon vertices at 0, 72, 144, 216, 288 deg from top
  const cx = 120;
  const cy = 120;
  const r = 100;
  const verts = useMemo(() => {
    return Array.from({ length: 5 }, (_, i) => {
      const theta = (-90 + i * 72) * (Math.PI / 180);
      return { x: cx + r * Math.cos(theta), y: cy + r * Math.sin(theta) };
    });
  }, []);
  const polyPoints = verts.map((v) => `${v.x},${v.y}`).join(' ');

  return (
    <div className="relative">
      <svg width="240" height="240" viewBox="0 0 240 240" role="img" aria-label="Synthesising assessment profile">
        {/* Faint concentric outlines */}
        {[0.33, 0.66, 1.0].map((s, i) => (
          <polygon
            key={i}
            points={verts.map((v) => `${cx + (v.x - cx) * s},${cy + (v.y - cy) * s}`).join(' ')}
            fill="none"
            stroke="#1e3a5f"
            strokeOpacity={0.12}
            strokeWidth="1"
          />
        ))}
        {/* 5 axes */}
        {verts.map((v, i) => (
          <line
            key={i}
            x1={cx} y1={cy} x2={v.x} y2={v.y}
            stroke="#d4a84b"
            strokeWidth="2.5"
            strokeLinecap="round"
            style={{
              strokeDasharray: r,
              strokeDashoffset: r,
              animation: `tra-axis-fill 10s linear ${i * 1.6}s infinite`,
            }}
          />
        ))}
        {/* Outer pentagon outline */}
        <polygon
          points={polyPoints}
          fill="none"
          stroke="#1e3a5f"
          strokeWidth="1.25"
          strokeOpacity={0.75}
        />
        {/* Centre dot */}
        <circle cx={cx} cy={cy} r="3" fill="#1e3a5f" />
      </svg>
      <style>{`
        @keyframes tra-axis-fill {
          0%   { stroke-dashoffset: ${r}; opacity: 0.2; }
          30%  { stroke-dashoffset: 0;   opacity: 1; }
          60%  { stroke-dashoffset: 0;   opacity: 1; }
          100% { stroke-dashoffset: ${r}; opacity: 0.2; }
        }
      `}</style>
    </div>
  );
}
