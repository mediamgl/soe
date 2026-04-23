import React, { useEffect, useState } from 'react';
import { Copy, Check } from 'lucide-react';

export default function ResumeCodeCard({ code, heading = 'Your resume code', note }) {
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    if (!copied) return;
    const t = setTimeout(() => setCopied(false), 1800);
    return () => clearTimeout(t);
  }, [copied]);

  async function onCopy() {
    try {
      if (navigator.clipboard && navigator.clipboard.writeText) {
        await navigator.clipboard.writeText(code);
      } else {
        // Fallback
        const el = document.createElement('textarea');
        el.value = code;
        document.body.appendChild(el);
        el.select();
        document.execCommand('copy');
        document.body.removeChild(el);
      }
      setCopied(true);
    } catch (_) {
      // ignore
    }
  }

  return (
    <div className="card card-gold-top">
      <p className="eyebrow">{heading}</p>
      <div className="mt-4 flex items-center gap-3 flex-wrap">
        <code
          className="font-mono text-2xl sm:text-3xl tracking-[0.15em] text-navy select-all bg-mist border border-hairline px-4 py-2"
          aria-label="Resume code"
        >
          {code}
        </code>
        <button
          type="button"
          onClick={onCopy}
          className="inline-flex items-center gap-2 border border-navy text-navy px-4 py-2 text-xs uppercase tracking-wider2 font-medium hover:bg-navy hover:text-white transition-colors"
          aria-label="Copy resume code to clipboard"
        >
          {copied ? (
            <>
              <Check className="w-4 h-4" strokeWidth={2.5} /> Copied
            </>
          ) : (
            <>
              <Copy className="w-4 h-4" strokeWidth={2} /> Copy
            </>
          )}
        </button>
      </div>
      {note && <p className="mt-5 text-sm text-ink/75 leading-relaxed">{note}</p>}
    </div>
  );
}
