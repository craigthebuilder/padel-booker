// Server Component — strikes that are queued but haven't fired yet.

import type { BookingRequest } from '@/lib/db';
import { fmtSlotTime, weekdayName } from '@/lib/schedule';

export function PendingStrikes({
  requests,
  accountLabels,
}: {
  requests: BookingRequest[];
  accountLabels: Record<number, string>;
}) {
  return (
    <section className="rounded-xl border border-white/10 bg-white/[0.02] p-5">
      <h2 className="text-lg font-semibold">Queued strikes</h2>

      {requests.length === 0 ? (
        <p className="mt-3 text-sm text-white/40">
          Nothing queued. Submit the form above to schedule a strike.
        </p>
      ) : (
        <ul className="mt-3 flex flex-col divide-y divide-white/10">
          {requests.map((r) => (
            <li key={r.id} className="py-2.5 text-sm">
              <div className="font-mono">
                <span className="text-accent">
                  {weekdayName(r.target_date)} {r.target_date}
                </span>{' '}
                · {fmtSlotTime(r.hour_start)}–{fmtSlotTime(r.hour_end)}
              </div>
              <div className="mt-0.5 text-xs text-white/45">
                fires {r.trigger_at.replace('T', ' ')} ET ·{' '}
                {accountLabels[r.account_id] ?? `#${r.account_id}`}
              </div>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
