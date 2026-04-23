import React, { useMemo } from 'react';

// Tiny inline SVG sparkline. Pass values as an array of numbers. Width/height in px.
export default function Sparkline({ values = [], width = 110, height = 28, stroke = '#1e3a5f', fill = null }) {
  const path = useMemo(() => {
    if (!values || values.length === 0) return '';
    const max = Math.max(1, ...values);
    const min = Math.min(0, ...values);
    const range = max - min || 1;
    const step = values.length > 1 ? width / (values.length - 1) : width;
    return values.map((v, i) => {
      const x = i * step;
      const y = height - ((v - min) / range) * (height - 4) - 2;
      return `${i === 0 ? 'M' : 'L'}${x.toFixed(1)},${y.toFixed(1)}`;
    }).join(' ');
  }, [values, width, height]);

  if (!values || values.length === 0) {
    return <svg width={width} height={height} />;
  }
  return (
    <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`} role="img" aria-label="Trend">
      {fill && <path d={`${path} L${width},${height} L0,${height} Z`} fill={fill} />}
      <path d={path} fill="none" stroke={stroke} strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}
