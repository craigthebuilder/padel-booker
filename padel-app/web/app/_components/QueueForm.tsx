// Server Component — "queue a booking" form bound to a Server Action.

import type { SafeAccount } from '@/lib/db';
import type { Slot } from '@/lib/slots';
import { type Schedule, weekdayName } from '@/lib/schedule';

export function QueueForm({
  accounts,
  slots,
  schedule,
  action,
}: {
  accounts: SafeAccount[];
  slots: Slot[];
  schedule: Schedule;
  action: (formData: FormData) => void;
}) {
  const defaultAccountId = String(
    accounts.find((a) => a.is_default)?.id ?? accounts[0]?.id ?? '',
  );

  return (
    <section className="rounded-xl border border-white/10 bg-white/[0.02] p-5">
      <h2 className="text-lg font-semibold">Queue a booking</h2>

      <div className="mt-3 rounded-lg border border-accent/20 bg-accent/[0.07] p-3 text-sm leading-relaxed">
        <div>
          Strike fires{' '}
          <span className="font-mono font-semibold text-accent">
            {schedule.triggerDate} · 07:02 ET
          </span>
        </div>
        <div className="mt-0.5">
          Books{' '}
          <span className="font-mono font-semibold text-accent">
            {schedule.targetDate} ({weekdayName(schedule.targetDate)})
          </span>{' '}
          <span className="text-white/45">
            — {schedule.targetWeekend ? 'weekend' : 'weekday'} slots
          </span>
        </div>
      </div>

      <form action={action} className="mt-4 flex flex-col gap-3">
        <label className="flex flex-col gap-1 text-sm">
          <span className="font-medium text-white/70">Account</span>
          <select
            name="account_id"
            defaultValue={defaultAccountId}
            className="rounded-md border border-white/15 bg-black px-3 py-2 text-white focus:border-accent focus:outline-none"
          >
            {accounts.map((a) => (
              <option key={a.id} value={a.id}>
                {a.label}
              </option>
            ))}
          </select>
        </label>

        <label className="flex flex-col gap-1 text-sm">
          <span className="font-medium text-white/70">Time slot</span>
          <select
            name="slot"
            defaultValue={
              slots[0] ? `${slots[0].hour_start}-${slots[0].hour_end}` : ''
            }
            className="rounded-md border border-white/15 bg-black px-3 py-2 text-white focus:border-accent focus:outline-none"
          >
            {slots.map((s) => (
              <option key={s.label} value={`${s.hour_start}-${s.hour_end}`}>
                {s.label}
              </option>
            ))}
          </select>
        </label>

        <button
          type="submit"
          className="mt-1 rounded-md bg-accent px-4 py-2 font-semibold text-black transition hover:opacity-90"
        >
          Queue strike
        </button>
      </form>
    </section>
  );
}
