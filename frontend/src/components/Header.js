import React from 'react';
import { Link } from 'react-router-dom';

export default function Header() {
  return (
    <header className="border-b border-hairline">
      <div className="max-w-content mx-auto px-6 sm:px-8 h-16 flex items-center justify-between">
        <Link to="/" className="flex items-center gap-3 group" aria-label="Home">
          <span className="h-6 w-[2px] bg-gold" aria-hidden="true" />
          <span className="font-serif text-navy text-lg tracking-wide group-hover:text-navy-dark transition-colors">
            Transformation Readiness Assessment
          </span>
        </Link>
        <span className="hidden sm:block text-xs uppercase tracking-wider2 text-muted">
          Demonstration
        </span>
      </div>
    </header>
  );
}
