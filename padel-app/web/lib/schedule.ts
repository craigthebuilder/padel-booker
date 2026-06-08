// web/lib/schedule.ts — pure scheduling logic (no Next.js, no DB; easy to test).
//
// Timezone strategy: we do NOT hand-roll DST offsets. We ask Intl for the ET
// calendar date and ET wall-clock, and we store the trigger as an ET wall-clock
// string ("YYYY-MM-DDT07:02:00"). The Python worker resolves that to a real UTC
// instant using zoneinfo — the authoritative clock lives in one place.

const ET = 'America/New_York';
const RELEASE_MINUTES = 7 * 60 + 2; // 07:02 AM ET = the moment slots release

/** YYYY-MM-DD for a Date, in ET. (en-CA formats as YYYY-MM-DD.) */
export function etDateStr(d: Date): string {
  return new Intl.DateTimeFormat('en-CA', {
    timeZone: ET,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).format(d);
}

/** Minutes since ET midnight for a Date. (en-GB + hour12:false gives "HH:MM".) */
function etMinutesSinceMidnight(d: Date): number {
  const hhmm = new Intl.DateTimeFormat('en-GB', {
    timeZone: ET,
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  }).format(d);
  const [h, m] = hhmm.split(':').map(Number);
  return (h % 24) * 60 + m;
}

/** Add N calendar days to a YYYY-MM-DD string (timezone-safe; pure date math). */
export function addDays(dateStr: string, n: number): string {
  const [y, m, d] = dateStr.split('-').map(Number);
  const dt = new Date(Date.UTC(y, m - 1, d));
  dt.setUTCDate(dt.getUTCDate() + n);
  return dt.toISOString().slice(0, 10);
}

/** Day of week for a YYYY-MM-DD (0=Sun … 6=Sat), timezone-safe. */
export function dayOfWeek(dateStr: string): number {
  const [y, m, d] = dateStr.split('-').map(Number);
  return new Date(Date.UTC(y, m - 1, d)).getUTCDay();
}

export function isWeekend(dateStr: string): boolean {
  const dow = dayOfWeek(dateStr);
  return dow === 0 || dow === 6;
}

const WEEKDAY_NAMES = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
export function weekdayName(dateStr: string): string {
  return WEEKDAY_NAMES[dayOfWeek(dateStr)];
}

export type Schedule = {
  triggerDate: string; // ET date the strike fires (at 07:02)
  triggerAtEt: string; // ET wall-clock string the worker resolves to an instant
  targetDate: string; // ET date being booked (= triggerDate + 7)
  targetWeekend: boolean;
};

/**
 * Compute the next strike from `now`.
 *
 * ASSUMPTION (verify): "next 07:02 ET that hasn't passed" — today if currently
 * before 07:02 ET, else tomorrow. To force ALWAYS-tomorrow instead, change the
 * `triggerDate` line to `addDays(todayEt, 1)` unconditionally.
 */
export function computeSchedule(now: Date = new Date()): Schedule {
  const todayEt = etDateStr(now);
  const pastRelease = etMinutesSinceMidnight(now) >= RELEASE_MINUTES;
  const triggerDate = pastRelease ? addDays(todayEt, 1) : todayEt;
  const targetDate = addDays(triggerDate, 7);
  return {
    triggerDate,
    triggerAtEt: `${triggerDate}T07:02:00`,
    targetDate,
    targetWeekend: isWeekend(targetDate),
  };
}

/** Format seconds-since-midnight as "6:00 PM" for display. */
export function fmtSlotTime(secondsSinceMidnight: number): string {
  const total = Math.floor(secondsSinceMidnight / 60);
  let h = Math.floor(total / 60);
  const m = total % 60;
  const ampm = h >= 12 ? 'PM' : 'AM';
  h = h % 12 || 12;
  return `${h}:${String(m).padStart(2, '0')} ${ampm}`;
}
