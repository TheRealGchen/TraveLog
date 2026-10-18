"use client";

import type { Trip } from "@travel/client";

import { DayCard } from "@/components/day-card";
import { Skeleton } from "@/components/ui/skeleton";
import { errorMessage } from "@/lib/api";
import { useDays } from "@/lib/queries";

export function DaysTab({ trip }: { trip: Trip }) {
  const days = useDays(trip.id);

  if (days.isPending) {
    return (
      <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
        {[0, 1, 2].map((i) => (
          <Skeleton key={i} className="h-64 rounded-2xl" />
        ))}
      </div>
    );
  }
  if (days.isError) return <p className="text-destructive">{errorMessage(days.error)}</p>;

  return (
    <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
      {days.data.days.map((day) => (
        <DayCard key={day.date} day={day} travelers={trip.travelers} timeZone={trip.timezone} />
      ))}
    </div>
  );
}
