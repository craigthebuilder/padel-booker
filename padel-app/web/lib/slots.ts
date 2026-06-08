// web/lib/slots.ts — selectable booking slots (confirmed from the RCKB UI).
//
// hour_start / hour_end are SECONDS since ET midnight — the exact format the
// RCKB POST payload wants (6:00 PM = 64800, 7:30 PM = 70200; that pair is the
// empirically-proven 6–7:30 PM booking). Durations vary (30/60/90 min); the API
// takes an explicit start+end, so that's fine.
//
// NOTE: only 6–7:30 PM is battle-tested. The rest are transcribed from the
// booking UI and get confirmed on the first dry-run/recon.

export type Slot = {
  label: string;
  hour_start: number;
  hour_end: number;
};

// seconds since ET midnight
const t = (hh: number, mm = 0) => hh * 3600 + mm * 60;

export const WEEKDAY_SLOTS: Slot[] = [
  { label: '7:00–8:00 AM', hour_start: t(7), hour_end: t(8) },
  { label: '8:00–9:00 AM', hour_start: t(8), hour_end: t(9) },
  { label: '9:00–9:30 AM', hour_start: t(9), hour_end: t(9, 30) },
  { label: '9:30–10:00 AM', hour_start: t(9, 30), hour_end: t(10) },
  { label: '10:00–10:30 AM', hour_start: t(10), hour_end: t(10, 30) },
  { label: '10:30–11:00 AM', hour_start: t(10, 30), hour_end: t(11) },
  { label: '11:00–11:30 AM', hour_start: t(11), hour_end: t(11, 30) },
  { label: '11:30 AM–12:00 PM', hour_start: t(11, 30), hour_end: t(12) },
  { label: '12:00–12:30 PM', hour_start: t(12), hour_end: t(12, 30) },
  { label: '12:30–1:00 PM', hour_start: t(12, 30), hour_end: t(13) },
  { label: '1:00–1:30 PM', hour_start: t(13), hour_end: t(13, 30) },
  { label: '1:30–2:00 PM', hour_start: t(13, 30), hour_end: t(14) },
  { label: '2:00–2:30 PM', hour_start: t(14), hour_end: t(14, 30) },
  { label: '2:30–3:00 PM', hour_start: t(14, 30), hour_end: t(15) },
  { label: '3:00–3:30 PM', hour_start: t(15), hour_end: t(15, 30) },
  { label: '3:30–4:00 PM', hour_start: t(15, 30), hour_end: t(16) },
  { label: '4:00–4:30 PM', hour_start: t(16), hour_end: t(16, 30) },
  { label: '4:30–5:00 PM', hour_start: t(16, 30), hour_end: t(17) },
  { label: '5:00–5:30 PM', hour_start: t(17), hour_end: t(17, 30) },
  { label: '5:30–6:00 PM', hour_start: t(17, 30), hour_end: t(18) },
  { label: '6:00–7:30 PM', hour_start: t(18), hour_end: t(19, 30) },
  { label: '7:30–9:00 PM', hour_start: t(19, 30), hour_end: t(21) },
];

export const WEEKEND_SLOTS: Slot[] = [
  { label: '8:00–9:30 AM', hour_start: t(8), hour_end: t(9, 30) },
  { label: '9:30–11:00 AM', hour_start: t(9, 30), hour_end: t(11) },
  { label: '11:00 AM–12:30 PM', hour_start: t(11), hour_end: t(12, 30) },
  { label: '12:30–1:00 PM', hour_start: t(12, 30), hour_end: t(13) },
  { label: '1:00–1:30 PM', hour_start: t(13), hour_end: t(13, 30) },
  { label: '1:30–2:00 PM', hour_start: t(13, 30), hour_end: t(14) },
  { label: '2:00–2:30 PM', hour_start: t(14), hour_end: t(14, 30) },
  { label: '2:30–3:00 PM', hour_start: t(14, 30), hour_end: t(15) },
  { label: '3:00–3:30 PM', hour_start: t(15), hour_end: t(15, 30) },
  { label: '3:30–4:00 PM', hour_start: t(15, 30), hour_end: t(16) },
  { label: '4:00–4:30 PM', hour_start: t(16), hour_end: t(16, 30) },
  { label: '4:30–6:00 PM', hour_start: t(16, 30), hour_end: t(18) },
  { label: '6:00–7:30 PM', hour_start: t(18), hour_end: t(19, 30) },
  { label: '7:30–9:00 PM', hour_start: t(19, 30), hour_end: t(21) },
];

export function slotsFor(weekend: boolean): Slot[] {
  return weekend ? WEEKEND_SLOTS : WEEKDAY_SLOTS;
}
