import React from 'react';

export default function Footer() {
  return (
    <footer className="border-t border-hairline mt-24">
      <div className="max-w-content mx-auto px-6 sm:px-8 py-8 flex flex-col sm:flex-row items-center justify-between gap-3">
        <p className="text-sm text-muted text-center sm:text-left">
          Demonstration Version <span className="text-gold mx-2" aria-hidden="true">•</span> Methodology by Steven Bianchi
        </p>
        <span className="h-px w-16 bg-gold hidden sm:block" aria-hidden="true" />
      </div>
    </footer>
  );
}
