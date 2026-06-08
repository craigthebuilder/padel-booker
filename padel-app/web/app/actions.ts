'use server';

// Server Actions — the ONLY way the web tier writes to the DB.
// Wired directly to <form action={...}>; no manual fetch/endpoint needed.

import { revalidatePath } from 'next/cache';
import { createBookingRequest } from '@/lib/db';
import { computeSchedule } from '@/lib/schedule';

export async function queueBooking(formData: FormData): Promise<void> {
  const accountId = Number(formData.get('account_id'));
  const slot = String(formData.get('slot') ?? ''); // "64800-70200"
  const [hourStart, hourEnd] = slot.split('-').map(Number);

  if (!accountId || !Number.isFinite(hourStart) || !Number.isFinite(hourEnd)) {
    throw new Error('Invalid booking input');
  }

  // The schedule is computed server-side (authoritative) — never trust the
  // client for the trigger/target date.
  const sched = computeSchedule();

  createBookingRequest({
    account_id: accountId,
    target_date: sched.targetDate,
    hour_start: hourStart,
    hour_end: hourEnd,
    trigger_at: sched.triggerAtEt,
  });

  revalidatePath('/'); // re-render the dashboard with the new request
}
