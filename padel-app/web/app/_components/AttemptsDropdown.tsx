'use client';

// Client Component — collapsible "attempts" log (needs open/close state).

import { useState } from 'react';
import type { Attempt } from '@/lib/db';
import { fmtSlotTime } from '@/lib/schedule';

const OUTCOME: Record<string, { label: string; cls: string }> = {
  success: { label: 'Booked', cls: 'bg-accent/20 text-accent' },
  'definitive-fail': { label: 'Failed', cls: 'bg-red-500/20 text-red-400' },
  'transient-fail': { label: 'Missed', cls: 'bg-amber-500/20 text-amber-400' },
  error: { label: 'Error', cls: 'bg-white/10 text-white/60' },
};

export function AttemptsDropdown({
  attempts,
  accountLabels,
}: {
  attempts: Attempt[];
  accountLabels: Record<number, string>;
}) {
  const [open, setOpen] = useState(false);

  return (
    <section className="rounded-xl border border-white/10 bg-white/[0.02]">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="flex w-full items-center justify-between px-5 py-4 text-left"
      >
        <span className="text-lg font-semibold">
          Attempts <span className="text-sm text-white/40">({attempts.length})</span>
        </span>
        <span
          className={`text-white/50 transition-transform ${open ? 'rotate-180' : ''}`}
        >
          ▾
        </span>
      </button>

      {open && (
        <div className="px-5 pb-5">
          {attempts.length === 0 ? (
            <p className="text-sm text-white/40">No attempts yet.</p>
          ) : (
            <ul className="flex flex-col divide-y divide-white/10">
              {attempts.map((a) => {
                const o = OUTCOME[a.outcome] ?? OUTCOME.error;
                return (
                  <li key={a.id} className="py-3 text-sm">
                    <div className="flex items-center justify-between gap-2">
                      <span
                        className={`rounded px-2 py-0.5 text-xs font-semibold ${o.cls}`}
                      >
                        {o.label}
                      </span>
                      <span className="font-mono text-xs text-white/40">
                        {a.fired_at}
                      </span>
                    </div>
                    <div className="mt-1 font-mono text-xs">
                      {a.target_date} · {fmtSlotTime(a.hour_start)}–
                      {fmtSlotTime(a.hour_end)} ·{' '}
                      {accountLabels[a.account_id] ?? `#${a.account_id}`}
                    </div>
                    {a.message ? (
                      <div className="mt-0.5 truncate text-xs text-white/40">
                        HTTP {a.http_status ?? '—'} · {a.message}
                      </div>
                    ) : null}
                  </li>
                );
              })}
            </ul>
          )}
        </div>
      )}
    </section>
  );
}
