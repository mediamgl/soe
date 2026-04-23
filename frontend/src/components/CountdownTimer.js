import React, { useEffect, useRef, useState } from 'react';

/**
 * CountdownTimer — shows mm:ss counting DOWN from targetMinutes. When it hits 0,
 * continues counting UP in muted colour prefixed with '+'. Never auto-submits.
 * A subtle tooltip reads "Target time only. Take the time you need.".
 */
export default function CountdownTimer({ targetMinutes, label, startKey }) {
  const [elapsedMs, setElapsedMs] = useState(0);
  const rafRef = useRef(null);
  const startRef = useRef(null);
  const lastAnnouncedMinute = useRef(null);
  const [announceText, setAnnounceText] = useState('');

  useEffect(() => {
    // Reset on phase change
    startRef.current = performance.now();
    setElapsedMs(0);
    lastAnnouncedMinute.current = null;
  }, [startKey]);

  useEffect(() => {
    let mounted = true;
    function tick() {
      if (!mounted || startRef.current == null) return;
      const e = performance.now() - startRef.current;
      setElapsedMs(e);
      // Announce on minute boundary only (not every second)
      const mins = Math.floor(e / 60000);
      if (mins !== lastAnnouncedMinute.current) {
        lastAnnouncedMinute.current = mins;
        const target = targetMinutes * 60;
        const s = Math.floor(e / 1000);
        if (s < target) {
          setAnnounceText(`${Math.floor((target - s) / 60)} minutes remaining`);
        } else {
          const over = s - target;
          setAnnounceText(`${Math.floor(over / 60)} minutes over target`);
        }
      }
      rafRef.current = requestAnimationFrame(tick);
    }
    rafRef.current = requestAnimationFrame(tick);
    return () => {
      mounted = false;
      if (rafRef.current) cancelAnimationFrame(rafRef.current);
    };
  }, [targetMinutes]);

  const targetSec = targetMinutes * 60;
  const elapsedSec = Math.floor(elapsedMs / 1000);
  const remaining = targetSec - elapsedSec;
  const over = remaining < 0;
  const absSec = Math.abs(remaining);
  const mm = String(Math.floor(absSec / 60)).padStart(2, '0');
  const ss = String(absSec % 60).padStart(2, '0');
  const display = (over ? '+' : '') + `${mm}:${ss}`;

  return (
    <div
      className="border border-hairline bg-white px-4 py-3 min-w-[200px]"
      title="Target time only. Take the time you need."
    >
      {label && <p className="text-[10px] uppercase tracking-wider2 text-muted leading-none">{label}</p>}
      <p
        className={
          'mt-1 font-serif text-3xl tabular-nums leading-none ' +
          (over ? 'text-muted' : 'text-navy')
        }
        aria-hidden="true"
      >
        {display}
      </p>
      <p className="mt-1 text-[10px] uppercase tracking-wider2 text-muted">
        Target {targetMinutes} min
      </p>
      <span className="sr-only" aria-live="polite">{announceText}</span>
    </div>
  );
}
