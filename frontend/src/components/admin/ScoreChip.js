import React from 'react';

const COLOUR_CLASS = {
  navy: 'bg-navy text-white',
  gold: 'bg-gold text-navy',
  terracotta: 'bg-terracotta text-white',
};

export default function ScoreChip({ colour, children, size = 'md' }) {
  const cls = COLOUR_CLASS[colour] || 'bg-hairline text-ink/70';
  const sizeCls = size === 'sm'
    ? 'text-[10px] px-2 py-0.5'
    : 'text-[11px] px-2.5 py-1';
  return (
    <span className={`inline-block uppercase tracking-wider2 font-medium ${sizeCls} ${cls}`}>
      {children || '—'}
    </span>
  );
}
