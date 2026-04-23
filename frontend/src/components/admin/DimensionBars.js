import React from 'react';

// Horizontal bar chart of dimension averages (0-5 scale). Colours by band.
function bandColour(score) {
  if (score == null) return '#d1d5db';
  if (score >= 4.2) return '#1e3a5f';
  if (score >= 3.5) return '#d4a84b';
  return '#b85c38';
}

export default function DimensionBars({ rows = [] }) {
  return (
    <div className="space-y-3">
      {rows.map((r) => {
        const mean = r.mean_score;
        const pct = mean == null ? 0 : Math.max(0, Math.min(100, (mean / 5) * 100));
        return (
          <div key={r.dimension_id}>
            <div className="flex items-baseline justify-between mb-1">
              <span className="text-[13px] text-navy font-medium">{r.name}</span>
              <span className="text-[11px] text-muted">
                {mean == null ? 'No data' : `${mean.toFixed(2)} / 5`}
                <span className="text-muted/60 ml-2">n={r.sample_size}</span>
              </span>
            </div>
            <div className="h-2 bg-hairline">
              <div className="h-2" style={{ width: `${pct}%`, background: bandColour(mean) }} />
            </div>
          </div>
        );
      })}
    </div>
  );
}
