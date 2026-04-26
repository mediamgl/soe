import React, { useEffect, useRef } from 'react';
import { X } from 'lucide-react';

export default function Modal({ open, onClose, title, children, size = 'md' }) {
  const panelRef = useRef(null);
  // Keep onClose in a ref so the effect below doesn't re-run when the parent
  // passes a new function identity on each render. Without this, an inline
  // arrow like `onClose={() => setOpen(false)}` (recreated on every parent
  // render) would re-trigger the effect, calling panelRef.focus() and
  // stealing focus from any input the user is typing in. Classic React
  // focus-loss footgun. Single dep `[open]` + ref makes the effect a true
  // mount-on-open / cleanup-on-close.
  const onCloseRef = useRef(onClose);
  useEffect(() => { onCloseRef.current = onClose; }, [onClose]);

  useEffect(() => {
    if (!open) return undefined;
    const onKey = (e) => {
      if (e.key === 'Escape' && onCloseRef.current) onCloseRef.current();
    };
    document.addEventListener('keydown', onKey);
    // focus panel for a11y — runs ONCE per open transition (deps = [open])
    if (panelRef.current) panelRef.current.focus();
    document.body.style.overflow = 'hidden';
    return () => {
      document.removeEventListener('keydown', onKey);
      document.body.style.overflow = '';
    };
  }, [open]);

  if (!open) return null;

  const widthCls = size === 'lg' ? 'max-w-2xl' : 'max-w-lg';

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4 sm:p-6"
      role="dialog"
      aria-modal="true"
      aria-label={title || 'Dialog'}
    >
      <button
        type="button"
        aria-label="Close dialog backdrop"
        className="absolute inset-0 bg-navy-deep/60"
        onClick={onClose}
        tabIndex={-1}
      />
      <div
        ref={panelRef}
        tabIndex={-1}
        className={`relative bg-white border border-hairline w-full ${widthCls} max-h-[90vh] overflow-y-auto shadow-lg`}
      >
        <div className="flex items-start justify-between gap-4 p-6 sm:p-7 border-b border-hairline">
          <h2 className="font-serif text-xl sm:text-2xl text-navy leading-snug">{title}</h2>
          <button
            type="button"
            onClick={onClose}
            className="flex-none text-muted hover:text-navy transition-colors"
            aria-label="Close"
          >
            <X className="w-5 h-5" strokeWidth={2} />
          </button>
        </div>
        <div className="p-6 sm:p-7">{children}</div>
      </div>
    </div>
  );
}
