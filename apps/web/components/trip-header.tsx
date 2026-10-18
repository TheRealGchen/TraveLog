"use client";

import type { Trip } from "@travel/client";
import { CalendarDaysIcon, GlobeIcon, MapPinIcon, PencilIcon } from "lucide-react";
import { useState } from "react";

import { DateRangePicker, type DateRangeValue } from "@/components/date-range-picker";
import { EditTripDialog } from "@/components/edit-trip-dialog";
import { TravelerRow } from "@/components/traveler-row";
import { Button } from "@/components/ui/button";
import { useUpdateTrip } from "@/lib/queries";
import { countdownLabel, formatDateRange } from "@/lib/time";

function BigCountdown({ trip }: { trip: Trip }) {
  if (trip.status === "upcoming") {
    return (
      <div className="sm:text-right">
        <p className="text-5xl font-bold tracking-tight text-primary tabular-nums sm:text-6xl">
          {trip.daysUntilStart}
        </p>
        <p className="text-sm font-medium text-muted-foreground">
          {trip.daysUntilStart === 1 ? "day to go" : "days to go"}
        </p>
      </div>
    );
  }
  return (
    <p className="text-3xl font-bold tracking-tight text-primary sm:text-4xl">
      {countdownLabel(trip.daysUntilStart, trip.status)}
    </p>
  );
}

export function TripHeader({ trip }: { trip: Trip }) {
  const update = useUpdateTrip(trip.id);
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState<DateRangeValue | null>(null);
  const dates = draft ?? { startDate: trip.startDate, endDate: trip.endDate };

  function commitDates() {
    const d = draft;
    setDraft(null);
    if (!d?.startDate || !d.endDate) return;
    if (d.startDate === trip.startDate && d.endDate === trip.endDate) return;
    update.mutate({ startDate: d.startDate, endDate: d.endDate });
  }

  return (
    <header className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-6">
        <div className="min-w-0 space-y-3">
          <div className="flex items-center gap-2">
            <h1 className="text-4xl font-bold tracking-tight sm:text-5xl">{trip.name}</h1>
            <Button
              variant="ghost"
              size="icon"
              aria-label="Edit trip"
              onClick={() => setEditing(true)}
            >
              <PencilIcon />
            </Button>
          </div>
          <div className="flex flex-wrap items-center gap-x-5 gap-y-2 text-muted-foreground">
            {trip.destination && (
              <span className="flex items-center gap-1.5">
                <MapPinIcon className="size-4" />
                {trip.destination}
              </span>
            )}
            <DateRangePicker
              value={dates}
              onChange={setDraft}
              onClose={commitDates}
              className="flex items-center gap-1.5 rounded-md underline-offset-4 outline-none hover:text-foreground hover:underline focus-visible:ring-3 focus-visible:ring-ring/50"
            >
              <CalendarDaysIcon className="size-4" />
              {formatDateRange(trip.startDate, trip.endDate)}
            </DateRangePicker>
            <span className="flex items-center gap-1.5" title="Trip timezone">
              <GlobeIcon className="size-4" />
              {trip.timezone.replaceAll("_", " ")}
            </span>
          </div>
        </div>
        <BigCountdown trip={trip} />
      </div>
      <TravelerRow trip={trip} />
      <EditTripDialog trip={trip} open={editing} onOpenChange={setEditing} />
    </header>
  );
}
