/**
 * Date and time helpers. The API returns UTC instants and calendar dates in the trip's
 * timezone. Trip times are always shown in the trip's timezone, never the browser's.
 */
import { TZDate } from "@date-fns/tz";
import { addDays, differenceInCalendarDays, format } from "date-fns";

/** "YYYY-MM-DD" -> a Date at local midnight, for calendar widgets that work in local Dates. */
export function parseDateOnly(value: string): Date {
  const [y, m, d] = value.split("-").map(Number);
  return new Date(y, m - 1, d);
}

/** A calendar widget's local Date -> "YYYY-MM-DD" (reads local fields, no timezone shift). */
export function formatDateOnly(value: Date): string {
  return format(value, "yyyy-MM-dd");
}

/** "YYYY-MM-DD" plus a number of days. */
export function addDaysToDateOnly(value: string, days: number): string {
  return formatDateOnly(addDays(parseDateOnly(value), days));
}

/** UTC ISO timestamp -> "HH:mm" wall-clock time in `timeZone`. */
export function utcToLocalTime(iso: string, timeZone: string): string {
  return format(new TZDate(iso, timeZone), "HH:mm");
}

/** UTC ISO timestamp -> "YYYY-MM-DD" calendar day in `timeZone`. */
export function utcToLocalDate(iso: string, timeZone: string): string {
  return format(new TZDate(iso, timeZone), "yyyy-MM-dd");
}

/** A day ("YYYY-MM-DD") and wall-clock time ("HH:mm") in `timeZone` -> UTC ISO with Z. */
export function localToUtc(date: string, time: string, timeZone: string): string {
  const [y, m, d] = date.split("-").map(Number);
  const [hh, mm] = time.split(":").map(Number);
  return new Date(new TZDate(y, m - 1, d, hh, mm, timeZone).getTime()).toISOString();
}

/**
 * Start and end wall-clock times on `date` -> UTC instants. An end time at or before the start
 * time is taken to be on the next day (e.g. 22:00 to 01:00).
 */
export function localRangeToUtc(
  date: string,
  start: string,
  end: string | null,
  timeZone: string,
): { startAt: string; endAt: string | null } {
  const startAt = localToUtc(date, start, timeZone);
  if (!end) return { startAt, endAt: null };
  let endAt = localToUtc(date, end, timeZone);
  if (endAt <= startAt) endAt = localToUtc(addDaysToDateOnly(date, 1), end, timeZone);
  return { startAt, endAt };
}

/** "10:00 – 12:00" in the trip's timezone; "+1" marks an end on a later day. */
export function formatTimeRange(
  startAt: string | null,
  endAt: string | null,
  timeZone: string,
): string {
  if (!startAt) return "All day";
  const start = utcToLocalTime(startAt, timeZone);
  if (!endAt) return start;
  const days = differenceInCalendarDays(
    parseDateOnly(utcToLocalDate(endAt, timeZone)),
    parseDateOnly(utcToLocalDate(startAt, timeZone)),
  );
  return `${start} – ${utcToLocalTime(endAt, timeZone)}${days > 0 ? ` (+${days})` : ""}`;
}

/** "Day 3, Thu Apr 4". */
export function formatDayHeader(dayNumber: number, date: string): string {
  return `Day ${dayNumber}, ${format(parseDateOnly(date), "EEE MMM d")}`;
}

/** "Thu, Apr 4". */
export function formatShortDate(date: string): string {
  return format(parseDateOnly(date), "EEE, MMM d");
}

/** "Apr 2 – 14, 2027", "Apr 28 – May 3, 2027", or "Dec 30, 2027 – Jan 2, 2028". */
export function formatDateRange(startDate: string, endDate: string): string {
  const start = parseDateOnly(startDate);
  const end = parseDateOnly(endDate);
  if (startDate === endDate) return format(start, "MMM d, yyyy");
  if (start.getFullYear() !== end.getFullYear()) {
    return `${format(start, "MMM d, yyyy")} – ${format(end, "MMM d, yyyy")}`;
  }
  if (start.getMonth() !== end.getMonth()) {
    return `${format(start, "MMM d")} – ${format(end, "MMM d, yyyy")}`;
  }
  return `${format(start, "MMM d")} – ${format(end, "d, yyyy")}`;
}

/** Badge text for the API's `daysUntilStart` and `status`. */
export function countdownLabel(daysUntilStart: number, status: string): string {
  if (status === "past") return "Completed";
  if (daysUntilStart === 0) return "Today!";
  if (status === "ongoing") return "In progress";
  return `${daysUntilStart} ${daysUntilStart === 1 ? "day" : "days"} to go`;
}

/** The browser's IANA timezone, used only as the default for a new trip. */
export function browserTimeZone(): string {
  return Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC";
}

/** Every IANA timezone the browser knows, with UTC first. */
export function allTimeZones(): string[] {
  const zones = Intl.supportedValuesOf("timeZone").filter((z) => z !== "UTC");
  return ["UTC", ...zones];
}
