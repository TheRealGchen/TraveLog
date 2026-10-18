"use client";

import type { Day, Trip } from "@travel/client";
import {
  ArrowLeftIcon,
  BedDoubleIcon,
  ChevronLeftIcon,
  ChevronRightIcon,
  GlobeIcon,
  MapPinIcon,
  PlusIcon,
} from "lucide-react";
import Link from "next/link";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";

import { ActivityItem } from "@/components/activity-item";
import { DayPlaceField } from "@/components/day-place-field";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { errorMessage } from "@/lib/api";
import { useAddActivity, useDay, useTrip, useUpdateDay } from "@/lib/queries";
import { addDaysToDateOnly, formatLongDate } from "@/lib/time";

export default function DayPage() {
  return (
    <Suspense>
      <DayPageContent />
    </Suspense>
  );
}

function DayPageContent() {
  const { tripId, date } = useParams<{ tripId: string; date: string }>();
  const trip = useTrip(tripId);
  const day = useDay(tripId, date);

  return (
    <main className="mx-auto w-full max-w-3xl px-4 py-8 sm:px-6 sm:py-12">
      <Link
        href={`/trips/${tripId}`}
        className="mb-8 inline-flex items-center gap-1.5 rounded-md text-sm text-muted-foreground outline-none hover:text-foreground focus-visible:ring-3 focus-visible:ring-ring/50"
      >
        <ArrowLeftIcon className="size-4" />
        {trip.data?.name ?? "Back to trip"}
      </Link>

      {(trip.isPending || day.isPending) && (
        <div className="space-y-4">
          <Skeleton className="h-12 w-2/3" />
          <Skeleton className="h-24 rounded-2xl" />
          <Skeleton className="h-28 rounded-2xl" />
        </div>
      )}
      {(trip.isError || day.isError) && (
        <div className="rounded-2xl border p-8 text-center">
          <p className="text-lg font-semibold">Couldn&apos;t load this day.</p>
          <p className="mt-2 text-muted-foreground">{errorMessage(trip.error ?? day.error)}</p>
        </div>
      )}
      {trip.data && day.data && <DayView trip={trip.data} day={day.data} />}
    </main>
  );
}

function DayView({ trip, day }: { trip: Trip; day: Day }) {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [expanded, setExpanded] = useState<string | null>(() => searchParams.get("activity"));
  const updateDay = useUpdateDay(trip.id, day.date);
  const prev = day.date > trip.startDate ? addDaysToDateOnly(day.date, -1) : null;
  const next = day.date < trip.endDate ? addDaysToDateOnly(day.date, 1) : null;
  const dayUrl = (d: string) => `/trips/${trip.id}/days/${d}`;

  return (
    <div className="space-y-8">
      <header className="flex items-start justify-between gap-4">
        <div className="space-y-2">
          <p className="inline-flex rounded-full bg-primary/10 px-3 py-1 text-sm font-semibold text-primary">
            Day {day.dayNumber}
          </p>
          <h1 className="text-3xl font-bold tracking-tight sm:text-4xl">
            {formatLongDate(day.date)}
          </h1>
          <p className="flex items-center gap-1.5 text-sm text-muted-foreground">
            <GlobeIcon className="size-4" />
            Times in {trip.timezone.replaceAll("_", " ")}
          </p>
        </div>
        <div className="flex shrink-0 gap-1">
          <Button
            variant="outline"
            size="icon-lg"
            aria-label="Previous day"
            disabled={!prev}
            onClick={() => prev && router.push(dayUrl(prev))}
          >
            <ChevronLeftIcon />
          </Button>
          <Button
            variant="outline"
            size="icon-lg"
            aria-label="Next day"
            disabled={!next}
            onClick={() => next && router.push(dayUrl(next))}
          >
            <ChevronRightIcon />
          </Button>
        </div>
      </header>

      <div className="grid gap-4 sm:grid-cols-2">
        <DayPlaceField
          key={`lodging-${day.lodging?.name ?? ""}`}
          id="day-lodging"
          label="Staying tonight"
          icon={<BedDoubleIcon className="size-4" />}
          placeholder="Hotel, Airbnb, friend's place…"
          value={day.lodging}
          onSave={(lodging) => updateDay.mutate({ lodging })}
        />
        <DayPlaceField
          key={`start-${day.startLocation?.name ?? ""}`}
          id="day-start"
          label="Starting from (optional)"
          icon={<MapPinIcon className="size-4" />}
          placeholder="Where the day begins"
          value={day.startLocation}
          onSave={(startLocation) => updateDay.mutate({ startLocation })}
        />
      </div>

      <section aria-label="Activities" className="space-y-4">
        <h2 className="text-xl font-semibold tracking-tight">Activities</h2>
        {day.activities.map((activity) => (
          <ActivityItem
            key={activity.id}
            activity={activity}
            day={day}
            trip={trip}
            expanded={expanded === activity.id}
            onToggle={(open) => setExpanded(open ? activity.id : null)}
          />
        ))}
        {day.activities.length === 0 && (
          <p className="rounded-2xl border border-dashed p-6 text-center text-muted-foreground">
            Nothing planned yet. Add the first activity below.
          </p>
        )}
        <QuickAdd trip={trip} date={day.date} onAdded={(id) => setExpanded(id)} />
      </section>
    </div>
  );
}

/** Type a title and press Enter; the new activity opens for details. */
function QuickAdd({
  trip,
  date,
  onAdded,
}: {
  trip: Trip;
  date: string;
  onAdded: (activityId: string) => void;
}) {
  const [title, setTitle] = useState("");
  const add = useAddActivity(trip.id);

  function submit(event: React.FormEvent) {
    event.preventDefault();
    if (!title.trim()) return;
    add.mutate(
      { date, body: { title: title.trim() } },
      {
        onSuccess: (activity) => {
          setTitle("");
          onAdded(activity.id);
        },
      },
    );
  }

  return (
    <form onSubmit={submit} className="flex gap-2">
      <Input
        aria-label="New activity"
        placeholder="Add an activity… (press Enter)"
        value={title}
        onChange={(e) => setTitle(e.target.value)}
        className="h-12 rounded-2xl text-base"
      />
      <Button type="submit" size="lg" className="h-12 rounded-2xl px-4" disabled={!title.trim() || add.isPending}>
        <PlusIcon />
        Add
      </Button>
    </form>
  );
}
