import React from 'react';
import { ArrowDownRight, ArrowUpRight } from 'lucide-react';
import Sparkline from './Sparkline';

export default function StatTile({
  label,
  value,
  unit,
  sparkValues,
  delta,
  deltaDir, // 'up' | 'down' | null
  accent = 'navy', // 'navy' | 'gold' | 'terracotta'
  hint,
  loading = false,
}) {
  const accentCls = {
    navy: 'border-t-navy',
    gold: 'border-t-gold',
    terracotta: 'border-t-terracotta',
  }[accent] || 'border-t-navy';

  return (
    <div className={`bg-white border border-hairline border-t-[3px] ${accentCls} p-5 min-h-[116px] flex flex-col justify-between`}>
      <p className="text-[10px] uppercase tracking-wider2 text-muted">{label}</p>
      {loading ? (
        <div className="mt-3 h-8 w-24 bg-hairline animate-pulse" />
      ) : (
        <div className="flex items-end justify-between gap-4 mt-3">
          <div className="flex items-baseline gap-1.5">
            <span className="text-3xl font-serif text-navy leading-none">{value ?? '—'}</span>
            {unit && <span className="text-xs text-muted">{unit}</span>}
          </div>
          {sparkValues && sparkValues.length > 0 && (
            <div aria-hidden="true">
              <Sparkline values={sparkValues} width={100} height={28} stroke="#1e3a5f" />
            </div>
          )}
        </div>
      )}
      {(delta !== undefined && deltaDir) && (
        <p className="mt-2 text-[11px] flex items-center gap-1">
          {deltaDir === 'up' ? (
            <ArrowUpRight className="w-3 h-3 text-navy" strokeWidth={2} />
          ) : deltaDir === 'down' ? (
            <ArrowDownRight className="w-3 h-3 text-terracotta" strokeWidth={2} />
          ) : null}
          <span className={deltaDir === 'down' ? 'text-terracotta' : 'text-navy/80'}>{delta}</span>
        </p>
      )}
      {hint && !delta && <p className="mt-2 text-[11px] text-muted">{hint}</p>}
    </div>
  );
}
