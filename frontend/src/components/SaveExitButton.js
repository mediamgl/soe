import React, { useState } from 'react';
import { LogOut } from 'lucide-react';
import SaveExitModal from './SaveExitModal';

export default function SaveExitButton() {
  const [open, setOpen] = useState(false);
  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="inline-flex items-center gap-2 text-xs uppercase tracking-wider2 text-navy hover:text-navy-dark font-medium border-b border-transparent hover:border-gold transition-colors"
      >
        <LogOut className="w-3.5 h-3.5" strokeWidth={2} /> Save &amp; exit
      </button>
      <SaveExitModal open={open} onClose={() => setOpen(false)} />
    </>
  );
}
