import React from 'react';

const COLOUR = {
  navy: '#1e3a5f',
  gold: '#d4a84b',
  terracotta: '#b85c38',
  unknown: '#d1d5db',
};

export default function Donut({ data = {}, size = 180, thickness = 22 }) {
  const entries = ['navy', 'gold', 'terracotta', 'unknown']
    .map((k) => ({ key: k, value: Number(data[k] || 0) }))
    .filter((e) => e.value > 0);
  const total = entries.reduce((s, e) => s + e.value, 0);
  const r = (size - thickness) / 2;
  const cx = size / 2;
  const cy = size / 2;
  if (total === 0) {
    return (
      <div className="flex items-center justify-center" style={{ width: size, height: size }}>
        <p className="text-xs text-muted">No completed sessions yet</p>
      </div>
    );
  }
  let startAngle = -Math.PI / 2;
  const paths = entries.map((e) => {
    const angle = (e.value / total) * Math.PI * 2;
    const endAngle = startAngle + angle;
    const x1 = cx + r * Math.cos(startAngle);
    const y1 = cy + r * Math.sin(startAngle);
    const x2 = cx + r * Math.cos(endAngle);
    const y2 = cy + r * Math.sin(endAngle);
    const largeArc = angle > Math.PI ? 1 : 0;
    const d = `M${x1} ${y1} A${r} ${r} 0 ${largeArc} 1 ${x2} ${y2}`;
    const seg = { d, key: e.key, value: e.value, pct: Math.round((e.value / total) * 100) };
    startAngle = endAngle;
    return seg;
  });
  return (
    <div className="flex items-center gap-6">
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} role="img" aria-label="Score distribution">
        {paths.map((p) => (
          <path key={p.key} d={p.d} stroke={COLOUR[p.key]} strokeWidth={thickness} fill="none" strokeLinecap="butt" />
        ))}
        <text x={cx} y={cy - 6} textAnchor="middle" fontFamily="Playfair Display, Georgia, serif" fontSize="24" fill="#1e3a5f">
          {total}
        </text>
        <text x={cx} y={cy + 14} textAnchor="middle" fontFamily="Inter, sans-serif" fontSize="9" fill="#6b7280" letterSpacing="2">
          COMPLETED
        </text>
      </svg>
      <ul className="text-sm space-y-2">
        {paths.map((p) => (
          <li key={p.key} className="flex items-center gap-2">
            <span className="inline-block w-3 h-3" style={{ background: COLOUR[p.key] }} />
            <span className="text-navy capitalize font-medium">{p.key === 'unknown' ? 'Uncategorised' : p.key}</span>
            <span className="text-muted text-xs">{p.value} ({p.pct}%)</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
