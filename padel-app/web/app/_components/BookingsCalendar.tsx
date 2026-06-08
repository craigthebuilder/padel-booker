// Server Component — "current bookings" as a compact 2-week calendar that starts
// TODAY (we can only book ~a week ahead, so two weeks comfortably covers it).
// Booked days glow light-blue; hover shows the account + when it was booked.

import type { Booking } from '@/lib/db';
import { addDays, etDateStr, fmtSlotTime, weekdayName } from '@/lib/schedule';

const DAYS = 14;

function monthLabel(dateStr: string): string {
  const [y, m, d] = dateStr.split('-').map(Number);
  return new Date(Date.UTC(y, m - 1, d)).toLocaleDateString('en-US', {
    month: 'short',
    year: 'numeric',
    timeZone: 'UTC',
  });
}

export function BookingsCalendar({
  bookings,
  accountLabels,
}: {
  bookings: Booking[];
  accountLabels: Record<number, string>;
}) {
  const byDate: Record<string, Booking[]> = {};
  for (const b of bookings) (byDate[b.target_date] ??= []).push(b);

  const today = etDateStr(new Date());
  const days = Array.from({ length: DAYS }, (_, i) => addDays(today, i));
  const range =
    monthLabel(days[0]) === monthLabel(days[DAYS - 1])
      ? monthLabel(days[0])
      : `${monthLabel(days[0])} – ${monthLabel(days[DAYS - 1])}`;

  return (
    <section className="rounded-xl border border-white/10 bg-white/[0.02] p-5">
      <div className="flex items-baseline justify-between">
        <h2 className="text-lg font-semibold">Current bookings</h2>
        <span className="text-xs text-white/40">Next 2 weeks · {range}</span>
      </div>

      <div className="mt-4 grid grid-cols-7 gap-1.5">
        {days.map((d, i) => {
          const dayBookings = byDate[d] ?? [];
          const booked = dayBookings.length > 0;
          const isToday = i === 0;
          return (
            <div
              key={d}
              className={`group relative flex flex-col items-center justify-center gap-0.5 rounded-md border py-3 ${
                booked
                  ? 'border-accent/50 bg-accent/20 text-white'
                  : 'border-white/10 text-white/45'
              } ${isToday ? 'ring-1 ring-accent' : ''}`}
            >
              <span className="text-[10px] uppercase tracking-wide text-white/35">
                {weekdayName(d)}
              </span>
              <span className="text-sm font-medium">{Number(d.slice(8, 10))}</span>

              {booked && (
                <div className="pointer-events-none absolute bottom-full left-1/2 z-10 mb-2 hidden -translate-x-1/2 whitespace-nowrap rounded-md border border-accent/40 bg-black px-3 py-2 text-left text-[11px] leading-relaxed shadow-xl group-hover:block">
                  <div className="mb-1 font-mono text-white/50">{d}</div>
                  {dayBookings.map((b) => (
                    <div key={b.id}>
                      <span className="font-mono text-accent">
                        {fmtSlotTime(b.hour_start)}–{fmtSlotTime(b.hour_end)}
                      </span>{' '}
                      · {accountLabels[b.account_id] ?? `#${b.account_id}`}
                      {b.court_label ? ` · ${b.court_label}` : ''}
                      <div className="text-white/45">booked {b.created_at} UTC</div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          );
        })}
      </div>

      {bookings.length === 0 && (
        <p className="mt-3 text-xs text-white/40">
          No confirmed bookings yet — booked days will light up here.
        </p>
      )}
    </section>
  );
}
