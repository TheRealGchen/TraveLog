"use client";

import type { Day, Traveler } from "@travel/client";
import { BedDoubleIcon, MapPinIcon, PlusIcon } from "lucide-react";
import { motion } from "motion/react";
import Link from "next/link";

import { TravelerAvatars } from "@/components/traveler-avatars";
import { dateParts, formatLongDate, utcToLocalTime } from "@/lib/time";

const PREVIEW = 4;

/** A day of the trip as a large clickable card, with its date front and center. */
export function DayCard({
  day,
  travelers,
  timeZone,
}: {
  day: Day;
  travelers: Traveler[];
  timeZone: string;
}) {
  const parts = dateParts(day.date);
  const people = travelers.filter((t) => day.activities.some((a) => a.travelerIds.includes(t.id)));
  const more = day.activities.length - PREVIEW;

  return (
    <motion.div
      className="h-full"
      whileHover={{ y: -4 }}
      transition={{ type: "spring", stiffness: 400, damping: 30 }}
    >
      <Link
        href={`/trips/${day.tripId}/days/${day.date}`}
        aria-label={`Day ${day.dayNumber}, ${formatLongDate(day.date)}`}
        className="flex h-full flex-col rounded-2xl sm:min-h-64 border bg-card p-5 shadow-sm transition-shadow outline-none hover:shadow-lg focus-visible:ring-3 focus-visible:ring-ring/60"
      >
        <div className="flex items-center gap-4">
          <div className="flex w-16 shrink-0 flex-col items-center rounded-xl bg-primary/10 py-2 text-primary">
            <span className="text-xs font-semibold uppercase">{parts.weekday}</span>
            <span className="text-3xl leading-none font-bold tabular-nums">{parts.day}</span>
            <span className="text-xs font-semibold uppercase">{parts.month}</span>
          </div>
          <div className="min-w-0">
            <p className="text-sm font-medium text-muted-foreground">Day {day.dayNumber}</p>
            <p className="truncate text-lg font-semibold">{formatLongDate(day.date)}</p>
          </div>
        </div>

        <div className="mt-4 space-y-1.5 text-sm">
          <p className="flex items-center gap-2">
            <BedDoubleIcon className="size-4 shrink-0 text-muted-foreground" />
            {day.lodging ? (
              <span className="truncate">Staying at {day.lodging.name}</span>
            ) : (
              <span className="text-muted-foreground">No lodging yet</span>
            )}
          </p>
          {day.startLocation && (
            <p className="flex items-center gap-2">
              <MapPinIcon className="size-4 shrink-0 text-muted-foreground" />
              <span className="truncate">Starting from {day.startLocation.name}</span>
            </p>
          )}
        </div>

        <div className="mt-4 flex-1 border-t pt-4">
          {day.activities.length === 0 ? (
            <p className="flex items-center gap-2 text-sm text-muted-foreground">
              <PlusIcon className="size-4" />
              Plan this day
            </p>
          ) : (
            <ul className="space-y-2 text-sm">
              {day.activities.slice(0, PREVIEW).map((a) => (
                <li key={a.id} className="flex gap-3">
                  <span className="w-12 shrink-0 font-medium text-primary tabular-nums">
                    {a.time ? utcToLocalTime(a.time.startAt, timeZone) : "—"}
                  </span>
                  <span
                    className={
                      a.status === "done" ? "truncate text-muted-foreground line-through" : "truncate"
                    }
                  >
                    {a.title}
                  </span>
                </li>
              ))}
              {more > 0 && <li className="text-muted-foreground">+{more} more</li>}
            </ul>
          )}
        </div>

        {people.length > 0 && (
          <div className="mt-4 flex justify-end">
            <TravelerAvatars travelers={people} size="sm" />
          </div>
        )}
      </Link>
    </motion.div>
  );
}
