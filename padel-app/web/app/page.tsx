import Link from 'next/link';
import {
  listAccounts,
  listAttempts,
  listBookings,
  listPendingRequests,
} from '@/lib/db';
import { computeSchedule } from '@/lib/schedule';
import { slotsFor } from '@/lib/slots';
import { queueBooking } from './actions';
import { logout } from './login/actions';
import { QueueForm } from './_components/QueueForm';
import { PendingStrikes } from './_components/PendingStrikes';
import { BookingsCalendar } from './_components/BookingsCalendar';
import { AttemptsDropdown } from './_components/AttemptsDropdown';

// Next 16: cacheComponents is off by default, so force per-request rendering
// to always reflect the latest DB state.
export const dynamic = 'force-dynamic';

export default function Home() {
  const accounts = listAccounts();
  const attempts = listAttempts();
  const bookings = listBookings();
  const pending = listPendingRequests();

  const schedule = computeSchedule();
  const slots = slotsFor(schedule.targetWeekend);

  const accountLabels: Record<number, string> = Object.fromEntries(
    accounts.map((a) => [a.id, a.label]),
  );

  return (
    <div className="mx-auto w-full max-w-6xl px-6 py-10">
      <header className="mb-8 flex flex-wrap items-center justify-between gap-4">
        <h1 className="text-2xl font-semibold tracking-tight">
          Key Biscayne Cliff Drysdale Court Booker
        </h1>
        <div className="flex items-center gap-2">
          <Link
            href="/accounts"
            className="rounded-md border border-white/15 px-3 py-1.5 text-sm text-white/80 transition hover:border-accent hover:text-accent"
          >
            Accounts
          </Link>
          <form action={logout}>
            <button
              type="submit"
              className="rounded-md border border-white/15 px-3 py-1.5 text-sm text-white/60 transition hover:border-red-400 hover:text-red-400"
            >
              Lock
            </button>
          </form>
        </div>
      </header>

      <div className="grid gap-6 lg:grid-cols-2">
        <div className="flex flex-col gap-6">
          <QueueForm
            accounts={accounts}
            slots={slots}
            schedule={schedule}
            action={queueBooking}
          />
          <PendingStrikes requests={pending} accountLabels={accountLabels} />
        </div>
        <BookingsCalendar bookings={bookings} accountLabels={accountLabels} />
      </div>

      <div className="mt-6">
        <AttemptsDropdown attempts={attempts} accountLabels={accountLabels} />
      </div>
    </div>
  );
}
