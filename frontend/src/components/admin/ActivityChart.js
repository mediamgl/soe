import React, { useMemo } from 'react';

// 14-day activity line chart. Two series: new_sessions (navy), completions (gold).
export default function ActivityChart({ data = [], height = 140 }) {
  const { pathNew, pathDone, labels } = useMemo(() => {
    if (!data.length) return { pathNew: '', pathDone: '', labels: [] };
    const width = 620;
    const max = Math.max(1, ...data.flatMap((d) => [d.new_sessions, d.completions]));
    const step = width / Math.max(1, data.length - 1);
    const mk = (key) => data.map((d, i) => {
      const x = i * step;
      const y = height - ((d[key] / max) * (height - 14)) - 6;
      return `${i === 0 ? 'M' : 'L'}${x.toFixed(1)},${y.toFixed(1)}`;
    }).join(' ');
    const labels = data.map((d) => d.date.slice(5));
    return { pathNew: mk('new_sessions'), pathDone: mk('completions'), labels, width };
  }, [data, height]);

  if (!data.length) {
    return <p className="text-sm text-muted italic">No activity yet.</p>;
  }
  return (
    <div>
      <svg viewBox={`0 0 620 ${height}`} className="w-full" role="img" aria-label="14-day activity">
        <path d={pathNew} fill="none" stroke="#1e3a5f" strokeWidth={1.75} strokeLinecap="round" strokeLinejoin="round" />
        <path d={pathDone} fill="none" stroke="#d4a84b" strokeWidth={1.75} strokeLinecap="round" strokeLinejoin="round" strokeDasharray="4 2" />
      </svg>
      <div className="mt-3 flex items-center justify-between text-[10px] text-muted">
        <span>{labels[0]}</span>
        <span>{labels[Math.floor(labels.length / 2)]}</span>
        <span>{labels[labels.length - 1]}</span>
      </div>
      <div className="mt-3 flex items-center gap-5 text-xs">
        <span className="flex items-center gap-2"><span className="inline-block w-4 h-[2px] bg-navy" />New sessions</span>
        <span className="flex items-center gap-2"><span className="inline-block w-4 h-[2px] bg-gold" />Completions</span>
      </div>
    </div>
  );
}
